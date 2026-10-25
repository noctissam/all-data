# -*- coding: utf-8 -*-
"""
Extract tables from papers that carry a real text layer, using PyMuPDF find_tables().

This is the fast lane. Profiling showed 23 of the 33 mapped PDFs have both a text layer
and vector table rules, and find_tables() reads those directly - no OCR, no guessing
about column geometry, and the compound names come out exactly as typeset. For Chinese
papers this matters twice over: the CNKI thesis text layer is OCR garbage (酯 rendered
as 酷), so anything read from a text layer has to be checked for reliability first
(see text_is_reliable).

Cross-page tables: a long aroma table repeats its header on every page, so fragments
are stitched when the header signature matches and the pages are consecutive.

Usage:
    python src/extract_textlayer.py [--only 3,7] [--limit 5]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymupdf  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MAP = os.path.join(ROOT, "NEW-TRY", "out", "re整理", "sheet_map.json")
OUTDIR = os.path.join(ROOT, "NEW-TRY", "out", "re整理")

# ---------------------------------------------------------------- column roles
ROLES = [
    ("cas",        r"CAS|化学 CAS|CAS\s*号"),
    ("name_cn",    r"香气物质|化合物名称|物质名称|呈香化合物|风味物质|风味化合物|化合物|物质"),
    ("ri",         r"保留指数|RI\b| Kovats"),
    ("odor_desc",  r"香气描述|风味描述|呈香|描述"),
    ("odor_val",   r"香气强度|OAV|香气活|FD\s*值|FD值|嗅闻强度"),
    ("conc_group", r"质量浓度|相对含量|含量|浓度|定量"),
    ("threshold",  r"阈值|嗅闻阈值|感官阈值"),
    ("quant_ion",  r"定量离子|特征离子|m/z|离子"),
    ("method",     r"方法|定性依据|鉴定"),
    ("no",         r"^序$|^序号$|^编号$|No\.?$"),
    ("rt",         r"保留时间|保留值"),
]
ROLE_RE = [(k, re.compile(p, re.I)) for k, p in ROLES]

UNIT_RE = re.compile(
    r"[（(]\s*"
    r"((?:μ|u|m)?\s*g\s*/\s*l(?:\s*[·*.]\s*-?\s*1)?"
    r"|mg\s*/\s*kg"
    r"|μg\s*/\s*kg"
    r"|%\s*v?/?\s*v?"
    r"|mg\s*/\s*l"
    r"|μg\s*/\s*l)"
    r"\s*[）)]", re.I)


def text_is_reliable(doc, min_digit_ratio=0.03):
    """
    A born-digital text layer keeps its digits; the CNKI OCR layer loses them (the
    table caption 表3-12 came back as 表一). Digit density separates the two without
    guessing from the producer string.
    """
    chars = digits = 0
    for p in list(doc)[:6]:
        t = p.get_text()
        chars += len(t)
        digits += sum(ch.isdigit() for ch in t)
    return (digits / max(chars, 1)) >= min_digit_ratio


def role_of(header_text, col):
    h = header_text[col] if col < len(header_text) else ""
    if not h.strip():
        return None
    for k, rx in ROLE_RE:
        if rx.search(h):
            return k
    return None


def clean(s):
    if s is None:
        return ""
    s = s.replace("　", " ").replace("\xa0", " ")
    return re.sub(r"[ \t]*\n[ \t]*", " ", s).strip()


def merged_header(rows, scan=6):
    """
    Build per-column header text from the leading rows.

    Scanning more than the first 3 rows matters because the "text" strategy folds the
    header into the first data row, giving cells like "序号 4" or "香气物质 丁酸丁酯".
    The words we need are still in there, so roles are resolved by scanning several
    rows rather than assuming row 0 is a clean header.
    """
    ncol = max((len(r) for r in rows), default=0)
    parts = [[] for _ in range(ncol)]
    for r in rows[:scan]:
        for c in range(ncol):
            v = clean(r[c]) if c < len(r) else ""
            if v and v not in parts[c]:
                parts[c].append(v)
    return [" ".join(p) for p in parts]


def column_roles(rows, ncol, scan=6):
    """
    Per column, the first role keyword appearing in any of its leading cells.
    """
    roles = []
    for c in range(ncol):
        found = None
        for r in rows[:scan]:
            v = clean(r[c]) if c < len(r) else ""
            if not v:
                continue
            for k, rx in ROLE_RE:
                if rx.search(v):
                    found = k
                    break
            if found:
                break
        roles.append(found)
    return roles


def header_sig(hdr):
    return "|".join(re.sub(r"\s+", "", h) for h in hdr)


def extract_paper(entry, args):
    path = entry.get("path")
    res = dict(idx=entry["idx"], sheet=entry["sheet"], pdf=entry.get("pdf"),
               route="text-layer", n_tables=0, fragments=0, tables=[], note="")
    if not path or not os.path.exists(path):
        res["note"] = "pdf missing"
        return res
    doc = pymupdf.open(path)
    if not text_is_reliable(doc):
        res["note"] = "text layer looks OCR-derived - needs the image pipeline"
        res["route"] = "needs-ocr"
        doc.close()
        return res

    frags = []
    seen_bbox = []
    for pno in range(doc.page_count):
        page = doc[pno]
        # Strategy order matters. The "text" strategy groups a whole page by whitespace
        # and returns MORE rows, but it folds the header row into the first data row
        # (a cell becomes "序号 4"). Where real rules exist, lines_strict/lines are clean,
        # so they win; text is only used when the line strategies find nothing.
        best, best_score = [], -1.0
        for strat in ("lines_strict", "lines", "text"):
            try:
                found = page.find_tables(strategy=strat)
            except Exception as e:
                res["note"] += "find_tables(%s) p%d: %s " % (strat, pno + 1, e)
                continue
            cand = []
            for t in found.tables:
                try:
                    rows = t.extract()
                except Exception:
                    continue
                cand.append((t, rows))
            rows_tot = sum(len(r) for _t, r in cand)
            if rows_tot == 0:
                continue
            good = sum(1 for _t, r in cand
                       if len([x for x in r
                               if sum(1 for c in x if (c or "").strip()) >= 3]) >= 3)
            score = good * 1000 + min(rows_tot, 900)
            if strat.startswith("lines"):
                score += 500          # tie-break toward rule-based extraction
            if score > best_score:
                best, best_score = cand, score
            if strat == "lines" and good >= 2:
                break                 # clean enough, do not bother with the text strategy
        for t, rows in best:
            rows = [[clean(c) for c in r] for r in rows if any(clean(c) for c in r)]
            if len(rows) < 3:
                continue
            ncol = max(len(r) for r in rows)
            if ncol < 3:          # a 2-column layout block is usually not a data table
                continue
            rows = [r + [""] * (ncol - len(r)) for r in rows]
            bb = [round(v, 1) for v in t.bbox]
            if any(abs(bb[0] - s[0]) < 3 and abs(bb[3] - s[3]) < 3 for s in seen_bbox):
                continue
            seen_bbox.append(bb)
            frags.append(dict(page=pno + 1, rows=rows, bbox=bb))
    doc.close()

    # stitch: consecutive pages, same column count, compatible header
    tables = []
    for f in frags:
        hdr = merged_header(f["rows"])
        sig = header_sig(hdr)
        placed = False
        for t in tables:
            if f["page"] - t["pages"][-1] <= 1 and t["sig"] == sig:
                t["rows"].extend(f["rows"])
                t["pages"].append(f["page"])
                t["frags"] += 1
                placed = True
                break
        if not placed:
            tables.append(dict(header=hdr, sig=sig, rows=list(f["rows"]),
                               pages=[f["page"]], frags=1))

    for t in tables:
        t["n_row"] = len(t["rows"])
        t["n_col"] = len(t["header"])
        t["roles"] = column_roles(t["rows"], t["n_col"])
        t["units"] = [(UNIT_RE.search(t["header"][c]).group(1).replace(" ", "")
                       if UNIT_RE.search(t["header"][c]) else "")
                      for c in range(t["n_col"])]
    res["tables"] = tables
    res["n_tables"] = len(tables)
    res["fragments"] = len(frags)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma separated sheet indices")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=OUTDIR)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    entries = json.load(open(MAP, encoding="utf-8"))
    only = set(int(x) for x in a.only.split(",") if x.strip())
    done = 0
    summary = []
    for e in entries:
        if only and e["idx"] not in only:
            continue
        if a.limit and done >= a.limit:
            break
        r = extract_paper(e, a)
        fn = os.path.join(a.out, "raw_%02d.json" % e["idx"])
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        if r["route"] != "text-layer":
            print("  #%-3d %-46s -> %s" % (e["idx"], (e.get("pdf") or "")[:46], r["note"][:60]))
        else:
            big = [t for t in r["tables"] if t["n_col"] >= 3 and t["n_row"] >= 5]
            print("  #%-3d %-46s tables=%-3d big=%-2d rows=%-5d %s" % (
                e["idx"], (e.get("pdf") or "")[:46], r["n_tables"], len(big),
                sum(t["n_row"] for t in big),
                "; ".join("%dx%d" % (t["n_row"], t["n_col"]) for t in big[:4])))
        summary.append(dict(idx=e["idx"], route=r["route"], n_tables=r["n_tables"],
                            note=r["note"][:80]))
        done += 1
    print("\nprocessed %d papers -> %s" % (done, a.out))


if __name__ == "__main__":
    main()
