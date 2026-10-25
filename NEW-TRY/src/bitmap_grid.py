# -*- coding: utf-8 -*-
"""
Turn bitmap-detected table fragments plus OCR boxes into a grid.

Why this exists
---------------
The vector route (s1..s5) only works when a PDF exposes its rules and glyphs at page
level. It handled paper 01 but produced zero tables for papers 02, 03, 05, 06 and 07 -
those were rejected with "median runs/row 2.0 < 3", because their glyphs live inside
Form XObjects and get_drawings() never sees them. Reading the rules out of the drawing
stream is therefore not optional; the only route that works for all of them is pixels.

The detector already solved the hard half
-----------------------------------------
cn_detect_tables.py finds the interior blank columns of each fragment and records them
as `gutters`, in page pixels at the detection dpi. Those gutters ARE the column
separators - they are derived from the rendered image, so they survive whatever the PDF
does internally, and they cost nothing to compute. So this script does not guess where
the columns are; it converts the gutters into the crop's coordinate frame and lets them
be the columns.

Coordinate conversion, which is where the earlier versions went wrong
--------------------------------------------------------------------
gutters are page px at detect dpi; OCR boxes are crop px at ocr dpi; the crop rect is
in pt. Converting a gutter takes both steps:

    pt = px * 72 / detect_dpi
    crop_px = (pt - rect.x0) * ocr_dpi / 72

Skipping either step lands the separators in the wrong place, and the symptom is
plausible-looking output rather than an error: cells split at the wrong x, so numbers
get cut in half.

Usage:
    python src/bitmap_grid.py --paper 2 --tag en
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REOUT = os.path.join(ROOT, "out", "re整理")

MISSING = {"", "-", "—", "–", "－", "/", "ND", "nd", "n.d", "未检出", "未检测到",
           "tr", "Tr", "TR", "nd.", "*", "―"}
VALUE_RE = re.compile(r"^[-−+]?\d[\d  ,]*(?:\.\d+)?"
                      r"(?:\s*±\s*\d[\d  ,]*(?:\.\d+)?)?"
                      r"\s*(?:[a-zA-Zμµ%／/·*\-]{0,6})?$")


def is_value(s):
    s = (s or "").strip()
    if not s or s in MISSING:
        return False
    if "±" in s:
        return True
    return bool(VALUE_RE.match(s))


def box_rect(b):
    pts = b.get("box") or []
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def clean(t):
    return re.sub(r"[ \t]*\n[ \t]*", " ", (t or "").replace("\xa0", " ")).strip()


def gutter_columns(gutters, rect, detect_dpi, ocr_dpi, crop_w, min_w=10.0):
    """Gutter x positions converted into the crop's pixel frame, as column separators."""
    k1 = 72.0 / float(detect_dpi)
    k2 = float(ocr_dpi) / 72.0
    seps = []
    for g in gutters or []:
        gx0, gx1 = (g + g) if isinstance(g, (int, float)) else (g[0], g[1])
        cx = (gx0 + gx1) / 2.0 * k1                 # page px -> pt
        cx = (cx - rect[0]) * k2                   # pt -> crop px
        if min_w < cx < crop_w - min_w:
            seps.append(cx)
    seps.sort()
    out = []
    for x in seps:
        if not out or x - out[-1] >= min_w:
            out.append(x)
    return out


