# -*- coding: utf-8 -*-
"""Recover lost column headers from the PDF text layer.

For each data column the band grid left unnamed ("列N"), the paper's own header is still
in the text layer. The header is the nearest line-group ABOVE the first data row that
occupies more than one column - that is what distinguishes it from the English caption and
the body prose sitting further up the page.

Usage:
    python src/recover_headers.py --dry-run
    python src/recover_headers.py --apply
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import pymupdf            # noqa: E402
import extract_band as E  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))

# Headers read off the source page and confirmed by eye, where the grid lost or shifted them.
#
# Each entry is keyed by (band index, table index) and gives the columns in order, together
# with where on the page the text was read from. They are here rather than inferred because
# in every one of these the grid's own column boundaries disagree with the paper's: it files
# a heading in the middle of a merged cell and drops a label into the neighbouring column, so
# there is no rule that recovers them - only the page knows.
#
#   (26, 17) 附表7 p58 y104: 化合物 | 阈值(μg·L-1) | GRD-1 | GRD-JC | GRD-PD | GRD-2 | JPLG
#             | LGTQ.  The band has a gap at column 2 and everything after it one column to
#             the right of where the paper prints it.
#   (26, 21) 附表8 p62 y107: 化合物 | TT-1Sb | TT-2Sb | TT-4Sb | TJ-1Sb | TJ-2Sb | TJ-4Sb.
#             The header never reached the band at all; only a stray 醇类 category row did.
#   (26, 22) 附表8 p63 y107: the same table with Sb dropped from every sample code.
#   (21,  6) 表2-3 p36 y619: 风味物质 | 1 | 2 | 3 | 4 | 5.  The grid merged the level
#             columns into pairs, so the cells read "1 2" and "3 4"; the label is written the
#             way the cell holds it rather than split, because the measurements themselves
#             are still merged in the same cells and splitting one without the other would
#             misstate what the column contains.
KNOWN_HEADERS = {
    (26, 17): ["化合物", "阈值(μg·L-1)", "GRD-1", "GRD-JC", "GRD-PD", "GRD-2", "JPLG",
               "LGTQ"],
    (26, 21): ["化合物", "TT-1Sb", "TT-2Sb", "TT-4Sb", "TJ-1Sb", "TJ-2Sb", "TJ-4Sb"],
    (26, 22): ["化合物", "TT-1S", "TT-2S", "TT-4S", "TJ-1S", "TJ-2S", "TJ-4S"],
    (21, 6): ["风味物质", "1 2", "3 4", "5"],
    # (21, 8) is the CONTINUATION of 表2-3 on p39; its header is on p36 with 表2-3's, and
    # the five columns there are not merged the way they are in the first part.
    (21, 8): ["", "1", "2", "3", "4", "5"],
}

# Longest a header cell may be. Sample names, group labels and units all fit; the Chinese
# and English titles above the table do not. This is the whole discriminator between the
# two, because both sit above the body and both span every column.
HEADER_CELL = 12

# The English titles are broken into one word per grid cell, so a caption line looks exactly
# like a header line to every other test here - it is short, it is above the body, and it
# covers several columns. Function words are what is left of it once the words that could be
# a name are gone, so they are refused outright.
STOPWORD = re.compile(
    r"^(and|of|the|in|for|with|to|on|at|by|from|a|an|is|as|or|et|al|no\.|appendix|tab\.|"
    r"table|fig\.|continu\w*|续|表|附表)$", re.I)

spec = importlib.util.spec_from_file_location(
    "builder", os.path.join(HERE, "build_rec整理.py"))
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


def pdf_for(idx):
    for e in json.load(open(os.path.join(REOUT, "sheet_map.json"), encoding="utf-8")):
        if e.get("idx") == idx and e.get("path") and os.path.exists(e["path"]):
            return e["path"]
    return None


def col_of(x, bounds):
    for i in range(len(bounds) - 1):
        if bounds[i] <= x < bounds[i + 1]:
            return i
    return None


def group_lines(words, tol=3.0):
    """Words into visual lines by their y baseline."""
    lines = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        if lines and abs(w[1] - lines[-1][0]) <= tol:
            lines[-1][1].append(w)
        else:
            lines.append((w[1], [w]))
    return lines


def match_table(tables, band_table):
    """
    Find the page_tables() result that produced this band table.

    Compared on the first row that has a name in column 0, because the caption and the
    row count both vary once the grid has done its own repairs.
    """
    want = None
    for r in band_table.get("rows", []):
        if r and str(r[0] or "").strip():
            want = [str(x or "").strip() for x in r]
            break
    if not want:
        return None
    for t in tables:
        for r in t.get("rows", []):
            if r and str(r[0] or "").strip() and [str(x or "").strip() for x in r] == want:
                return t
    return None


def recover(idx, ti, band_table, targets, name_col=0):
    """targets: list of column indices that need a name."""
    pages = band_table.get("pages") or []
    if not pages:
        return {}, "no page recorded"
    pdf = pdf_for(idx)
    if not pdf:
        return {}, "pdf not found"
    doc = pymupdf.open(pdf)
    got, note = {}, None
    try:
        for page_no in pages:
            pg = doc[page_no - 1]
            tables = E.page_tables(pg)
            t = match_table(tables, band_table)
            if not t or not t.get("bounds"):
                continue
            b = t["bounds"]
            x_lo, y_lo, x_hi, y_hi = t["bbox"]
            words = [w for w in pg.get_text("words")
                     if y_lo - 2 <= w[1] <= y_hi and x_lo - 2 <= w[0] <= x_hi + 2]
            lines = group_lines(words)

            # Where the body starts. Taken from the PROMOTED body, not from raw rows: on
            # several tables rows[0] is itself the header, and matching on it put the search
            # one row too high and made the header look like the body.
            _hdr, body = B.promote_header_rows(band_table)
            hdr = _hdr
            info = B.classify_columns(band_table)
            body_sig = None
            for r in body:
                cells = [str(x or "").strip() for x in r if str(x or "").strip()]
                if cells:
                    body_sig = cells[:2]
                    break
            if not body_sig:
                continue
            data_y = None
            for y, ws in lines:
                texts = [w[4].strip() for w in ws]
                if all(any(t == x or x in t for t in texts) for x in body_sig):
                    data_y = y
                    break
            if data_y is None:
                continue

            # Where each wanted column's DATA actually sits on the page.
            #
            # Assigning the header words through the column bounds looked right and was
            # not: the grid's bounds are derived from the band as a whole, and a header word
            # whose midpoint falls a few points past a boundary is assigned to the next
            # column. On 附表3 the word "定量离子" sits at x=171 over the column holding
            # 84 / 71 / 99, and by midpoint it landed one column to the right - which is
            # exactly why that column had no name and why no amount of re-reading the header
            # row could find one. Anchoring on the x of the column's own measurements is
            # what the eye does, and it does not depend on the bounds at all.
            axis = {}
            support = {}
            for c in targets:
                xs = []
                for r in body:
                    if c >= len(r):
                        continue
                    want = str(r[c] or "").strip()
                    if not want:
                        continue
                    # Locate THIS ROW's line first, by its leading cell, and only then take
                    # the wanted value from that line. Searching the whole page for the text
                    # "42" finds the 42 in the JPLG column of some other row too, and the
                    # median of those x positions drifts a whole column to the right -
                    # which is how 附表7's GRD-1 column came back labelled GRD-2.
                    head = next((str(x or "").strip() for x in r
                                 if str(x or "").strip()), "")
                    if not head:
                        continue
                    for y, ws in lines:
                        if y <= data_y:
                            continue
                        if not any(w[4].strip() == head for w in ws):
                            continue
                        for w in ws:
                            if w[4].strip() == want:
                                xs.append((w[0] + w[2]) / 2.0)
                        break
                if xs:
                    # Mode, not median. A handful of rows in every one of these tables has
                    # a missing cell, and the grid then slides the rest of the row sideways,
                    # so a minority of the matches land in the wrong column. The median
                    # follows that minority - 附表7's axis came out at 445 (the GRD-PD
                    # column) when every correct match was at 284. The column's position is
                    # the value most of the rows agree on.
                    bucket = {}
                    for x in xs:
                        k = round(x / 6.0)
                        bucket[k] = bucket.get(k, 0) + 1
                    best_k = max(bucket, key=lambda k: bucket[k])
                    axis[c] = best_k * 6.0
                    support[c] = bucket[best_k]
            if not axis:
                continue
            # a column whose position only one or two rows agree on has not been located,
            # it has been guessed
            axis = {c: x for c, x in axis.items() if support.get(c, 0) >= 3}
            if not axis:
                continue

            # Walk up looking for the header line. Each rule below was added after it
            # recovered the wrong thing:
            #   - cells must be short. Both titles sit above the table and span every
            #     column, so "names the most columns" picks the title every time.
            #   - pure digits are refused: that is a serial-number line.
            #   - stay near the body, so a neighbouring table's header cannot be adopted.
            #   - the label must sit over its own column.
            best = ({}, 0, None)
            for y, ws in reversed([L for L in lines if L[0] < data_y]):
                if data_y - y > 60:
                    break
                if len(ws) < 2:
                    continue
                if max(len(w[4].strip()) for w in ws) > HEADER_CELL:
                    continue                      # a title or a sentence, not a header
                cand = {}
                for w in ws:
                    txt = w[4].strip()
                    if not txt or re.fullmatch(r"[\d.,]+", txt):
                        continue
                    if STOPWORD.match(txt):
                        continue
                    mx = (w[0] + w[2]) / 2.0
                    near = min(axis, key=lambda c: abs(axis[c] - mx))
                    if abs(axis[near] - mx) <= 34 and near not in cand:
                        cand[near] = txt
                if len(cand) > best[1]:
                    best = (cand, len(cand), y)
                if best[1] == len(targets):
                    break

            # Refuse a label that is already spoken for.
            #
            # Some of these columns are spacers - band_28 prints 含量 | 相对保留时间 |
            # (blank) | 含量 | ..., and the grid files the blank as a column of its own.
            # A recovery that hands such a column its neighbour's name produces a
            # concentration column that the paper never printed, which is worse than 列N.
            taken = {}
            for c, _u in info["data_cols"]:
                lab = B.sample_label(band_table, c, 0, hdr)
                if lab and not lab.startswith("列"):
                    taken.setdefault(lab, []).append(c)
            cand_out = {}
            for c, txt in best[0].items():
                owner = taken.get(txt) or []
                near = [o for o in owner if abs(o - c) <= 1]
                if near:
                    continue
                cand_out[c] = txt
            best = (cand_out, len(cand_out), best[2])
            got, note = best[0], ("header line y=%.0f" % best[2]) if best[2] \
                else "no candidate line"
    finally:
        doc.close()
    return got, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    report = []
    changed = 0
    for f in sorted(glob.glob(os.path.join(REOUT, "band_*.json"))):
        if ".orig." in f:
            continue
        idx = int(os.path.basename(f)[5:7])
        d = json.load(open(f, encoding="utf-8"))
        dirty = False
        for ti, t in enumerate(d["tables"]):
            try:
                info = B.classify_columns(t)
            except Exception:
                continue
            targets = [c for c, _u in info["data_cols"]
                   if B.sample_label(t, c, 0, info.get("hdr_rows")).startswith("列")]
            if not targets:
                continue
            # a header read off the page beats anything this script could infer
            known = KNOWN_HEADERS.get((idx, ti))
            if known:
                got = {c: known[c] for c in targets if c < len(known)}
                if got:
                    note = "KNOWN_HEADERS (page-verified)"
                else:
                    got, note = {}, "KNOWN_HEADERS has no entry for column %s" % targets
            else:
                got, note = recover(idx, ti, t, targets)
            report.append("band_%02d t%-3d pages=%-12s 目标列 %s"
                          % (idx, ti, str(t.get("pages")), targets))
            if not got:
                report.append("        未取到表头（%s）" % note)
                continue
            hdr_rows = t.get("header_rows")
            if hdr_rows is None:
                hdr_rows = t["header_rows"] = [["" for _ in range(t["n_col"])]]
            # append a row carrying only the recovered labels, so the existing header block
            # keeps its own rows and sample_label still sees this one last.
            # Written back onto the table itself - hdr_rows IS that list, not a copy. The
            # version that built a copy with list(...) and appended to it reported every
            # header as recovered and persisted none of them.
            row = ["" for _ in range(t["n_col"])]
            for c, v in got.items():
                row[c] = v
            hdr_rows.append(row)
            report.append("        取到 %s  （%s）" % (got, note))
            dirty = True
            changed += 1
        if dirty and a.apply:
            json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    txt = "表头回捞报告%s\n修复表数: %d\n%s" % (
        "" if not a.dry_run else "  [DRY RUN]", changed, "\n".join(report))
    print(txt)
    if a.apply:
        p = os.path.join(REOUT, "header_recovery.txt")
        open(p, "w", encoding="utf-8").write(txt)
        print("\n-> %s" % p)


if __name__ == "__main__":
    main()