# -*- coding: utf-8 -*-
"""
Table-region detection for RASTER pdfs (CNKI theses, scanned papers).

The three-line-table detector in s1 reads vector rules out of page.get_drawings().
That works for born-digital papers and finds nothing at all here: a CNKI thesis is a
300 dpi page scan with the tables printed inside it, so there are no rules to read.

This finds the tables in the pixels instead:
  1. render the page small and greyscale
  2. for every text row, measure the fraction of dark pixels
  3. a horizontal rule is a row whose dark fraction stays high across the text block
  4. rules belonging to one table are the ones close together vertically, so consecutive
     rules are grouped into bands and a band with enough rules and enough room between
     them for text is a table candidate

It is cheap (no OCR) and it is only the candidate stage: the candidates are rendered at
full resolution and OCR'd afterwards.

Usage:
    python src/cn_detect_tables.py "<pdf>" [--dpi 150] [--min-rule-frac 0.45]
                                       [--debug] [--out out/cn]
"""

import argparse
import json
import os
import sys

import numpy as np
import pymupdf
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ensure_dirs, log, save_json  # noqa: E402


def page_array(page, dpi):
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    return np.asarray(img, dtype=np.uint8)


def find_rules(arr, text_x0, text_x1, min_run_frac, min_thick, dens_gate=0.25):
    """
    Row indices that look like a horizontal rule, as (y0, y1) in pixels.

    Density alone is not enough here. A line of Chinese body text is dense enough to
    exceed 45% dark pixels across the text block, so the first version of this function
    reported every paragraph line as a rule and merged whole pages into one "table".
    What separates a rule from text is CONTINUITY: a rule is one unbroken dark run,
    text is a row of short glyph runs. So gate on the longest contiguous dark run.
    """
    a = arr[:, text_x0:text_x1]
    dark = (a < 128)
    width = text_x1 - text_x0
    need = int(min_run_frac * width)
    dens = dark.mean(axis=1)

    runs = []
    for y in np.where(dens >= dens_gate)[0]:
        row = dark[y]
        if row.all():
            runs.append((int(y), int(y)))
            continue
        d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1)
        if len(starts) == 0:
            continue
        # bridge 1px scanner dropouts, then take the longest surviving run
        best = int((ends - starts).max()) if len(starts) else 0
        if best >= need:
            runs.append((int(y), int(y)))
    if not runs:
        return []
    merged = [list(runs[0])]
    for r in runs[1:]:
        if r[0] - merged[-1][1] <= 1:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    return [(a, b) for a, b in merged if b - a + 1 >= min_thick]


def merge_close(runs, gap):
    if not runs:
        return []
    out = [list(runs[0])]
    for r in runs[1:]:
        if r[0] - out[-1][1] <= gap:
            out[-1][1] = r[1]
        else:
            out.append(list(r))
    return [tuple(r) for r in out]


def interior_gutters(arr, y0, y1, min_gutter_px, min_consistency, blank_thr=0.02):
    """
    Column gutters = blank vertical strips that stay blank down most rows.

    Two thresholds matter and the first version had both wrong.

    `blank_thr` is the share of rows allowed to have ink at an x before the strip stops
    counting as blank. Measured on p30 of the thesis: at 0.004 a real table shows ZERO
    blank strips - JPEG noise puts ink in 1-2 of 380 rows, which already exceeds 0.4% -
    while at 0.02 the same table shows 6 clean gutters with consistency 0.84-0.98, and a
    pure-prose block still shows none at any threshold up to 0.08. So 0.02 separates
    table from prose cleanly; a tighter threshold silently discards every real table.

    `min_consistency` then keeps only gutters sitting in the same x across rows, which is
    what stops a single line of CJK text (gaps between words) from looking tabular.

    Returns (n_gutters, [(x0, x1, consistency), ...]) in pixel x.
    """
    block = arr[y0:y1 + 1]
    rowink = (block < 128)
    rows = rowink.mean(axis=1) > 0.004
    nrows = int(rows.sum())
    if nrows < 3:
        return 0, []
    ink = rowink[rows].mean(axis=0)
    cols = np.where(ink > blank_thr)[0]
    if len(cols) < 2:
        return 0, []
    a, b = int(cols.min()), int(cols.max())
    blank = ink[a:b + 1] <= blank_thr
    out = []
    i = 0
    while i < len(blank):
        if not blank[i]:
            i += 1
            continue
        j = i
        while j < len(blank) and blank[j]:
            j += 1
        if j - i >= min_gutter_px:
            x0, x1 = a + i, a + j
            cons = float((~rowink[rows][:, x0:x1 + 1].any(axis=1)).sum()) / nrows
            if cons >= min_consistency:
                out.append((x0, x1, round(cons, 2)))
        i = j
    return len(out), out