def cluster_rows(items, tol_ratio=0.55):
    """Group boxes into text lines by y-centre."""
    if not items:
        return []
    hs = sorted(b[3] - b[1] for b in items)
    med = hs[len(hs) // 2] or 10.0
    tol = max(3.0, med * tol_ratio)
    items = sorted(items, key=lambda z: (z[1] + z[3]) / 2.0)
    rows, cur, cy = [], [], None
    for it in items:
        yc = (it[1] + it[3]) / 2.0
        if cy is None or abs(yc - cy) <= tol:
            cur.append(it)
            cy = sum((a[1] + a[3]) / 2.0 for a in cur) / len(cur)
        else:
            rows.append(cur)
            cur, cy = [it], yc
    if cur:
        rows.append(cur)
    return rows


def build_grid(boxes, seps, ncol):
    """
    Snap each box to a column.

    A row's boxes are split at large internal x gaps FIRST. The detector's gutters come
    from the blank columns wide enough to survive a pixel threshold, so a narrow gap
    between a short RI number and a long compound name is not among them; without this
    pass those two land in one cell and the fragment loses its name column entirely.
    Splitting on the gap the OCR boxes themselves reveal costs nothing and recovers it.
    """
    bounds = [0.0] + seps + [1e9]
    rows = cluster_rows(boxes)
    grid = []
    for ln in rows:
        ln = sorted(ln, key=lambda z: z[0])
        widths = sorted((b[2] - b[0]) for b in ln)
        med_w = widths[len(widths) // 2] if widths else 10.0
        gap_min = max(10.0, med_w * 1.1)
        cells = [""] * ncol
        for x0, y0, x1, y1, txt in ln:
            c = (x0 + x1) / 2.0
            k = 0
            while k < ncol - 1 and c >= bounds[k + 1]:
                k += 1
            cells[k] = (cells[k] + " " + txt).strip() if cells[k] else txt
        # the cell-level split above cannot create a new column, so when a row has more
        # occupied cells than ncol the extra ones are pushed into place by widening the
        # column set for that row - the cell boundaries the OCR gaps imply are real.
        occupied = [k for k in range(ncol) if cells[k]]
        if len(occupied) == ncol and ncol < len(ln):
            cells = [""] * 0
            bounds2 = [0.0]
            prev = None
            for x0, _y0, x1, _y1, _t in ln:
                if prev is not None and x0 - prev > gap_min:
                    bounds2.append((prev + x0) / 2.0)
                prev = max(prev or x1, x1)
            cells = [""] * (len(bounds2))
            for (x0, _y0, x1, _y1, txt), bi in zip(ln, _assign(ln, bounds2)):
                cells[bi] = (cells[bi] + " " + txt).strip() if cells[bi] else txt
            grid.append(cells)
            continue
        grid.append(cells)
    # rows built with the row-local fallback may be wider than ncol; pad the rest
    width = max((len(r) for r in grid), default=ncol)
    return [r + [""] * (width - len(r)) for r in grid]


def _assign(ln, bounds):
    n = len(bounds) - 1
    out = []
    for x0, _y0, x1, _y1, _t in ln:
        c = (x0 + x1) / 2.0
        k = 0
        while k < n - 1 and c >= bounds[k + 1]:
            k += 1
        out.append(k)
    return out


def row_is_data(row, frac=0.25):
    """
    Is this row a measurement row?

    Requiring ANY numeric cell is too weak: a header row picks up a stray digit from
    the vertical margin text or from a footnote marker, and one stray digit turns the
    labels of the table into its first data row. A measurement row has most of its
    filled cells numeric, so the test is a share rather than an existence.
    """
    filled = [c for c in row if (c or "").strip()]
    if len(filled) < 2:
        return False
    return sum(1 for c in filled if is_value(c)) / len(filled) >= frac


def header_split(grid, ncol=0, max_head=4):
    """
    The header is the leading run of rows carrying no measurement.

    A group header can be two or three lines tall (a unit line, a sample line, then the
    labels), so the cut is content-driven rather than "first row only".

    Rows must also be WIDE to count as either header or data. Spreading a header
    fragment's boxes across a wide table's columns scatters the running head - journal
    title left, page number right - into three separate cells, and three filled cells
    holding one digit is a third numeric, which reads as a measurement row and stops the
    promotion dead. A real header row of an n-column table fills a good share of it, so
    the width test is scaled to ncol rather than fixed at three.
    """
    wide = max(3, int(ncol * 0.25))
    start = 0
    while start < len(grid) - 2 and sum(1 for c in grid[start] if c.strip()) < wide:
        start += 1
    cut = start
    while cut < min(start + max_head, len(grid) - 2) and not row_is_data(grid[cut]):
        cut += 1
    return cut, start


def _to_page_x(x, rect, dpi):
    return rect[0] + x / float(dpi) * 72.0


def _to_page_y(y, rect, dpi):
    return rect[1] + y / float(dpi) * 72.0


def med_h(bs):
    hs = sorted(b[3] - b[1] for b in bs)
    return hs[len(hs) // 2] or 10.0


def merge_wrapped_rows(items, seps, ncol):
    """
    Re-cut the rows on an anchor column instead of on text baselines.

    The problem
    -----------
    A cell that wraps onto two lines puts its second line below the first, while the
    value sitting in the same logical row is vertically CENTRED between them. Splitting
    on y alone then gives one compound three rows: the first line of its name, then its
    value, then its second line of name. In the PCA ester table of #27 that reads as

        1341 | 己酸-2-甲基丙酯 |          | MS,RIL, |
      1357 |                 | 果香、甜香 |          |  64 | 4 | 4
            | (己酸异丁酯    |          | Aroma    |

    which is why a perfectly correct name came to be reported as a possible typo.

    How the anchor is chosen
    -----------------------
    The anchor is the column that behaves like one value per row: the fewest boxes,
    spaced widely relative to the text height. On that table the compound-name column has
    26 boxes with a median gap of 110 px, while the identification-method column has 50
    boxes at 53 px - half a row apart, which is a wrapped cell, not an anchor. Counting
    rows per column is what distinguishes them; a pure y-clustering cannot, because both
    columns look like ordinary text lines.

    Every box is then attached to the nearest anchor, so a two-line name and the value
    beside it land on the same row no matter how many lines either uses.
    """
    bounds = [0.0] + seps + [1e9]

    def col_of(b):
        c = 0
        mid = (b[0] + b[2]) / 2.0
        while c < ncol - 1 and mid >= bounds[c + 1]:
            c += 1
        return c

    per_col = {}
    for b in items:
        per_col.setdefault(col_of(b), []).append(b)

    best = None
    best_uniform = False
    for c, bs in per_col.items():
        if len(bs) < 3:
            continue
        ys = sorted((b[1] + b[3]) / 2.0 for b in bs)
        gaps = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
        if not gaps:
            continue
        med = sorted(gaps)[len(gaps) // 2]
        # An anchor column carries one value per row, so its boxes are sparse AND
        # regularly spaced. Insisting on regularity is what stops a column that has gaps
        # in it - a concentration column where some samples read ND - from being chosen:
        # that column would merge two rows onto one anchor and put two compounds on a
        # single line, which is a worse error than the wrapping it was meant to fix.
        if med <= 1.6 * med_h(bs):
            continue
        uniform = (max(gaps) / med) < 1.8
        if best is None:
            best, best_uniform = c, uniform
        elif uniform and not best_uniform:
            best, best_uniform = c, True
        elif uniform == best_uniform and len(bs) < len(per_col[best]):
            best = c
    if best is None:
        return None

    anchors = sorted((b[1] + b[3]) / 2.0 for b in per_col[best])
    if len(anchors) < 2:
        return None

    grid = [[] for _ in anchors]
    for b in items:
        yc = (b[1] + b[3]) / 2.0
        k = min(range(len(anchors)), key=lambda i: abs(anchors[i] - yc))
        grid[k].append(b)

    out = []
    for ln in grid:
        if not ln:
            out.append([""] * ncol)
            continue
        cells = [""] * ncol
        for b in sorted(ln, key=lambda z: z[0]):
            c = col_of(b)
            cells[c] = (cells[c] + " " + b[4]).strip() if cells[c] else b[4]
        out.append(cells)
    return out, best


def merge_continuation_rows(grid, ncol):
    """
    Join a row whose last cell ends in a hyphen onto the row below it.

    A name too long for its column is broken mid-word and the hyphen kept, so the row
    ends in "-" and the rest of the name is the first cell of the next row:

        2,3-Diethyl-5-      1472   2.03
        methylpyrazine

    The anchor-column cut cannot help here: these tables have too few columns for it to
    find an anchor (T03 in #10 is two columns wide), yet the tell is unambiguous in the
    text itself. Only the FIRST cell is used to decide, because in a value column a
    trailing hyphen is arithmetic, not a broken word.
    """
    out, i = [], 0
    merged = 0
    while i < len(grid):
        row = list(grid[i])
        if i + 1 < len(grid):
            # Find the NAME cell: the first one containing letters. Column 0 is the row
            # number in these tables, and it is a digit, so "the first non-empty cell"
            # lands on "3" and never matches a trailing hyphen.
            tc = None
            for c in range(ncol):
                if c >= len(row):
                    break
                v = (row[c] or "").strip()
                if v and re.search(r"[A-Za-z一-鿿]", v):
                    tc = c
                    break
            head = (row[tc] or "").strip() if tc is not None else ""
            if head.endswith(("-", "‐", "‑", "－")) and len(head) >= 3:
                nxt = list(grid[i + 1])
                if tc < len(row) and tc < len(nxt):
                    row[tc] = (head + (nxt[tc] or "")).strip()
                for c in range(ncol):
                    cur = row[c] if c < len(row) else ""
                    nxt_c = nxt[c] if c < len(nxt) else ""
                    if not (cur or "").strip() and (nxt_c or "").strip():
                        if c < len(row):
                            row[c] = nxt_c
                        else:
                            row.append(nxt_c)
                merged += 1
                out.append(row)
                i += 2
                continue
        out.append(row)
        i += 1
    return out, merged


def drop_orphan_rows(grid, ncol):
    """
    Drop rows that carry a single stray fragment and nothing else.

    These come from a wrapped cell whose remainder was OCR'd as one character ("s" in
    T03 of #10) or a lone word with no measurement beside it. A row is only removed when
    EVERY other cell is empty, so a compound reported with ND across the board - a real
    and meaningful row - is kept.
    """
    out = []
    for r in grid:
        vals = [(x or "").strip() for x in r]
        if not any(vals):
            continue
        filled = [v for v in vals if v]
        head = vals[0] if vals else ""
        if len(filled) == 1 and head and len(head) <= 2:
            continue
        if not head and len(filled) == 1:
            continue
        out.append(r)
    return out, len(grid) - len(out)


def tabular_row_count(grid):
    """Rows wide enough to be table rows - three or more filled cells.

    This, not "does the row contain a number", is what separates a data fragment from a
    header fragment. A header-only fragment still contains digits - the page number, the
    "R2" of an R-squared column, a stray "2" - but its boxes collapse into one or two
    cells because they are captions spanning the table, not a row of columns.
    """
    return sum(1 for r in grid if sum(1 for c in r if c.strip()) >= 3)


def convert(paper, cand_path, ocr_path, dpi, out_tag):
    cand = json.load(open(cand_path, encoding="utf-8"))
    ocr = json.load(open(ocr_path, encoding="utf-8"))
    det_dpi = cand.get("dpi", 150)
    by_page = {}
    for c in cand["candidates"]:
        by_page.setdefault(c["page"], []).append(c)

    # stage 1: geometry and boxes, in page coordinates
    staged = []
    skipped = []
    for t in ocr["tables"]:
        page = t["page"]
        rect = t["rect"]
        best, bestov = None, 0.0
        for c in by_page.get(page, []):
            ov = min(c["y_bot_pt"], rect[3]) - max(c["y_top_pt"], rect[1])
            if ov > bestov:
                best, bestov = c, ov
        if best is None:
            skipped.append((t.get("id"), "no candidate"))
            continue
        crop_w = max(1, int((rect[2] - rect[0]) * dpi / 72.0))
        seps = gutter_columns(best.get("gutters"), rect, det_dpi, dpi, crop_w)
        if len(seps) + 1 < 2:
            skipped.append((t.get("id"), "no gutters"))
            continue
        items = []
        for b in (t.get("passA") or {}).get("boxes", []):
            r = box_rect(b)
            if not r:
                continue
            txt = clean(b.get("text"))
            if txt:
                items.append((r[0], r[1], r[2], r[3], txt))
        if len(items) < 3:
            skipped.append((t.get("id"), "too few boxes"))
            continue
        bounds = [0.0] + seps + [crop_w]
        staged.append(dict(
            id=t.get("id"), page=page, rect=rect, y_top=rect[1], y_bot=rect[3],
            bounds_page=[_to_page_x(x, rect, dpi) for x in bounds],
            n_col=len(bounds) - 1, n_boxes=len(items),
            items_page=[(_to_page_x(i[0], rect, dpi), _to_page_y(i[1], rect, dpi),
                         _to_page_x(i[2], rect, dpi), _to_page_y(i[3], rect, dpi), i[4])
                        for i in items],
            grid_own=build_grid(items, seps, len(bounds) - 1),
        ))

    # stage 2: a header separated from its body by a rule arrives as its own fragment.
    # A fragment that is not wide enough to be a data fragment is still emitted on its
    # own (it may be a small table of categories that would otherwise vanish) AND its
    # boxes are buffered so the next data fragment on the same page gets its labels.
    # Doing both is deliberate: buffering alone loses those small tables, emitting
    # alone leaves every table below the first one without any header at all.
    tables = []

    def emit(f, extra_items):
        items = extra_items + f["items_page"]
        grid = build_grid(items, f["bounds_page"], f["n_col"])
        # Re-cut on an anchor column when the plain y-clustering has clearly shredded
        # wrapped cells. The test is that the anchor version yields fewer rows AND they
        # are fuller - a table without wrapping is left on the original path, so this
        # cannot fire on tables that were already correct.
        anchored = merge_wrapped_rows(items, f["bounds_page"], f["n_col"])
        if anchored is not None:
            ag, acol = anchored
            old_full = sum(1 for r in grid if sum(1 for c in r if c.strip()) >= 3)
            new_full = sum(1 for r in ag if sum(1 for c in r if c.strip()) >= 3)
            # Wrapping shows up as far more y-clusters than logical rows. When the anchor
            # cut yields markedly fewer rows AND does not lose filled rows, it is the
            # correct reading; a table without wrapping simply fails the first test and
            # keeps the original grid.
            if len(ag) * 1.4 < len(grid) and new_full >= old_full * 0.8:
                grid = ag
                f.setdefault("notes", []).append(
                    "re-cut on anchor col %d: %d y-clusters -> %d rows"
                    % (acol, len(grid), len(ag)))
        cut, start = header_split(grid, f["n_col"])
        body, n_cont = merge_continuation_rows(grid[cut:], f["n_col"])
        body, n_orph = drop_orphan_rows(body, f["n_col"])
        if n_cont:
            f.setdefault("notes", []).append("merged %d hyphen-continued names" % n_cont)
        rows = [r for r in body if sum(1 for c in r if c.strip()) >= 2]
        if len(rows) < 2:
            skipped.append((f["id"], "only %d data rows" % len(rows)))
            return
        tables.append(dict(
            caption="", note="", header_rows=grid[start:cut], rows=rows,
            n_row=len(rows), n_col=f["n_col"], pages=[f["page"]], src_id=f["id"],
            verify=dict(n_gutters=f["n_col"] - 1, n_boxes=f["n_boxes"]),
            has_values=any(any(is_value(c) for c in r) for r in rows),
        ))

    for page in sorted({f["page"] for f in staged}):
        fs = sorted([f for f in staged if f["page"] == page], key=lambda z: z["y_top"])
        pending = []
        for f in fs:
            wide = tabular_row_count(f["grid_own"])
            if wide >= 2:
                emit(f, pending)
                pending = []
            elif wide >= 1 or len(f["grid_own"]) >= 3:
                emit(f, [])
                pending.extend(f["items_page"])
            else:
                pending.extend(f["items_page"])

    tables.sort(key=lambda z: (z["pages"][0], -z["n_row"]))
    return tables, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=int, required=True)
    ap.add_argument("--cand", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--outdir", default=REOUT)
    ap.add_argument("--tag", default="bm")
    a = ap.parse_args()

    tables, skipped = convert(a.paper, a.cand, a.ocr, a.dpi, a.tag)
    fn = os.path.join(a.outdir, "%s_%02d.json" % (a.tag, a.paper))
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(dict(idx=a.paper, route="bitmap" if tables else "bitmap-empty",
                       note="; ".join("%s:%s" % s for s in skipped[:6]),
                       tables=tables), f, ensure_ascii=False, indent=1)
    rows = sum(t["n_row"] for t in tables)
    print("  #%-3d tables=%-3d rows=%-5d  skipped=%-3d %s"
          % (a.paper, len(tables), rows, len(skipped),
             "; ".join("%s:%s" % s for s in skipped[:4])))
    print("  -> %s" % fn)


if __name__ == "__main__":
    main()
