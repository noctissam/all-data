# -*- coding: utf-8 -*-
"""
Rebuild bitmap-route tables from their OCR boxes.

The bitmap route is the weakest of the four: one OCR pass, no second opinion, and a grid
that decides how many columns the table has before looking at where the text actually is.
Two failures follow, and both are visible in the box data rather than in the extraction:

  merged cells   T09 of the 沂蒙 paper is six columns wide and the grid built five:
                 "19.62±1.73a" sits at x 1199-1415 and "18.06±2.69a" at x 1476-1690 - two
                 separate boxes, 61px apart - and they were written into one cell as
                 "19.62±1.73a 18.06±2.69a". A number with two standard deviations in one
                 cell is not a number, and the clean table has nowhere to put it.
  lost headers   the header of a continued table lives in the previous crop, so the grid
                 has nothing to name the columns with and they come out as 列N.

Rebuilding from the boxes fixes the first directly: cluster x, and every box lands in its
own column. Columns with no header are then filled from the header row of whichever crop in
the same paper carries the table's column names.

Only tables that actually show one of the two faults are touched. Everything else in the
bitmap route is left exactly as it was, because a table that is already right does not need
a second opinion from a script.

Usage:
    python src/repair_bitmap.py --dry-run
    python src/repair_bitmap.py --apply
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

HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.join(HERE, "..", "out", "re整理")

spec = importlib.util.spec_from_file_location(
    "builder", os.path.join(HERE, "build_rec整理.py"))
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

# A gutter between two columns. The boxes are one text line each, so a column holds exactly
# one box per row and any gap at all is a column boundary. Measured across the corpus the
# tightest real gutter is ~30px at 300dpi, so this sits well clear of it.
GUTTER = 18.0
ROW_TOL = 14.0
# Below this the OCR is reading the crop edge; these boxes are fragments of the neighbouring
# page and have been landing in the table as "众LH" and "LIH".
MIN_SCORE = 0.80
MIN_Y = 0.0
# A score floor alone cannot separate the two kinds of low-confidence box. In one table the
# scores split cleanly: p5=0.953, median 1.000, and the only four boxes under 0.80 are two real
# cells and two pieces of OCR garbage that happen to score the same -
#
#   0.727  "S58"    real internal-standard code
#   0.697  "110k"   real
#   0.728  "ivivyy"  noise
#   0.579  "puNJ.atJ.viy/aLJiuuuJuitctii"  page watermark
#
# The shape separates them where the score cannot. A short or digit-bearing token is a code the
# table is entitled to carry, so it survives down to LOW_SCORE; free-form letters need the full
# MIN_SCORE. Both of these columns (SSb / 389i / 3150m / 400c / 13,200l) are data, not labels,
# and dropping them silently emptied a real column.
MIN_SCORE_LOW = 0.60


def _credible(txt, score):
    if score >= MIN_SCORE:
        return True
    if score < MIN_SCORE_LOW:
        return False
    return any(ch.isdigit() for ch in txt) or len(txt) <= 4

# Headers read off a rendered page, for tables whose real header lives on another page AND whose
# columns cannot be lined up with it geometrically. Listed rather than filled in silently, and
# each entry records where it was read so it can be checked against the PDF.
#
#   ("32", "T15")  the acid table on p33 continues the one whose header sits at the top of p32,
#                  but p32's table carries an extra category column (醇类 / 酯类 / 酸类化合物)
#                  that shifts every centre: this table's columns sit at x 189/1007/1371/1619/1878
#                  against 200/378/928/1306/1610/1850, i.e. 79px and 65px out on two columns,
#                  past the 64px tolerance. Read off p32 at 3.2x and checked against the data -
#                  152466.77 / 200000 = 0.76 confirms 阈值, 浓度, OAV in that order.
VERIFIED_HEADERS = {
    ("32", "T15"): (["物质名称", "阈值（μg/L)", "二锅头（μg/L)", "OAV值", "量比关系"],
                    "第32页表头行（续表，几何对齐失败）"),
}


def load_boxes(idx):
    p = os.path.join(HERE, "..", "out", "bm%02d" % idx, "ocr_raw.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf-8"))
    out = {}
    for t in d.get("tables", []):
        boxes = (t.get("passA") or {}).get("boxes") or []
        keep = []
        for bx in boxes:
            txt = (bx.get("text") or "").strip()
            if not txt or not _credible(txt, float(bx.get("score", 0))):
                continue
            xs = [p[0] for p in bx["box"]]
            ys = [p[1] for p in bx["box"]]
            cy = sum(ys) / len(ys)
            if cy < MIN_Y:
                continue
            keep.append((min(xs), max(xs), cy, txt))
        out[t.get("id")] = keep
        boxes_page[t.get("id")] = t.get("page")
    return out


def cluster_columns(items):
    """Split by x: sort by left edge, start a new column at every gap wider than a gutter.

    Boxes far wider than the median are excluded first. A caption or banner is one box that
    reaches across several columns, and because it is chained in by the gap rule it welds those
    columns into a single range wider than the table. Keeping it also drags every box into the
    row anchor once assignment is by overlap, which turns 35 rows into 213. The wide boxes are
    still placed afterwards - by overlap with whatever columns survive.
    """
    if not items:
        return []
    widths = sorted(b[1] - b[0] for b in items)
    med = widths[len(widths) // 2] or 1.0
    cap = max(3.0 * med, 400.0)
    core = [b for b in items if (b[1] - b[0]) <= cap] or items
    core = sorted(core, key=lambda r: r[0])
    cols = [[core[0]]]
    for it in core[1:]:
        if it[0] - cols[-1][-1][1] > GUTTER:
            cols.append([it])
        else:
            cols[-1].append(it)
    return cols


def build_grid(items):
    """
    items: (x0, x1, cy, text). Returns rows of cells, one column per x cluster.

    Rows are anchored on the LEFTMOST column rather than clustered on y. Cells that wrap put
    two lines 53px apart in a table whose rows are 107px apart, so a y threshold either splits
    one row into three or merges three rows into one - the margin between "inside a cell" and
    "between rows" is 2px here. The leftmost column holds a row number or a name on one line
    every row, which gives an unambiguous anchor to assign everything else against.
    """
    if not items:
        return []
    cols = cluster_columns(items)
    ncol = len(cols)
    lefts = [min(c[i][0] for i in range(len(c))) for c in cols]

    def provisional(x0, x1):
        mid = (x0 + x1) / 2.0
        return min(range(ncol), key=lambda k: abs(lefts[k] - mid))

    anchors = sorted(b[2] for b in items if provisional(b[0], b[1]) == 0)
    if len(anchors) < 2:
        anchors = sorted(b[2] for b in items)

    # A box belongs to whichever column's x RANGE it overlaps most, not to the nearest left
    # edge. The two disagree exactly where it costs data: "50" (539-590, mid 564) is 137px from
    # column 1's left edge at 427 but only 123px from column 2's at 688, so nearest-edge files
    # it one column right and the row reads "50 571.95".
    sp = [(min(c[i][0] for i in range(len(c))), max(c[i][1] for i in range(len(c))))
          for c in cols]

    def colof(x0, x1):
        best, bestk = 0.0, 0
        for k, (lo, hi) in enumerate(sp):
            ov = min(x1, hi) - max(x0, lo)
            if ov > best:
                best, bestk = ov, k
        if best > 0:
            return bestk
        return min(range(ncol), key=lambda k: max(sp[k][0] - x1, x0 - sp[k][1], 0))

    rows = {}
    for x0, x1, cy, txt in items:
        k = min(range(len(anchors)), key=lambda i: abs(anchors[i] - cy))
        cell = rows.setdefault(k, {})
        c = colof(x0, x1)
        cell[c] = (cell[c] + " " + txt) if c in cell else txt
    return [[rows[k].get(c, "") for c in range(ncol)] for k in sorted(rows)]


def header_split(rows):
    """
    Split a rebuilt grid into header rows and body rows.

    A header names things and measures nothing, so the test is that it contains NO number at
    all - not "mostly labels". The looser test was tried and it promoted a measurement row to
    a header on four tables, because these papers mark significance with a degree sign and
    with asterisks, and "83.58±3.24°" is not a number to a regex that only allowed letters.
    Promoting it dropped the first compound of each of those tables.

    Most bitmap crops do not contain the header at all - the table continues from the
    previous page - and for those this correctly returns no header and leaves the columns
    unnamed rather than inventing names for them.
    """
    hdr, body, seen_data = [], [], False
    for r in rows:
        filled = [c for c in r if c.strip()]
        if not filled:
            continue
        if seen_data:
            body.append(r)
            continue
        if any(B.NUMBERISH.match(c.strip()) for c in filled):
            seen_data = True
            body.append(r)
            continue
        hdr.append(r)
    return hdr, body


def merged_count(rows, ncol):
    """Cells holding more than one measurement - the fault this pass exists to fix."""
    n = 0
    for r in rows:
        for c in r:
            t = str(c or "").strip()
            if len(re.findall(r"\d+\.?\d*\s*±", t)) > 1:
                n += 1
    return n


def unnamed_cols(t):
    try:
        info = B.classify_columns(t)
    except Exception:
        return []
    return [c for c, _u in info["data_cols"]
            if B.sample_label(t, c, 0, info.get("hdr_rows")).startswith("列")]


def _center(it):
    return (it[0] + it[1]) / 2.0


def _looks_numeric(txt):
    return bool(B.NUMBERISH.match(str(txt or "").strip()))


def find_header(col_centers, boxes_by_id, page, data_texts, tol=64.0):
    """
    Find this table's column names in another crop of the same paper.

    A table that runs over a page break has its header on the first page and none of the
    continuation, so the grid has nothing to name the columns with. But the columns are still
    there, at the same x positions: 附表 of the 沂蒙 paper names its columns 物质名称 / 一级好酒
    / 一级差酒 / 二级好酒 / 二级差酒 / 三级酒 in one crop, and the continuation crops put their
    measurements at exactly those x positions.

    Four refusals, each added after it attached the wrong thing. A wrong header is worse than
    no header: it names a column confidently and wrongly, where 列N at least admits ignorance.

      same page only      the papers carry several tables with the same column layout a few
                          pages apart; picking one across six pages attached another table's
                          header (RI / 物质名称 / 香气描述 / 鉴定方式) to a table whose columns
                          are 一级好酒 / 一级差酒 / ...
      no data values      a measurement row was being taken for a header row, so 1-Butanol
                          and 乙酸乙酯 turned up as column names
      no compound names   a column headed by a substance is a data row however label-like
                          the text is
    """
    def ok(txt):
        t = str(txt or "").strip()
        if not t or _looks_numeric(t):
            return False
        if t in data_texts:
            return False
        if B.looks_like_compound(t):
            return False
        return True

    best_line, best_hit = None, 0
    for tid, items in boxes_by_id.items():
        pg = boxes_page.get(tid)
        if pg is not None and page is not None and abs(pg - page) > 1:
            continue
        lines = {}
        for it in items:
            lines.setdefault(round(it[2] / ROW_TOL), []).append(it)
        for key in sorted(lines):
            ws = lines[key]
            if len(ws) < 3 or not all(ok(w[3]) for w in ws):
                continue
            ws = sorted(ws, key=lambda w: w[0])
            hit, used = 0, set()
            for c in col_centers:
                k = min(range(len(ws)), key=lambda i: abs(_center(ws[i]) - c))
                if abs(_center(ws[k]) - c) <= tol and k not in used:
                    used.add(k)
                    hit += 1
            if hit > best_hit:
                best_line, best_hit = (tid, key, ws), hit
    if best_line is None or best_hit < 3:
        return None, None
    tid, key, ws = best_line

    head = {}
    for w in ws:
        c = min(range(len(col_centers)), key=lambda i: abs(col_centers[i] - _center(w)))
        if abs(col_centers[c] - _center(w)) <= tol and c not in head:
            head[c] = w[3]
    # Columns the main line did not name take the first label ABOVE it, in the SAME crop.
    # Scanning every crop of the paper instead reached into another table's data rows and
    # put 醇类 - a category, not a column - in the name column's header.
    for tid2 in [tid]:
        items = boxes_by_id[tid2]
        lines = {}
        for it in items:
            if it[2] / ROW_TOL >= key:
                continue
            lines.setdefault(round(it[2] / ROW_TOL), []).append(it)
        for k2 in sorted(lines, reverse=True):
            for w in lines[k2]:
                if not ok(w[3]):
                    continue
                c = min(range(len(col_centers)),
                        key=lambda i: abs(col_centers[i] - _center(w)))
                if abs(col_centers[c] - _center(w)) <= tol and c not in head:
                    head[c] = w[3]
            if len(head) == len(col_centers):
                break
        if len(head) == len(col_centers):
            break
    if len(head) < 2:
        return None, None
    return [head.get(i, "") for i in range(len(col_centers))], tid


boxes_page = {}


def _first(row):
    for c in row:
        if str(c or "").strip():
            return str(c).strip()
    return ""


def _nfill(row):
    return sum(1 for c in row if str(c or "").strip())


def _meas_count(cell):
    """
    How many measurements a single cell holds.

    Counted by whitespace-separated tokens, because that is how the grid merged them:
    "3337.10 1875.00", "7.293 0.9901", "256 256", "0.76 0.2047", "19.62±1.73a
    18.06±2.69a". A cell that is at least one measurement AND carries other text is counted
    by its token count, which covers the category rows where the class name was written into
    the same cell as its value ("酯类 637.85±219.87a").

    A cell with no measurement in it is never a merge: a CAS ("108-64-5"), a solvent note
    ("46% ethanol/ water solution") and "MS,RIL, Aroma" all stay at zero, which is what stops
    the rebuild being licensed to invent a column out of them.
    """
    t = str(cell or "").strip()
    if not t:
        return 0
    toks = [x.strip() for x in t.split() if x.strip()]
    meas = sum(1 for tok in toks
               if re.match(r"^<?\d+\.?\d*$", tok) or re.match(r"^<?\d+\.?\d*\s*±", tok))
    return len(toks) if meas else 0


def _merge_slack(row):
    """
    How many extra filled cells this row is allowed to gain.

    A cell holding k measurements can legitimately split into k columns, adding k-1 filled
    cells. Everything else a rebuild produces is content it invented - which is exactly what
    happened to T22, where the crop holds no header of its own and the neighbouring crop's
    header boxes got attached to the first data row.
    """
    return sum(max(0, _meas_count(c) - 1) for c in row)


def rebuild_is_sound(old_rows, new_rows):
    """
    Accept the rebuild only where it can be shown to lose nothing and add nothing.

    Two real failures motivated this. T08 lost two of its seven rows to a bad row anchor, and
    T22 gained four cells per row that no merged cell in the original could account for.
    Both looked fine in the row count alone.
    """
    if len(new_rows) < len(old_rows):
        return False, "重建后行数变少 %d->%d" % (len(old_rows), len(new_rows))
    # The other direction matters just as much. Splitting wrapped cells legitimately adds a few
    # rows (27->32 here), but a row count that explodes means the row anchor broke and one
    # physical row is being counted many times over.
    if len(new_rows) > len(old_rows) * 2 + 4:
        return False, "重建后行数暴涨 %d->%d，行锚定已失效" % (len(old_rows), len(new_rows))
    new_firsts = [_first(r) for r in new_rows]
    unmatched, corrected = [], []
    for o in old_rows:
        k = _first(o)
        if not k:
            continue
        # the first cell itself may have been a merged name+value ("酯类 637.85±219.87a"),
        # so match on containment rather than equality
        cands = [r for r, f in zip(new_rows, new_firsts) if f and (f in k or k in f)]
        if not cands:
            unmatched.append(k)
            continue
        if _nfill(o) + _merge_slack(o) < min(_nfill(c) for c in cands):
            return False, "首格 %r 的行多出了无法用并格解释的内容" % k[:20]
    # A row whose leading cell the rebuild spells differently is usually the rebuild reading
    # it correctly: the bitmap route turned the category row 醛类 into 已醛 and then inserted a
    # phantom empty column beside it. Refusing every such row would keep the OCR error. But
    # allowing any number of them would let a rebuild quietly drop a whole table, so the
    # tolerance is small and every correction is reported.
    tol = max(2, int(len(old_rows) * 0.08))
    if len(unmatched) > tol:
        return False, ("有 %d 行的首格对不上（容差 %d）：%s"
                       % (len(unmatched), tol, "、".join(x[:12] for x in unmatched[:4])))
    corrected = unmatched
    note = "无损"
    if corrected:
        note = "并更正了 %d 处 OCR 首格：%s" % (len(corrected),
                                          "、".join(x[:12] for x in corrected[:4]))
    return True, note


def resolve_crop(t, boxes, boxes_page):
    """
    Which OCR crop produced this table.

    Normally the table records the crop's own id. That breaks when the OCR was re-run: the
    candidate set changes, every id shifts, and the recorded id can point at a DIFFERENT
    crop that happens to exist. That is the dangerous case - the id resolves, so nothing
    complains, and the table gets rebuilt from a neighbouring page's numbers. The page is
    therefore checked as well as the id.

    A page carries one table in most of these papers; when it carries several there is no way
    to tell which one this is, so that is refused rather than guessed.
    """
    sid = t.get("src_id")
    pg = (t.get("pages") or [None])[0]
    if pg is None:
        return None, "无页码"
    if sid in boxes and boxes_page.get(sid) == pg:
        return sid, "src_id"
    same = [tid for tid in boxes_page if boxes_page[tid] == pg]
    if len(same) == 1:
        why = "src_id=%s 指向第%s页而非第%s页" % (sid, boxes_page.get(sid), pg) if sid in boxes \
            else "src_id=%s 不存在" % sid
        return same[0], "按页码匹配 %s（%s）" % (pg, why)
    return None, "src_id=%s 与页码不符，且第%s页有 %d 个裁剪，不敢猜" % (sid, pg, len(same))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    report = []
    changed = 0
    for f in sorted(glob.glob(os.path.join(REOUT, "bm_*.json"))):
        if ".orig." in f:
            continue
        idx = int(os.path.basename(f)[3:5])
        boxes = load_boxes(idx)
        if boxes is None:
            continue
        d = json.load(open(f, encoding="utf-8"))
        dirty = False
        for ti, t in enumerate(d.get("tables") or []):
            tg = unnamed_cols(t)
            before = merged_count(t.get("rows") or [], t.get("n_col") or 0)
            if not tg and not before:
                continue
            src, how = resolve_crop(t, boxes, boxes_page)
            items = boxes.get(src) if src else None
            if not items:
                report.append("bm_%02d t%-2d %s  字框缺失，无法重建"
                              % (idx, ti, how))
                continue
            grid = build_grid(items)
            if not grid:
                continue
            hdr, body = header_split(grid)
            if len(body) < 2:
                report.append("bm_%02d t%-2d %s  重建后只剩 %d 行数据，放弃"
                              % (idx, ti, src, len(body)))
                continue
            ok, why = rebuild_is_sound(t.get("rows") or [], body)
            if not ok:
                report.append("bm_%02d t%-2d %s  拒绝重建：%s（并格 %d，仍未修）"
                              % (idx, ti, src, why, before))
                continue
            if why != "无损":
                report.append("     %s：%s" % (src, why))
            after = merged_count(body, len(grid[0]))
            note = ""
            # A header row holding a single label (酸类化合物, the section heading repeated at
            # the top of a continuation page) names no columns at all, so it counts as no
            # header and the search still runs.
            if grid and (not hdr or
                         sum(1 for r in hdr for c in r if str(c or "").strip()) < 2):
                centers = cluster_columns(items)
                # column CENTRES, not left edges: a header label is centred over its column,
                # so matching its centre against the column's left edge put every label 40-90px
                # out and nothing ever matched
                ctr = [(min(c[i][0] for i in range(len(c)))
                        + max(c[i][1] for i in range(len(c)))) / 2.0 for c in centers]
                seen_txt = {str(c).strip() for r in body for c in r
                            if str(c or "").strip()}
                pg = (t.get("pages") or [None])[0]
                heads, src2 = find_header(ctr, boxes, pg, seen_txt)
                note = ""
                if heads:
                    hdr = [heads]
                    note = "  表头取自 %s(第%s页)" % (src2, boxes_page.get(src2))
                else:
                    vh = VERIFIED_HEADERS.get(("%02d" % idx, src))
                    if vh:
                        # the section heading this row carried is not part of the real header;
                        # put it back at the top of the body so the category is not lost
                        keep = [c for r in hdr for c in r
                                if str(c or "").strip() and str(c).strip() not in vh[0]]
                        hdr = [list(vh[0])]
                        if keep:
                            body = [[str(keep[0]).strip()] + [""] * (len(vh[0]) - 1)] + body
                        note = "  表头人工核对：%s" % vh[1]
            report.append("bm_%02d t%-2d %s  列 %d->%d  行 %d->%d  并格 %d->%d  无名列 %s%s"
                          % (idx, ti, src, t.get("n_col"), len(grid[0]),
                             len(t.get("rows") or []), len(body), before, after,
                             tg or "无", note))
            if a.apply:
                t["header_rows"] = hdr
                t["rows"] = body
                t["n_col"] = len(grid[0])
                t["rebuilt_from_boxes"] = src
                dirty = True
                changed += 1
        if dirty:
            json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    txt = ("BITMAP 路线按 OCR 字框重建%s\n重建表数: %d\n%s"
           % ("  [DRY RUN]" if a.dry_run else "", changed, "\n".join(report)))
    print(txt)
    if a.apply:
        p = os.path.join(REOUT, "bitmap_rebuild.txt")
        open(p, "w", encoding="utf-8").write(txt)
        print("\n-> %s" % p)


if __name__ == "__main__":
    main()