def _sub_blocks(dark, split_gap_px, min_sub_px):
    """Split at blank line gaps. Only used for mixed regions - see candidates()."""
    cuts = [0]
    i = 0
    while i < len(dark):
        if dark[i]:
            i += 1
            continue
        j = i
        while j < len(dark) and not dark[j]:
            j += 1
        if j - i >= split_gap_px:
            cuts.append((i + j) // 2)
        i = j
    cuts.append(len(dark))
    out = []
    for k in range(len(cuts) - 1):
        a, b = cuts[k], cuts[k + 1]
        if b - a >= min_sub_px:
            out.append((a, b))
    return out


def _fragments_in(arr, y0, y1, s, page_no, kind, min_gutter_px, min_consistency,
                  min_rows_px):
    rowink = (arr[y0:y1 + 1] < 128)
    if int((rowink.mean(axis=1) > 0.004).sum()) < min_rows_px:
        return None
    ng, guts = interior_gutters(arr, y0, y1, min_gutter_px, min_consistency)
    if ng < 1:
        return None
    return dict(page=page_no, kind=kind, n_gutters=ng,
                gutters=[[int(g[0]), int(g[1])] for g in guts],
                y_top_px=int(y0), y_bot_px=int(y1))


def candidates(page_no, arr, rules, s, min_rows_px, min_frag_px, text_top, text_bot,
               split_gap_px, min_gutter_px, min_sub_px, min_consistency=0.6):
    """
    Fragments = the regions delimited by consecutive rules, filtered by the gutter test.

    Do NOT sub-split a rule-delimited region. The inter-row gap inside a table is about
    the same as the line gap in prose (10-15 px at 150 dpi here), so splitting on blank
    gaps shreds the table into single rows that then fail the height filter - that is
    exactly what happened on p30, whose table has 378 rows and produced zero fragments.
    The rules already delimit the table, so they are all that is needed.

    The region ABOVE the first rule is the exception: it is whatever came before the
    table, so it can be the tail of a previous table mixed with body text. That one is
    sub-divided with a deliberately large gap so paragraphs separate but table rows do
    not, and each piece is then tested on its own.
    """
    out = []
    bounds = [(text_top, rules[0][0], "above_first"),
              *[(rules[i][1], rules[i + 1][0], "between") for i in range(len(rules) - 1)],
              (rules[-1][1], text_bot, "below_last")]

    for (y0, y1, kind) in bounds:
        if y1 - y0 < min_frag_px:
            continue
        band = arr[y0:y1]
        dark = (band < 128).mean(axis=1) > 0.004
        rows = np.where(dark)[0]
        if len(rows) < min_rows_px:
            continue
        top = y0 + int(rows.min())
        bot = y0 + int(rows.max())

        f = _fragments_in(arr, top, bot, s, page_no, kind,
                          min_gutter_px, min_consistency, min_rows_px)
        if f:
            out.append(f)
            continue
        # mixed region: break it apart and test the pieces
        for a, b in _sub_blocks(dark, split_gap_px, min_sub_px):
            r2 = np.where(dark[a:b])[0]
            if len(r2) < min_rows_px:
                continue
            t2, b2 = y0 + a + int(r2.min()), y0 + a + int(r2.max())
            f2 = _fragments_in(arr, t2, b2, s, page_no, kind + "_part",
                               min_gutter_px, min_consistency, min_rows_px)
            if f2:
                out.append(f2)

    for x in out:
        x["y_top_pt"] = round(x["y_top_px"] / s, 1)
        x["y_bot_pt"] = round(x["y_bot_px"] / s, 1)
        x["height_pt"] = round((x["y_bot_px"] - x["y_top_px"]) / s, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--min-run-frac", type=float, default=0.55,
                    help="longest CONTIGUOUS dark run, as a share of the text width, "
                         "that counts as a rule (density alone is fooled by CJK text)")
    ap.add_argument("--min-thick", type=int, default=2, help="px")
    ap.add_argument("--merge-gap", type=int, default=3, help="px")
    ap.add_argument("--min-rows-px", type=int, default=4,
                    help="text lines a sub-block must hold")
    ap.add_argument("--min-frag-px", type=int, default=40)
    ap.add_argument("--split-gap-px", type=int, default=40,
                    help="blank height that separates paragraphs; must stay well above "
                         "the 10-15 px inter-row gap inside a table")
    ap.add_argument("--min-gutter-px", type=int, default=14,
                    help="blank vertical strip width that counts as a column gutter")
    ap.add_argument("--min-consistency", type=float, default=0.6,
                    help="share of rows a gutter must be blank on to be a column")
    ap.add_argument("--min-sub-px", type=int, default=110,
                    help="sub-block height in px - must span several lines, because a "
                         "single line of CJK text also has gaps and looks tabular")
    ap.add_argument("--pad-pt", type=float, default=4.0)
    ap.add_argument("--out", default=os.path.join("..", "out", "cn"))
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    outdir = os.path.abspath(a.out)
    os.makedirs(outdir, exist_ok=True)
    logf = os.path.join(outdir, "detect.log")
    if os.path.exists(logf):
        os.remove(logf)
    log("raster table detection (dpi=%d)" % a.dpi, logf)

    doc = pymupdf.open(a.pdf)
    s = a.dpi / 72.0
    allc = []
    for pno in range(1, doc.page_count + 1):
        page = doc[pno - 1]
        arr = page_array(page, a.dpi)
        # ignore the running head and the page number: use the widest dark band
        col = (arr < 128)
        rowfrac = col.mean(axis=1)
        body = np.where(rowfrac > 0.01)[0]
        if len(body) == 0:
            continue
        tx0 = int(col[:, body.min():body.max()].any(axis=0).argmax())
        tx1 = arr.shape[1] - int(col[:, body.min():body.max()].any(axis=0)[::-1].argmax())
        rules = merge_close(find_rules(arr, tx0, tx1, a.min_run_frac, a.min_thick),
                            a.merge_gap)
        if not rules:
            continue
        c = candidates(pno, arr, rules, s, a.min_rows_px, a.min_frag_px,
                        int(body.min()), int(body.max()),
                        a.split_gap_px, a.min_gutter_px, a.min_sub_px)
        if c:
            log("  p%-3d rules=%-3d frags=%-2d  %s" % (
                pno, len(rules), len(c),
                " | ".join("y%.0f-%.0f g%d" % (x["y_top_pt"], x["y_bot_pt"], x["n_gutters"])
                           for x in c[:5])), logf)
            allc.extend(c)

        if a.debug and c:
            from PIL import ImageDraw
            sc = a.dpi / 72.0
            img = Image.fromarray(arr).convert("RGB")
            d = ImageDraw.Draw(img)
            for r in rules:
                d.line([(tx0, r[0]), (tx1, r[0])], fill=(0, 160, 255), width=1)
            pad = int(a.pad_pt * sc)
            for x in c:
                d.rectangle([tx0, max(0, x["y_top_px"] - pad),
                             tx1, min(img.height - 1, x["y_bot_px"] + pad)],
                            outline=(255, 0, 0), width=2)
            img.save(os.path.join(outdir, "dbg_p%02d.png" % pno))

    doc.close()
    save_json(dict(pdf=os.path.abspath(a.pdf), dpi=a.dpi, n_candidates=len(allc),
                   candidates=allc), os.path.join(outdir, "candidates.json"))
    log("candidates: %d -> %s" % (len(allc), os.path.join(outdir, "candidates.json")), logf)


if __name__ == "__main__":
    main()
