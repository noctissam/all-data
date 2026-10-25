# -*- coding: utf-8 -*-
"""
Extract data tables from Chinese journal PDFs that have a real text layer.

Why not find_tables()
---------------------
PyMuPDF's table finder needs a cell grid. Chinese journals typeset three-line
tables (三线表) with no vertical rules, so "lines" and "lines_strict" both return
nothing, while "text" fallback returns MORE rows but sweeps in the page furniture
above and below the table - the journal banner, the abstract, the reference list.
The result is a grid whose "header" is a mash of 摘要：... and whose column roles
cannot be recovered.

What this does instead
----------------------
Use the table rules themselves as the row boundaries. Profiling showed every one of
these papers carries 15-232 horizontal rules, and most typeset a full-width rule
between every data row. So:

  1. merge the rule segments that share a y into one span (a table rule is often
     drawn as three separate segments, one per text column)
  2. group rules that are close together with matching x-extent into tables
  3. each gap between two consecutive rules is one band; if a band holds several
     text lines, split it by y
  4. inside a line, split into cells on horizontal gaps, then snap every cell to a
     column grid derived from the whole table so that columns line up across rows

Words come from the text layer, so compound names and numbers are exact - no OCR.
Papers whose text layer is OCR-derived are rejected up front (see text_ok) because
the chemistry glyphs are the ones OCR mangles: 酯 comes back as 酷, 阈 as 阂.

Usage:
    python src/extract_band.py [--only 12,13,17] [--limit 5]
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

# ------------------------------------------------------------------ geometry
MIN_SEG_W = 6.0        # a rule segment before merging; journals draw one per column
MIN_RULE_W = 50.0      # a merged table rule spans most of the text column
RULE_H = 3.5           # anything thicker is a box border, not a rule
RULE_Y_TOL = 2.5       # segments within this y are one rule
RULE_X_GAP = 4.0       # collinear segments this close are one continuous rule
BAND_GAP_MAX = 130.0   # bigger vertical distance between rules -> separate tables
X_OVERLAP_MIN = 0.35   # fraction of the narrower rule that must overlap
LINE_TOL = 3.0         # words this close in y are the same text line
CELL_GAP = 5.0         # horizontal gap that starts a new cell
COL_GAP = 7.0          # horizontal gap that starts a new column

# ------------------------------------------------------------------ roles
ROLES = [
    ("cas",       r"CAS"),
    ("name_cn",   r"香气物质|化合物名称|物质名称|呈香化合物|风味物质|风味化合物|化合物|成分名称"
                  r"|compound\s*name|name\s*of\s*compound|odorant|aroma\s*compound"
                  r"|volatile\s*compound|compound$|analyte"),
    ("ri",        r"保留指数|Kovats|\bRI\b|retention\s*index"),
    ("odor_desc", r"香气描述|风味描述|呈香特性|描述|odor\s*desc|descript|odor\s*character"),
    ("odor_val",  r"香气强度|OAV|香气活|嗅闻强度|FD\s*值|FD值|odor\s*value|odor\s*intensity"
                  r"|aroma\s*intensity|\bFD\b"),
    ("threshold", r"阈值|嗅闻阈值|感官阈值|OAV|threshold|odor\s*threshold|detection\s*threshold"),
    ("conc_group", r"质量浓度|相对含量|相对浓度|含量|浓度|峰面积|concentration|content|amount"
                   r"|abundance|area\s*ratio|level"),
    ("quant_ion", r"定量离子|特征离子|m/z|离子|quantification\s*ion|characteristic\s*ion"),
    ("method",    r"定性依据|鉴定|分析方法|检测方法|方法|identification|qualification"),
    ("no",        r"^序$|^序号$|^编号$|No\.?$|编号|^\d+\s*$|serial"),
    ("rt",        r"保留时间|保留值|retention\s*time|\bRT\b"),
]
ROLE_RE = [(k, re.compile(p, re.I)) for k, p in ROLES]

def classify_unit(s):
    """
    Unit from a parenthetical, tolerant of how Chinese journals typeset it.

    The same quantity appears as "mg·L-1", "mg / L", "μg/L" and "mg·L⁻¹"; the slash is
    often absent entirely and the exponent is typed as "-1", so a pattern that insists
    on "/" silently loses the unit and the column then looks unitless.
    """
    if not s:
        return ""
    t = s.replace(" ", "").replace("　", "")
    t = t.replace("·", "/").replace("*", "/").replace("×", "/").replace("⋅", "/")
    t = t.replace("－", "-").replace("−", "-").replace("⁻¹", "-1")
    t = re.sub(r"-\d$", "", t)                     # trailing exponent, e.g. L-1
    t = t.rstrip("/")
    if re.search(r"%(v/v|v|V/V)?$", t):
        return "%v/v" if "v" in t.lower() else "%"
    m = re.fullmatch(r"([munμµ]?g|kg)/(l|kg|ml|dL)", t, re.I)
    if m:
        return "%s/%s" % (m.group(1).replace("µ", "μ").lower(), m.group(2).lower())
    if re.fullmatch(r"[munμµ]?g", t, re.I):
        return t.replace("µ", "μ").lower()
    return ""


PAREN_RE = re.compile(r"[\(（\[【]([^()（）\[\]【】]{0,30})[\)）\]】]")
# Three bracket styles are in use in the corpus and only the round ones were being read,
# so a column headed "Relative content [mg/L]" or "含量【%】" reached the workbook with no
# unit. The character class excludes all three so a bracketed unit never swallows a
# bracketed aside.

# rows that are page furniture rather than table content
FURNITURE = re.compile(
    r"^(参考文献|摘要|关键词|引言|结论|致谢|收稿日期|基金项目|作者简介|"
    r"·\s*\d+\s*·|中\s*国\s*[酿食科]|食品科学技术|中\s*国\s*酿\s*造|"
    r"\d{4}\s*,?\s*\d+|\d{3}-\d{4})")

NUMCELL = re.compile(r"\d")          # a cell carrying a digit is data, not a label

# A cell that holds a MEASUREMENT, as opposed to one that merely contains a digit.
# The distinction decides what counts as header: a sample row reading X0 / X1 / X3
# has digits in it but is a label, and promoting it is what keeps 化合物名称 and the
# sample names together in the header instead of leaving the sample names in the data.
VALUE_RE = re.compile(r"^[-−+]?\d[\d  ,]*(?:\.\d+)?"
                      r"(?:\s*[±±]\s*\d[\d  ,]*(?:\.\d+)?)?"
                      r"\s*(?:[a-zA-Zμµ%／/·*\-]{0,6})?$")


def is_value_cell(s):
    s = (s or "").strip()
    if not s:
        return False
    if "±" in s or "＋" in s:
        return True
    return bool(VALUE_RE.match(s))


MISSING = {"", "-", "—", "–", "－", "/", "ND", "nd", "n.d", "N.D", "未检出",
           "未检测到", "tr", "Tr", "TR", "nd.", "*", "－", "―"}

CAPTION_RE = re.compile(r"^(表|Table|Tab\.?|TABLE)\s*\d", re.I)


def clean(s):
    if s is None:
        return ""
    s = s.replace("　", " ").replace("\xa0", " ").replace("’", "'")
    return re.sub(r"[ \t]*\n[ \t]*", " ", s).strip()


def is_missing(s):
    return clean(s) in MISSING


def text_ok(doc):
    """
    Reject OCR-derived text layers.

    A born-digital Chinese journal keeps 酯 and 阈; the CNKI OCR layer turns them
    into 酷 and 阂 and often flattens digits. Only fullwidth DIGITS and fullwidth
    LATIN are counted as evidence - fullwidth ，（）；： are normal typesetting in
    every one of these journals and would otherwise flag all of them.
    """
    t = "".join(p.get_text() for p in list(doc)[:8])
    if not t.strip():
        return False, "no text layer"
    if "�" in t:
        return False, "replacement chars present"
    bad = sum(1 for ch in t
              if (0xFF10 <= ord(ch) <= 0xFF19)      # ０-９
              or (0xFF21 <= ord(ch) <= 0xFF3A)     # Ａ-Ｚ
              or (0xFF41 <= ord(ch) <= 0xFF5A))    # ａ-ｚ
    if bad / max(len(t), 1) > 0.004:
        return False, "fullwidth digits/latin soup (%.4f)" % (bad / max(len(t), 1))
    if t.count("酯") == 0 and (t.count("醇") + t.count("酸")) > 50:
        return False, "no 酯 anywhere but plenty of 醇/酸"
    return True, ""


# ------------------------------------------------------------------ rules
def page_rules(page):
    """
    Horizontal rules, as (y, x0, x1).

    Order matters here. Journals frequently draw one rule as a row of separate
    segments - the aroma table in 杨斌 2023 has every horizontal line split into ten
    pieces of 40-54pt. Filtering by width before merging threw all of them away and
    the table became invisible, so segments are gathered first, collinear neighbours
    are joined, and only the merged span is tested against MIN_RULE_W.
    """
    raw = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.height <= RULE_H and r.width >= MIN_SEG_W:
            raw.append((round(r.y0, 1), round(r.x0, 1), round(r.x1, 1)))
    if not raw:
        return []
    raw.sort()
    by_y = []
    for y, x0, x1 in raw:
        if by_y and abs(y - by_y[-1][0]) <= RULE_Y_TOL:
            py, spans = by_y[-1]
            spans.append((x0, x1))
            by_y[-1] = ((py + y) / 2.0, spans)
        else:
            by_y.append((y, [(x0, x1)]))

    out = []
    for y, spans in by_y:
        spans.sort()
        cx0, cx1 = spans[0]
        for x0, x1 in spans[1:]:
            if x0 - cx1 <= RULE_X_GAP:
                cx1 = max(cx1, x1)
            else:
                if cx1 - cx0 >= MIN_RULE_W:
                    out.append((y, cx0, cx1))
                cx0, cx1 = x0, x1
        if cx1 - cx0 >= MIN_RULE_W:
            out.append((y, cx0, cx1))
    out.sort()
    return out


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def group_tables(rules):
    """Consecutive rules close together and spanning the same x range form a table."""
    tables, cur = [], []
    for y, x0, x1 in rules:
        if not cur:
            cur = [(y, x0, x1)]
            continue
        py, px0, px1 = cur[-1]
        ov = overlap(px0, px1, x0, x1) / max(min(px1, x1) - max(px0, x0), 1e-6)
        if (y - py) <= BAND_GAP_MAX and ov >= X_OVERLAP_MIN:
            cur.append((y, x0, x1))
        else:
            if len(cur) >= 2:
                tables.append(cur)
            cur = [(y, x0, x1)]
    if len(cur) >= 2:
        tables.append(cur)
    return tables


# ------------------------------------------------------------------ words
def lines_in(page, y0, y1, x0, x1):
    """Text lines between two rules, each a list of (x0, x1, text)."""
    ws = []
    for w in page.get_text("words"):
        wx0, wy0, wx1, wy1, txt = w[0], w[1], w[2], w[3], w[4]
        yc = (wy0 + wy1) / 2.0
        xc = (wx0 + wx1) / 2.0
        if y0 - 1 <= yc <= y1 + 1 and x0 - 4 <= xc <= x1 + 4:
            ws.append((yc, wx0, wx1, txt, wy1 - wy0))
    if not ws:
        return []
    ws.sort(key=lambda z: (z[0], z[1]))
    lines, cur, cy = [], [], None
    for it in ws:
        if cy is None or abs(it[0] - cy) <= LINE_TOL:
            cur.append(it)
            cy = it[0] if cy is None else (cy * (len(cur) - 1) + it[0]) / len(cur)
        else:
            lines.append(cur)
            cur, cy = [it], it[0]
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda z: z[1])
        cells, cx0, cx1, parts = [], None, None, []
        for yc, wx0, wx1, txt, h in ln:
            if cx0 is not None and wx0 - cx1 <= CELL_GAP:
                cx1 = max(cx1, wx1)
                parts.append(txt)
            else:
                if cx0 is not None:
                    cells.append((cx0, cx1, clean(" ".join(parts))))
                cx0, cx1, parts = wx0, wx1, [txt]
        if cx0 is not None:
            cells.append((cx0, cx1, clean(" ".join(parts))))
        if cells:
            out.append(cells)
    return out


def page_vrules(page):
    """Vertical rules as (x, y0, y1), collinear segments merged."""
    raw = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.width <= RULE_H and r.height >= MIN_SEG_W:
            raw.append((round(r.x0, 1), round(r.y0, 1), round(r.y1, 1)))
    raw.sort()
    merged = []
    for x, y0, y1 in raw:
        if merged and abs(x - merged[-1][0]) <= RULE_Y_TOL:
            px, a, b = merged[-1]
            merged[-1] = ((px + x) / 2.0, min(a, y0), max(b, y1))
        else:
            merged.append((x, y0, y1))
    return [m for m in merged if m[2] - m[1] >= 8.0]


def vrule_bounds(vrules, y_top, y_bot, x_lo, x_hi):
    """
    Column boundaries taken from the vertical rules that actually span this table.

    When a table is fully ruled the verticals ARE the columns - 杨斌 2023 draws them
    at x = 56.3, 96.0, 141.6, 184.1, ... which are exactly the cell edges. Using them
    removes all guesswork, which matters because interval-based column inference
    breaks on centred numbers (a short value leaves phantom gaps either side).
    """
    need = (y_bot - y_top) * 0.45
    xs = sorted(x for x, a, b in vrules
                if x_lo - 2 <= x <= x_hi + 2 and overlap(a, b, y_top, y_bot) >= need)
    if len(xs) < 2:
        return []
    out = [x_lo - 5.0]
    for x in xs:
        if x - out[-1] >= 8.0:
            out.append(x)
    out.append(x_hi + 5.0)
    return out if len(out) >= 3 else []


def column_grid(all_lines, x_lo, x_hi):
    """
    Column boundaries for a table that has no verticals, from a coverage profile.

    Earlier versions used "x ranges no cell ever covers". That fails twice over: a
    centred number leaves a gap on both sides, and a long name in one row fills a gap
    that exists in every other row. Projecting coverage across ALL rows instead makes
    a real separator a consistent valley, whatever the individual cell alignment is.
    """
    span = max(x_hi - x_lo, 1.0)
    nb = int(span) + 1
    cov = [0] * nb
    for ln in all_lines:
        for cx0, cx1, _t in ln:
            a = max(int(cx0 - x_lo) - 1, 0)
            b = min(int(cx1 - x_lo) + 2, nb)
            for i in range(a, b):
                cov[i] += 1
    if not any(cov):
        return []
    # smooth over ~6pt so single-bin noise cannot become a separator
    k = 3
    sm = [sum(cov[max(i - k, 0):i + k + 1]) / len(cov[max(i - k, 0):i + k + 1])
          for i in range(nb)]
    peak = max(sm)
    thr = max(peak * 0.34, 1.0)

    bounds, last = [x_lo - 5.0], 0
    for i in range(k + 1, nb - k - 1):
        if sm[i] < thr <= sm[i - 1] and (x_lo + i) - bounds[-1] >= 14.0:
            bounds.append(x_lo + i)
            last = i
    if (x_hi + 5.0) - bounds[-1] < 12.0:
        bounds.pop()
    bounds.append(x_hi + 5.0)
    return bounds if len(bounds) >= 3 else []


def grid_from_lines(lines, bounds, with_spans=False):
    """
    Snap each cell to a column. Cells sharing a column are joined, so a header like
    保留指数 + a stays one column label rather than two.

    with_spans also returns each filled cell's x-extent, which is what lets a unit
    written once across a group header ("质量浓度/(mg·L-1)" centred over five brand
    columns) be attributed to all five.
    """
    grid, spans = [], []
    nb = len(bounds) - 1
    for ln in lines:
        row = [""] * nb
        sp = [None] * nb
        for cx0, cx1, txt in ln:
            c = (cx0 + cx1) / 2.0
            k = 0
            while k < nb - 1 and c >= bounds[k + 1]:
                k += 1
            row[k] = (row[k] + " " + txt).strip() if row[k] else txt
            if sp[k] is None:
                sp[k] = [cx0, cx1]
            else:
                sp[k][0] = min(sp[k][0], cx0)
                sp[k][1] = max(sp[k][1], cx1)
        grid.append(row)
        spans.append([tuple(s) if s else None for s in sp])
    return (grid, spans) if with_spans else grid


# ------------------------------------------------------------------ tables
def page_bands(page):
    """
    The gap between each pair of consecutive rules, whether it can hold a table.

    Grouping rules into tables by proximity does not work: the running-head rule at
    the top of the page is a rule too, and a table whose rows are 300pt tall has only
    a top and a bottom rule 300pt apart. Deciding band by band instead - keep a gap
    when its x-extent matches its neighbour and the text in it is tabular - separates
    real tables from page furniture without depending on gaps being small.
    """
    rules = page_rules(page)
    out = []
    for i in range(len(rules) - 1):
        y0, a0, a1 = rules[i]
        y1, b0, b1 = rules[i + 1]
        denom = max(min(a1, b1) - max(a0, b0), 1e-6)
        out.append(dict(y0=y0, y1=y1,
                        x_lo=min(a0, b0), x_hi=max(a1, b1),
                        ok=(overlap(a0, a1, b0, b1) / denom) >= X_OVERLAP_MIN))
    return out


# A one-cell line that is a label in its own right, not the tail of a wrapped name. The
# ratio tables print 芳香族 / 酯类 / 吡嗪类 as rows, and a class label that lost its values
# would otherwise be appended to whatever compound sits above it, inventing a substance.
# Matched with search(), not match(): the test is what the text ENDS with, and match()
# anchors at the start so "醛酮类" never matched a pattern ending in "类".
STRAY_LABEL = re.compile(r"[类族]\s*$|[Σ∑]|总含量|合计|注[:：]")
DIGITS_ONLY = re.compile(r"^[\d.,]+$")

# A name ending in one of these is already a whole compound, so a line below it starts a
# NEW row rather than continuing it. Without this, a three-line wrap ("3-羟基" / "-2-丁" /
# "酮") has its first fragment attached to whatever compound happened to sit above it, which
# produced 糠醛3-羟基 - a name that resolves to nothing and looks like a real substance.
#
# The rule matches how the wrap actually falls: a name that needs a second line is cut
# BEFORE its suffix, so its first fragment ends in 基/甲/乙/二 and not in 酯/醇/醛.
COMPLETE_SUFFIX = re.compile(
    r"(酯|醇|酸|醛|酮|酚|醚|烯|烷|腈|肼|吡嗪|内酯|硫|胺|腙|肼)\s*$")

# Text that marks a line as a heading or a note rather than half a compound name. Without
# this, "合计风味" + "风味" and "二甲基三硫" + "脂肪酸" both glued, inventing substances.
# 硫 was missing from COMPLETE_SUFFIX, which is how 二甲基三硫 ended up as 二甲基三硫脂肪酸.
NOT_A_FRAGMENT = re.compile(r"化合物|平均值|平均|合计|小计|总计|其他|其他类|序号|注释|说明")


# Collected across a whole run so the rejoin can be reported instead of happening silently.
WRAP_MERGED = []
WRAP_SKIPPED = []


def merge_wrapped_names(rows, bounds):
    """
    Rejoin a compound name that the paper printed across two baselines.

    A long name in a narrow first column wraps: 2-甲基丁醇 is printed as "2-甲基" on one
    line and "丁醇" on the next, with the measurements on the first line. The grid reads one
    row per baseline, so the first becomes a compound called "2-甲基" and the second is a
    line with a single filled cell - which the "at least two cells" filter then throws away
    entirely. The name is silently truncated and nothing is left to notice.

    The second line is rejoined onto the row above it, but only when the shape is
    unmistakable:
      - exactly one cell filled, and it is the leftmost (the name column);
      - the text is short, because it is the tail of a name, not a label;
      - the row above has real measurements, so this is not a heading;
      - the row above already has a name, so there is something to continue.

    Anything that does not fit is left alone and recorded, because appending the wrong text
    to a compound name is worse than leaving it truncated - the first case produces a name
    that looks like a real substance and resolves to a real, wrong CAS.

    Returns (rows, merged_list, skipped_list).
    """
    merged, notes, skipped = [], [], []
    for r in rows:
        cells = [c.strip() for c in r]
        filled = [i for i, c in enumerate(cells) if c]
        if len(filled) == 1 and filled[0] == 0 and merged:
            tail = cells[0]
            prev = merged[-1]
            prev_filled = sum(1 for c in prev if c.strip())
            prev_vals = sum(1 for c in prev[1:] if c.strip() and is_value_cell(c))
            # captured BEFORE any assignment: prev is the same list object as merged[-1],
            # so reading prev[0] after the merge returns the merged text and the report
            # reads "X = X + tail" for every line
            head = prev[0].strip()
            if (len(tail) <= 8 and prev_filled >= 2 and prev_vals >= 1
                    and head and not STRAY_LABEL.search(tail)
                    and not COMPLETE_SUFFIX.search(prev[0])
                    and not NOT_A_FRAGMENT.search(prev[0])
                    and not NOT_A_FRAGMENT.search(tail)
                    and not DIGITS_ONLY.match(head)
                    and not DIGITS_ONLY.match(tail)):
                joined = head + tail
                prev[0] = joined
                notes.append((head, tail, joined))
                continue
            skipped.append((tail, "上一行形态不符(填充%d/数值%d)"
                            % (prev_filled, prev_vals)))
        merged.append(list(r))
    return merged, notes, skipped


def page_tables(page, furniture=frozenset()):
    """
    Tables on one page, as (header_rows, data_rows, n_col).

    The header is the first band by construction rather than by keyword matching: in a
    ruled table the gap between the top rule and the next one IS the header. That
    holds for three-line tables and fully-ruled ones alike, whereas looking for words
    like 香气物质 fails on a table headed 品牌名称 or on one with no words at all.
    """
    out = []
    vrules = page_vrules(page)
    run = []

    def flush(run):
        if not run:
            return
        x_lo = min(b["x_lo"] for b, _l in run)
        x_hi = max(b["x_hi"] for b, _l in run)
        y_top, y_bot = run[0][0]["y0"], run[-1][0]["y1"]
        flat = [l for _b, ls in run for l in ls]
        bounds = vrule_bounds(vrules, y_top, y_bot, x_lo, x_hi)
        how = "vrules"
        if not bounds:
            bounds = column_grid(flat, x_lo, x_hi)
            how = "profile"
        if len(bounds) < 3:
            return
        ncol = len(bounds) - 1
        head_lines = run[0][1]
        tail_lines = [l for _b, ls in run[1:] for l in ls]
        if tail_lines:
            header_rows, header_spans = grid_from_lines(head_lines, bounds, with_spans=True)
            grid = [r for b in tail_lines for r in grid_from_lines([b], bounds)]
            # a group header often needs a second line: 质量浓度/(mg·L-1) over
            # 序号 保留时间 ... then the sample names. Promote the leading run of
            # rows that hold no measurement at all.
            extra = 0
            while (extra < 3 and len(grid) > 4
                   and not any(is_value_cell(c) for c in grid[0])
                   and all(not is_value_cell(c) for c in grid[extra])):
                extra += 1
            if extra:
                header_rows = header_rows + grid[:extra]
                grid = grid[extra:]
            rows = grid
        else:
            # only one band: header and body share it, so split on content
            grid, spans = grid_from_lines(head_lines, bounds, with_spans=True)
            cut = 0
            while cut < min(4, len(grid) - 2) and not any(is_value_cell(c)
                                                         for c in grid[cut]):
                cut += 1
            cut = cut or 1
            header_rows, header_spans = grid[:cut], spans[:cut]
            rows = grid[cut:]
        # Rejoin a wrapped compound name BEFORE the thin-row filter runs, because the
        # continuation line is exactly the thin row that filter discards. Doing it after
        # would be too late: the text is already gone.
        rows, merged_notes, skipped_notes = merge_wrapped_names(rows, bounds)
        WRAP_MERGED.extend(merged_notes)
        WRAP_SKIPPED.extend(skipped_notes)
        rows = [r for r in rows if sum(1 for c in r if c.strip()) >= 2]
        if len(rows) < 2:
            return
        out.append(dict(bbox=[round(x_lo, 1), round(y_top, 1), round(x_hi, 1),
                              round(y_bot, 1)],
                        n_bands=len(run), cols=how, header_rows=header_rows,
                        header_spans=header_spans, bounds=bounds,
                        rows=rows, n_col=ncol))

    for b in page_bands(page):
        if not b["ok"]:
            flush(run)
            run = []
            continue
        ln = lines_in(page, b["y0"], b["y1"], b["x_lo"], b["x_hi"])
        ln = [l for l in ln
              if not (len(l) == 1
                      and (FURNITURE.match(l[0][2] or "") or (l[0][2] or "") in furniture))]
        # one line is only tabular if it already has several cells; two or more lines
        # qualify as soon as they sit between two rules of the same table
        if ln and (len(ln) >= 2 or len(ln[0]) >= 3):
            run.append((b, ln))
        else:
            flush(run)
            run = []
    flush(run)
    return out


# ------------------------------------------------------------------ header
def header_row_index(grid):
    """
    Index of the first row that reads like a header: at least two cells naming a
    column role. Data rows essentially never do.
    """
    for i, r in enumerate(grid[:6]):
        hits = sum(1 for c in r if any(rx.search(c or "") for _k, rx in ROLE_RE))
        if hits >= 2:
            return i
    return -1


def col_roles(header_rows, header_spans, bounds, ncol):
    """
    Per column: role keyword and unit.

    Two things a naive per-column lookup gets wrong on Chinese aroma tables:
      - the group label 质量浓度/(mg·L-1) is centred over five brand columns, so it
        lands in ONE column and the other four look unlabelled. The cell's x-extent
        (header_spans) says which columns it governs, and they are filled in from it.
      - the unit may only appear in a parenthetical, so it is read from the text of
        the header block rather than expected to match the column label.
    """
    roles, units = [], []
    for c in range(ncol):
        role = None
        for r in header_rows:
            v = (r[c] if c < len(r) else "") or ""
            if not v.strip():
                continue
            for k, rx in ROLE_RE:
                if rx.search(v):
                    role = k
                    break
            if role:
                break
        roles.append(role)
        units.append("")

    for r, sp in zip(header_rows, header_spans or []):
        for c in range(ncol):
            v = (r[c] if c < len(r) else "") or ""
            if not v.strip():
                continue
            s = sp[c] if c < len(sp) else None
            for ptext in PAREN_RE.findall(v):
                u = classify_unit(ptext)
                if not u:
                    continue
                lo = s[0] if s else None
                hi = s[1] if s else None
                # a group label is centred over its span, so its own x-extent covers
                # only one column; grow outward to the neighbouring unlabelled columns
                span = [d for d in range(ncol)
                        if lo is None or (lo - 2 <= (bounds[d] + bounds[d + 1]) / 2 <= hi + 2)]
                grown = set(span)
                for d in span:
                    for step in (-1, 1):
                        k = d
                        while 0 <= k + step < ncol and roles[k + step] is None \
                                and not (r[k + step] or "").strip():
                            k += step
                            grown.add(k)
                for d in grown:
                    if not units[d]:
                        units[d] = u
                    if roles[d] is None:
                        for k, rx in ROLE_RE:
                            if rx.search(v):
                                roles[d] = k
                                break
    return roles, units


def hdr_sig(grid, _row, ncol):
    """Header identity for cross-page stitching: the last header row, whitespace-free."""
    r = grid[-1] if grid else []
    return "|".join(re.sub(r"\s+", "", (r[c] if c < len(r) else "")) for c in range(ncol))


def running_furniture(doc, min_pages=3):
    """
    Text that sits in the same place on several pages - the journal banner, the
    running title, the page number. It is drawn with rules and lands inside table
    bands often enough that it has to be recognised by repetition, not by pattern:
    the banner in 关宝义 2025 reads "Analysis a", which no keyword list would match.
    """
    seen = {}
    for p in doc:
        h = p.rect.height
        ws = [w for w in p.get_text("words") if (w[1] + w[3]) / 2 < 0.09 * h
              or (w[1] + w[3]) / 2 > 0.91 * h]
        lines = {}
        for w in ws:
            key = round((w[1] + w[3]) / 2 / 4.0)
            lines.setdefault(key, []).append(w)
        for key, grp in lines.items():
            txt = re.sub(r"\s+", "", clean(" ".join(w[4] for w in sorted(grp, key=lambda z: z[0]))))
            if len(txt) < 3:
                continue
            k = (key, txt)
            seen[k] = seen.get(k, 0) + 1
    return frozenset(txt for (_k, txt), n in seen.items() if n >= min_pages)


def extract(path):
    doc = pymupdf.open(path)
    ok, why = text_ok(doc)
    if not ok:
        doc.close()
        return dict(route="needs-ocr", note=why, tables=[])
    furniture = running_furniture(doc)
    frags = []
    for pno in range(doc.page_count):
        for t in page_tables(doc[pno], furniture):
            frags.append(dict(page=pno + 1, **t))
    doc.close()

    # stitch a table that runs over a page break: the header repeats, so a matching
    # header signature on the next page means continuation, not a new table
    merged = []
    for f in frags:
        g = [r + [""] * (f["n_col"] - len(r)) for r in f["rows"]]
        h = [r + [""] * (f["n_col"] - len(r)) for r in f["header_rows"]]
        sig = hdr_sig(h, 0, f["n_col"])
        for t in merged:
            if (f["page"] - t["pages"][-1]) <= 1 and t["sig"] == sig and t["n_col"] == f["n_col"]:
                t["rows"].extend(g)
                t["pages"].append(f["page"])
                break
        else:
            merged.append(dict(header_rows=h, header_spans=f.get("header_spans"),
                               rows=g, n_col=f["n_col"], bounds=f.get("bounds"),
                               pages=[f["page"]], sig=sig))

    out = []
    for t in merged:
        g = drop_repeated_header(t["rows"], t["header_rows"])
        if len(g) < 2:
            continue
        roles, units = col_roles(t["header_rows"], t.get("header_spans"),
                                 t.get("bounds") or [], t["n_col"])
        # the caption is context, not a column label - keep it apart so the header
        # row can be written as the column headings it is
        cap = ""
        for h in t["header_rows"]:
            for c in h:
                if CAPTION_RE.match(c or ""):
                    cap = clean(" ".join(x for x in h if x.strip()))
                    break
            if cap:
                break
        out.append(dict(caption=cap,
                        header=t["header_rows"][-1], header_rows=t["header_rows"],
                        roles=roles, units=units,
                        rows=[[clean(c) for c in r] for r in g],
                        n_row=len(g), n_col=t["n_col"], pages=t["pages"],
                        has_name=("name_cn" in roles)))
    out.sort(key=lambda z: (z["pages"][0], -z["n_row"]))
    return dict(route="band" if out else "no-tables",
                note="" if out else "no ruled table found",
                tables=out)


def drop_repeated_header(rows, header_rows):
    """
    A table that spans pages repeats its header on each page, and a two-row header
    also repeats both parts. Those rows are not data, so remove any row whose filled
    cells match the header cells they line up with.

    Only applied once the table is known to be substantial. A two-row table whose
    single data row happens to echo its own header would otherwise be emptied out and
    the whole table lost, which is worse than keeping one redundant row.
    """
    hdr = [h for h in header_rows if sum(1 for c in h if c.strip()) >= 2]
    if not hdr or len(rows) < 5:
        return rows
    keep = []
    for r in rows:
        filled = [(i, (r[i] if i < len(r) else "").strip()) for i in range(len(r))]
        filled = [(i, v) for i, v in filled if v]
        if len(filled) < 2:
            keep.append(r)
            continue
        same = 0
        for h in hdr:
            hits = sum(1 for i, v in filled
                       if (h[i] if i < len(h) else "").strip() == v)
            same = max(same, hits)
        if same >= max(2, int(len(filled) * 0.6)):
            continue
        keep.append(r)
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    entries = json.load(open(MAP, encoding="utf-8"))
    only = set(int(x) for x in a.only.split(",") if x.strip())
    n = 0
    for e in entries:
        if only and e["idx"] not in only:
            continue
        if a.limit and n >= a.limit:
            break
        if not e.get("path") or not os.path.exists(e["path"]):
            print("  #%-3d %-44s -> PDF 缺失" % (e["idx"], (e.get("pdf") or "")[:44]))
            n += 1
            continue
        r = extract(e["path"])
        fn = os.path.join(OUTDIR, "band_%02d.json" % e["idx"])
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(dict(idx=e["idx"], sheet=e["sheet"], pdf=e.get("pdf"),
                           **r), f, ensure_ascii=False, indent=1)
        if r["route"] != "band":
            print("  #%-3d %-44s -> %s %s" % (e["idx"], (e.get("pdf") or "")[:44],
                                               r["route"], r["note"][:44]))
        else:
            rows = sum(t["n_row"] for t in r["tables"])
            named = sum(1 for t in r["tables"] if "name_cn" in (t["roles"] or []))
            print("  #%-3d %-44s tables=%-3d named=%-2d rows=%-5d %s" % (
                e["idx"], (e.get("pdf") or "")[:44], len(r["tables"]), named, rows,
                "; ".join("%dx%d" % (t["n_row"], t["n_col"]) for t in r["tables"][:4])))
        n += 1
    print("\nprocessed %d" % n)

    # The wrap rejoin changes what a compound is called, so it is reported rather than
    # applied silently. Written next to the band files; a wrong rejoin produces a
    # plausible-looking name, which is the failure nobody would otherwise catch.
    kinds = {}
    for a, b, c in WRAP_MERGED:
        kinds.setdefault(c, (a, b))
    rep = ["WRAPPED-NAME REJOIN  %d occurrences, %d distinct names" % (len(WRAP_MERGED),
                                                                      len(kinds)),
           "=" * 74]
    for c in sorted(kinds):
        a, b = kinds[c]
        rep.append("   %-30s  = %-18s + %s" % (c, a, b))
    if WRAP_SKIPPED:
        seen = set()
        left = []
        for tail, why in WRAP_SKIPPED:
            if tail in seen:
                continue
            seen.add(tail)
            left.append("   %-18s %s" % (tail, why))
        rep.append("")
        rep.append("left unrejoined (%d distinct)" % len(left))
        rep.extend(left)
    outp = os.path.join(OUTDIR, "wrap_report.txt")
    open(outp, "w", encoding="utf-8").write("\n".join(rep))
    print("wrap rejoin: %d occurrences, %d distinct -> %s"
          % (len(WRAP_MERGED), len(kinds), outp))


if __name__ == "__main__":
    main()
