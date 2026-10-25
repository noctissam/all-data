# -*- coding: utf-8 -*-
"""
Step 1 - locate three-line tables ("三线表") in a PDF and render two crops each.

A three-line table is recognised structurally, not by OCR:
    rule1 (top)  ----------  header rule  ----------  rule3 (bottom)
No vertical rules, no interior rules.

For every detected table two images are written:
    <id>_<page>_A.png   pass A, dpi 300   (main extraction)
    <id>_<page>_B.png   pass B, dpi 400   (verification pass, same content)

Usage:
    python src/s1_detect_tables.py "<pdf path>" [--dpi-main 300] [--dpi-check 400]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymupdf  # noqa: E402

from common import (CFG, GRID_DIR, IMG_DIR, LOG_DIR, PREVIEW_DIR, TABLES_JSON,  # noqa: E402
                    ensure_dirs, log, save_json, tid)


# --------------------------------------------------------------------------- rules
def collect_rules(page, cfg):
    """Thin, wide, flat shapes = candidate table rules."""
    out = []
    for d in page.get_drawings():
        width = d.get("width") or 0.0
        for it in d["items"]:
            op = it[0]
            if op == "re":
                r = it[1]
                if r.width < cfg["min_rule_w"] or r.height > cfg["max_rule_h"]:
                    continue
                if r.height < 0.05:
                    continue
                out.append(dict(y=(r.y0 + r.y1) / 2.0, x0=r.x0, x1=r.x1, t=r.height, src="re"))
            elif op == "qu":
                r = it[1].rect
                if r.width < cfg["min_rule_w"] or r.height > cfg["max_rule_h"]:
                    continue
                out.append(dict(y=(r.y0 + r.y1) / 2.0, x0=r.x0, x1=r.x1, t=r.height, src="qu"))
            elif op == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) > cfg["flat_tol"]:
                    continue
                x0, x1 = sorted((a.x, b.x))
                if x1 - x0 < cfg["min_rule_w"]:
                    continue
                out.append(dict(y=(a.y + b.y) / 2.0, x0=x0, x1=x1, t=width, src="l"))
    return merge_rules(out, cfg)


def x_overlap_ratio(r1, r2):
    inter = min(r1["x1"], r2["x1"]) - max(r1["x0"], r2["x0"])
    if inter <= 0:
        return 0.0
    return inter / min(r1["x1"] - r1["x0"], r2["x1"] - r2["x0"])


def merge_rules(rules, cfg):
    """Collapse duplicated / doubled rules drawn on top of each other."""
    out = []
    for r in sorted(rules, key=lambda z: z["y"]):
        for o in out:
            if abs(o["y"] - r["y"]) <= cfg["rule_dy_tol"] and \
               x_overlap_ratio(o, r) >= cfg["rule_ox"]:
                o["y"] = (o["y"] + r["y"]) / 2.0
                o["x0"] = min(o["x0"], r["x0"])
                o["x1"] = max(o["x1"], r["x1"])
                o["t"] = max(o["t"], r["t"])
                o["src"] = o["src"] + "+" + r["src"]
                break
        else:
            out.append(dict(r))
    return sorted(out, key=lambda z: z["y"])


# --------------------------------------------------------------------------- glyphs
def line_intervals(page, box, gap=8.0, max_gap=9.0, cap=3):
    """
    Contiguous text lines just above / below a rule, so the crop can start and end in
    blank space instead of slicing a line of glyphs in half.
    Returns (lines_above, lines_below) as (y0, y1) tuples.
    """
    search = (box[0] - 80, max(box[1] - 80, 0), box[2] + 80, min(box[3] + 60, 10000))
    raw = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.width > 40 or r.height > 14 or r.width < 0.2:
            continue
        if not (search[1] <= r.y0 and r.y1 <= search[3]):
            continue
        raw.append(r)
    if not raw:
        return [], []
    raw.sort(key=lambda r: r.y0)
    merged = []
    for r in raw:
        if merged and r.y0 - merged[-1][1] <= 1.2:
            merged[-1][1] = max(merged[-1][1], r.y1)
        else:
            merged.append([r.y0, r.y1])
    above, below = [], []
    y = box[1]
    while len(above) < cap:
        cand = [m for m in merged if m[1] <= y + 0.5]
        if not cand:
            break
        last = cand[-1]
        if y - last[1] > max_gap:
            break
        above.append(tuple(last))
        y = last[0]
    y = box[3]
    while len(below) < cap:
        cand = [m for m in merged if m[0] >= y - 0.5]
        if not cand:
            break
        first = cand[0]
        if first[0] - y > max_gap:
            break
        below.append(tuple(first))
        y = first[1]
    return above, below


def glyph_items(page, box):
    """
    Small vector outlines inside box, grouped into text lines.
    This PDF has no text layer, so glyph paths are the only cheap pre-OCR signal.
    """
    lines = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.width > 40 or r.height > 14 or r.width < 0.2:
            continue
        cy = (r.y0 + r.y1) / 2.0
        if not (box[1] <= cy <= box[3]):
            continue
        placed = False
        for ln in lines:
            if abs(ln["cy"] - cy) <= 3.0:
                ln["items"].append((r.x0, r.x1))
                ln["cy"] = (ln["cy"] * ln["n"] + cy) / (ln["n"] + 1)
                ln["n"] += 1
                placed = True
                break
        if not placed:
            lines.append(dict(cy=cy, n=1, items=[(r.x0, r.x1)]))
    lines.sort(key=lambda z: z["cy"])
    return lines


def runs_of_line(items, gap=4.0):
    """Split one text line's x-intervals into cell-ish runs separated by blank gaps."""
    items = sorted(items)
    runs = []
    cur = [items[0]]
    for a, b in items[1:]:
        if a - cur[-1][1] > gap:
            runs.append(cur)
            cur = [(a, b)]
        else:
            cur.append((a, b))
    runs.append(cur)
    return [(g[0][0], g[-1][1]) for g in runs]


def tab_stats(page, box, mid_y):
    """
    Tabularity evidence for a candidate box.
    Body = everything between the header rule and the bottom rule, i.e. the data rows.
    A real three-line table has many body lines that split into >=3 horizontally
    separated runs; a decorative rule block (article info banner, figure caption)
    has prose lines that stay as 1-2 runs.
    """
    lines = glyph_items(page, box)
    body = [ln for ln in lines if ln["cy"] > mid_y + 1.0]
    head = [ln for ln in lines if ln["cy"] <= mid_y + 1.0]
    nruns = [len(runs_of_line(ln["items"])) for ln in body]
    multi = sum(1 for k in nruns if k >= 3)
    xs = []
    for ln in body:
        xs.extend(runs_of_line(ln["items"]))
    ncol = len(runs_of_line([(a, b) for a, b in xs], gap=6.0)) if xs else 0
    med = sorted(nruns)[len(nruns) // 2] if nruns else 0
    return dict(
        n_body_rows=len(body),
        n_head_rows=len(head),
        med_runs_body=med,
        frac_rows_3plus=round(multi / len(body), 3) if body else 0.0,
        body_col_runs=ncol,
    )


def glyph_rows(page, box, cfg):
    return len(glyph_items(page, box))


# --------------------------------------------------------------------------- detect
def detect_page(page, cfg):
    """Return list of candidate tables on one page."""
    rules = collect_rules(page, cfg)
    cands = []
    n = len(rules)
    for i in range(n):
        top = rules[i]
        for k in range(i + 1, n):
            bot = rules[k]
            h = bot["y"] - top["y"]
            if h < cfg["min_table_h"]:
                continue
            if h > cfg["max_table_h"]:
                break
            if x_overlap_ratio(top, bot) < cfg["min_x_overlap"]:
                continue
            mids = []
            for m in rules[i + 1:k]:
                frac = (m["y"] - top["y"]) / h
                if frac > cfg["max_mid_frac"]:
                    continue
                if max(x_overlap_ratio(m, top), x_overlap_ratio(m, bot)) < 0.30:
                    continue
                mids.append((m, frac))
            if not mids:
                continue
            mid, frac = mids[-1]     # lowest acceptable header rule
            extra = [m for m, _f in mids[:-1]]
            extra += [r for r in rules[i + 1:k]
                      if abs(r["y"] - mid["y"]) > cfg["rule_dy_tol"]]
            x0 = min(top["x0"], bot["x0"])
            x1 = max(top["x1"], bot["x1"])
            box = (x0, top["y"], x1, bot["y"])
            # Grow the crop outwards to blank space so caption / note lines above and
            # below the rules come out whole instead of being sliced through.
            above, below = line_intervals(page, box)
            y_top = (above[0][0] - cfg["pad_top"] if above else top["y"] - cfg["pad_top"])
            y_bot = (below[-1][1] + cfg["pad_bot"] if below else bot["y"] + cfg["pad_bot"])
            crop = (x0 - cfg["pad_x"], y_top, x1 + cfg["pad_x"], y_bot)
            st = tab_stats(page, box, mid["y"])
            cands.append(dict(
                page=page.number + 1,
                box=[round(v, 2) for v in box],
                crop=[round(v, 2) for v in crop],
                rules=dict(top=[round(top["y"], 2), round(top["x0"], 2), round(top["x1"], 2), top["t"]],
                           mid=[round(mid["y"], 2), round(mid["x0"], 2), round(mid["x1"], 2), mid["t"]],
                           bottom=[round(bot["y"], 2), round(bot["x0"], 2), round(bot["x1"], 2), bot["t"]]),
                h_pt=round(h, 2),
                w_pt=round(x1 - x0, 2),
                mid_frac=round(frac, 3),
                extra_rules=len(set(round(m["y"], 1) for m in extra)),
                n_text_rows=st["n_body_rows"] + st["n_head_rows"],
                tab=st,
            ))
    return cands, rules


def looks_like_table(c, cfg):
    """Reject decorative rule blocks: too few body rows, or body rows not split up."""
    t = c["tab"]
    if t["n_body_rows"] < cfg["min_body_rows"]:
        return False, "body rows %d < %d" % (t["n_body_rows"], cfg["min_body_rows"])
    if t["med_runs_body"] < cfg["min_med_runs"]:
        return False, "median runs/row %.1f < %d" % (t["med_runs_body"], cfg["min_med_runs"])
    if t["frac_rows_3plus"] < cfg["min_frac_3plus"]:
        return False, "rows with >=3 runs %.2f < %.2f" % (t["frac_rows_3plus"], cfg["min_frac_3plus"])
    return True, "ok"


def dedupe(cands):
    """Drop candidates nested inside a bigger one."""
    cands.sort(key=lambda c: -c["h_pt"])
    kept = []
    for c in cands:
        b = c["box"]
        dup = False
        for k in kept:
            kb = k["box"]
            ix = min(b[2], kb[2]) - max(b[0], kb[0])
            iy = min(b[3], kb[3]) - max(b[1], kb[1])
            if ix > 0 and iy > 0:
                inter = ix * iy
                if inter / ((b[2] - b[0]) * (b[3] - b[1])) > 0.55:
                    dup = True
                    break
        if not dup:
            kept.append(c)
    return kept


# --------------------------------------------------------------------------- render
def render(doc, page_no, crop, dpi, path):
    page = doc[page_no - 1]
    r = pymupdf.Rect(*crop)
    r = r & page.rect
    pix = page.get_pixmap(clip=r, dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    pix.save(path)
    return pix.width, pix.height


def render_preview(doc, page_no, boxes, dpi=100):
    from PIL import Image, ImageDraw
    page = doc[page_no - 1]
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    dr = ImageDraw.Draw(img)
    s = dpi / 72.0
    for b in boxes:
        x0, y0, x1, y1 = [v * s for v in b]
        dr.rectangle([x0, y0, x1, y1], outline=(220, 0, 0), width=3)
    dr.rectangle([0, 0, 150, 22], fill=(255, 255, 255))
    dr.text((6, 6), "page %d  boxes=%d" % (page_no, len(boxes)), fill=(200, 0, 0))
    path = os.path.join(PREVIEW_DIR, "p%02d.png" % page_no)
    img.save(path)
    return path


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--dpi-main", type=int, default=CFG["dpi_main"])
    ap.add_argument("--dpi-check", type=int, default=CFG["dpi_check"])
    a = ap.parse_args()

    ensure_dirs()
    logfile = os.path.join(LOG_DIR, "s1_detect.log")
    if os.path.exists(logfile):
        os.remove(logfile)
    log("STEP 1 - detect three-line tables", logfile)
    log("pdf: %s" % a.pdf, logfile)
    if not os.path.isfile(a.pdf):
        raise SystemExit("pdf not found")

    doc = pymupdf.open(a.pdf)
    log("pages: %d" % doc.page_count, logfile)

    all_cands, rejected, per_page_rules = [], [], {}
    for pno in range(1, doc.page_count + 1):
        page = doc[pno - 1]
        cands, rules = detect_page(page, CFG)
        per_page_rules[pno] = len(rules)
        kept = []
        page_rejected = []
        for c in dedupe(cands):
            ok, why = looks_like_table(c, CFG)
            c["_page"] = pno
            c["_why"] = why
            (kept if ok else page_rejected).append(c)
        all_cands.extend(kept)
        rejected.extend(page_rejected)
        log("  page %2d: rules=%4d  candidates=%d  tables=%d" % (
            pno, len(rules), len(cands), len(kept)), logfile)
        for c in page_rejected:
            log("        rejected p%02d y=%.0f..%.0f h=%.0f  %s" % (
                pno, c["box"][1], c["box"][3], c["h_pt"], c["_why"]), logfile)

    # reading order: page, then top to bottom
    all_cands.sort(key=lambda c: (c["_page"], c["box"][1]))

    tables = []
    for i, c in enumerate(all_cands, 1):
        t = tid(i)
        pno = c["_page"]
        name = "%s_p%02d" % (t, pno)
        c.pop("_page")
        c.pop("_why", None)
        c.update(id=t, name=name, page=pno,
                 long_table=bool(c["h_pt"] >= CFG["long_h_pt"] or c["n_text_rows"] >= CFG["long_rows"]),
                 img_a="img/%s_A.png" % name, img_b="img/%s_B.png" % name)
        pa = os.path.join(IMG_DIR, "%s_A.png" % name)
        pb = os.path.join(IMG_DIR, "%s_B.png" % name)
        c["px_a"] = list(render(doc, pno, c["crop"], a.dpi_main, pa))
        # verification copy: independent re-render at a different resolution
        doc2 = pymupdf.open(a.pdf)
        c["px_b"] = list(render(doc2, pno, c["crop"], a.dpi_check, pb))
        doc2.close()
        tables.append(c)
        log("  %s p%02d  %5.1f x %5.1f pt  rows~%2d  long=%s  A=%sx%s B=%sx%s" % (
            t, pno, c["w_pt"], c["h_pt"], c["n_text_rows"], c["long_table"],
            c["px_a"][0], c["px_a"][1], c["px_b"][0], c["px_b"][1]), logfile)

    for pno in range(1, doc.page_count + 1):
        boxes = [t["box"] for t in tables if t["page"] == pno]
        render_preview(doc, pno, boxes)

    meta = dict(pdf=os.path.abspath(a.pdf), n_pages=doc.page_count,
                dpi_main=a.dpi_main, dpi_check=a.dpi_check, cfg=CFG,
                rules_per_page=per_page_rules,
                n_candidates=len(tables) + len(rejected),
                n_rejected=len(rejected),
                rejected=[dict(page=r["_page"], box=r["box"], why=r["_why"]) for r in rejected],
                n_tables=len(tables),
                n_long=sum(1 for t in tables if t["long_table"]))
    save_json(dict(meta=meta, tables=tables), TABLES_JSON)
    doc.close()
    log("candidates=%d  tables kept=%d  (long: %d)  -> %s" % (
        meta["n_candidates"], meta["n_tables"], meta["n_long"], TABLES_JSON), logfile)
    log("images -> %s   previews -> %s" % (IMG_DIR, PREVIEW_DIR), logfile)


if __name__ == "__main__":
    main()
