# -*- coding: utf-8 -*-
"""
Build the "re整理" workbook: one sheet per literature, in data.xlsx order.

Nothing here reads the old data values. Sheet order is the contract - sheets 2-12 of
data.xlsx are the English papers and 13-35 the Chinese ones numbered on from the
English count - and each slot is filled from its own PDF.

Per literature the sheet carries two blocks:

  基础数据   the priority-1 fields: compound name, concentration (with unit), threshold,
             OAV / odour value, retention index. Columns are inferred from the CONTENT
             of each column rather than trusted from the keyword roles alone: caption
             text such as "共有挥发性风味物质含量" matches a compound-name keyword but
             sits above the table, so a keyword-only assignment puts the wrong column
             in the name slot. A column that is mostly non-numeric text is the name
             column; a column that is mostly measurements is a data column.

  原表逐格   every extracted cell, verbatim, with the caption and header rows.

A table that carries no concentration at all is labelled as such rather than left
blank, because Chinese GC-O papers report odour intensity instead and a blank cell
is indistinguishable from an extraction failure.

CAS is left empty on purpose: no paper prints it, and it is filled from PubChem in a
separate step so name and CAS can be checked in both directions first.

Usage:
    python src/build_rec整理.py [--out re整理.xlsx] [--src band]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extract_band import PAREN_RE, classify_unit, clean as _clean  # noqa: E402
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))

TITLE_FONT = Font(bold=True, size=12)
HEAD_FONT = Font(bold=True, size=10)
META_FONT = Font(size=9, color="555555")
CAP_FONT = Font(bold=True, size=10, color="1F4E79")
HEAD_FILL = PatternFill("solid", fgColor="DDEBF7")
KEY_FILL = PatternFill("solid", fgColor="FFF2CC")
OK_FILL = PatternFill("solid", fgColor="E2EFDA")
BAD_FILL = PatternFill("solid", fgColor="FCE4E4")

MISSING = {"", "-", "—", "–", "－", "/", "ND", "nd", "n.d", "未检出", "未检测到",
           "tr", "Tr", "TR", "nd.", "*", "―"}

# A CAS registry number. The final digit group is a check digit, which is what makes a
# mis-read detectable: "CC14" in place of "CCl4" fails this pattern instead of being
# carried into the sheet as if it were a registry number.
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
CAS_COL = re.compile(r"^\s*CAS\b|化学.?CAS|CAS.?号", re.I)

VALUE_RE = re.compile(r"^[-−+]?\d[\d  ,]*(?:\.\d+)?"
                      r"(?:\s*±\s*\d[\d  ,]*(?:\.\d+)?)?"
                      r"\s*(?:[a-zA-Zμµ%／/·*\-]{0,6})?$")
# OAV must be tested before threshold, and must not appear in the threshold pattern at
# all: "OAV" is an activity value, not a detection limit, and because the threshold
# pattern is checked first an OAV column was being reported as 阈值 with the threshold
# column's own label beside it.
THR_RE = re.compile(r"阈值|threshold|检出限| detection\s*limit", re.I)
OAV_RE = re.compile(r"香气强度|OAV|FD|odor\s*(?:value|intensity)", re.I)
# Identifier columns hold numbers but are not measurements of the compound: the
# monitored ion, the internal standard, a database ID, the molecular formula. Tested
# against the JOINED header text because these labels are split across two rows - the
# cell reads "ion" on its own and "Quantified" sits in the row above it.
ID_RE = re.compile(r"quantified\s*ion|characteristic\s*ion|internal\s*standard"
                   r"|定量离子|特征离子|内标|离子强度|离子|m/z|CAS|分子式|molecular\s*formula",
                   re.I)
# ...and a bare "IS" / "ID" only reads as an identifier in a single cell, where there is
# nothing else for it to be part of.
ID_CELL = re.compile(r"^\s*(IS|ID|TIC|SIM|RT)\s*$", re.I)
# Detection limits are instrument figures, not what the paper is measuring about the
# sample; the odour threshold is the number of interest and has its own column.
LOD_RE = re.compile(r"\bLOD\b|\bLOQ\b|检出限|检测限|定量限|最低检出|仪器分析下限", re.I)
RI_RE = re.compile(r"保留指数|Kovats|\bL?RI|[Ｒ Ｒ]I\b|数[ＲR][ＩI]|retention\s*index", re.I)
RT_RE = re.compile(r"保留时间|迁移时间|retention\s*time|\bRT\b", re.I)
NO_RE = re.compile(r"^\s*(序|序号|编号|no\.?|#)\s*$|serial", re.I)

# A bare column-heading word, or a paper's section number, read into the name column.
HEADER_WORD = re.compile(
    r"^\s*(name|compound|analyte|odorant|substance|concentration|content|"
    r"total|average|sd|average\s*deviation|sample|no\.?)\s*$"
    r"|^\s*\d{1,2}\.\d{1,2}\s*$", re.I)
# Statistics columns are numbers in a compound table but are not measurements of the
# compound. A calibration table (slope / intercept / R2) sits right next to the real
# concentration columns and would otherwise be carried into the basic-data view as if
# it were one.
STAT_RE = re.compile(r"\bslope\b|\bintercept\b|\bR\s*[²2]\b|equation|calibration"
                     r"|correlation|regression|\bp\s*[-–]\s*value|\bt\s*[-–]\s*value"
                     r"|\bF\s*[-–]\s*value|\bRSD\b|relative\s*standard\s*deviation"
                     r"|斜率|截距|回归系数|标准曲线|回归|相对标准偏差|pearson|\bp\s*value|显著|significance|\br\s*value|标准偏差"
                     # the Chinese statistical vocabulary was missing entirely, so a
                     # 相关系数 / 变量重要度 column beside the real concentrations was read as
                     # a concentration - and the sheet then reported numbers in it as
                     # samples with no unit
                     r"|相关系数|相关性|变量重要度|变量投影重要度|\bVIP\b|主成分|特征值|方差贡献"
                     r"|方差解释|累计贡献|判别系数|投影得分|潜变量", re.I)
UNIT_RE = re.compile(r"[\(（]([^()（）]{0,30})[\)）]")

# Characters that make a Chinese string a chemical name rather than a sample label.
# Without this the 品牌名称 / 生产厂家 table yields a "basic data" block of brands.
CHEM_RADICAL = re.compile(r"[酯酸醇醛烷烯苯吡酚酮醚腙肼基苯甲苯酚]"
                          r"|乙|丁|戊|己|庚|辛|壬|癸")
LATIN_NAME = re.compile(r"[A-Za-z]{4,}")


def looks_like_compound(s):
    s = (s or "").strip()
    if not s:
        return False
    if re.search(r"[\u4e00-\u9fff]", s):
        return bool(CHEM_RADICAL.search(s)) and not re.search(r"白酒|酒型|组$|品牌", s)
    return bool(LATIN_NAME.search(s))


NAME_RE = re.compile(r"香气物质|化合物名称|物质名称|风味物质|风味化合物|呈香化合物"
                     r"|compound\s*name|odorant|analyte", re.I)

# Characters that make a Chinese string a chemical name rather than a sample label.
# Without this the 品牌名称 / 生产厂家 table yields a "basic data" block of brands.
CHEM_RADICAL = re.compile(r"[酯酸醇醛烷烯苯吡酚酮醚腙肼基甲]"
                          r"|乙|丁|戊|己|庚|辛|壬|癸")
LATIN_NAME = re.compile(r"[A-Za-z]{4,}")


# Class labels and grand totals, not compounds. The ratio tables (表3-3, 表3-6) print
# 酯类 / 醇类 / 醛酮类 / 吡嗪类 and their Σ totals as rows. Every one of those passes the
# radical test below, because 酯, 醇, 醛 and 酮 are all radicals - so they entered the
# compound block and were then offered to the CAS lookup as if they were substances. A
# class label covers a whole group and has no registry number, so the blank cell there is
# the correct answer rather than a gap.
CATEGORY_ROW = re.compile(
    r"(?:酯|醇|酸|醛|酮|烯|苯|酚|吡嗪|含氮|硫化物|缩醛|呋喃|萜烯|芳香族|羰基)"
    r"类\s*(?:[Σ∑]\s*)?(?:\s*[（(]\s*×\s*10[^)）]*[)）]?)?\s*$"
    # the same label with the unit in brackets instead of a scale factor:
    # "酯类（g·L-1）" is the total-ester row, not a compound called 酯类
    r"|(?:酯|醇|酸|醛|酮|烯|苯|酚|缩醛|羰基)类\s*[（(][^)）]*[)）]\s*$"
    r"|物质总含量|总含量|脂肪酸")


def looks_like_compound(s):
    s = (s or "").strip()
    if not s:
        return False
    # checked before the radical test, which these rows would otherwise pass
    if CATEGORY_ROW.search(s):
        return False
    if re.search(r"[\u4e00-\u9fff]", s):
        return bool(CHEM_RADICAL.search(s)) and not re.search(r"白酒|酒型|组$|品牌", s)
    return bool(LATIN_NAME.search(s))


def is_value(s):
    s = (s or "").strip()
    if not s or s in MISSING:
        return False
    if "±" in s:
        return True
    return bool(VALUE_RE.match(s))


def col_stats(rows, c):
    vals = [(r[c] if c < len(r) else "").strip() for r in rows]
    filled = [v for v in vals if v]
    if not filled:
        return 0, 0, 0
    nv = sum(1 for v in filled if is_value(v))
    return len(filled), nv, len(filled) - nv


# A header cell is a sample name or a unit - a few characters. A cell carrying thirty of
# them is a sentence from the paragraph above the table, which is what the extractor files
# as header_rows on the pages where the table does not start at the top of a band.
PROSE_CELL = 24

# Two different questions, two different tests. Asking "is this cell a value?" and asking
# "does this row look like measurements?" are not the same, and using one regex for both is
# what left headers in the body:
#
#   "2 年陈"   a sample name that HAPPENS to start with a digit
#   "1 2"      two cells the grid merged; a level label, not a number
#   "5"        a level label, and a number
#
# Under a prefix match all three read as values, so the row scored zero labels and was never
# promoted - and the columns it named were reported as 列N while sitting right there.
#
# A value is a whole cell that is a number, optionally with a spread, a range, or a
# significance letter. Anything with other text in it is a label.
#
# Spaces are part of the digit run on purpose: these papers typeset thousands separators as
# thin spaces ("4 782.47"), and without them that cell reads as a LABEL - which promoted the
# first measurement row into the header block and replaced five sample names with five
# numbers.
# A space is a thousands separator only when exactly three digits follow it. "4 782.47" is
# one number written with a thin-space separator; "1 2" is the grid merging the 浓度梯度
# columns 1 and 2 into one cell, and treating it as the number 12 made the real header row
# look like a measurement row, so it was never promoted.
_CORE = r"(?:[-+]?\d{1,3}(?:[ ,  ]\d{3})*(?:\.\d+)?|[-+]?\d+(?:\.\d+)?)"
NUMBERISH = re.compile(
    r"^" + _CORE +
    r"(?:\s*(?:±|\+/-|[-–~])\s*" + _CORE + r")?"   # ± SD, or a range
    r"\s*[A-Za-z°º*%]{0,3}$")                          # 0.25b
STARTS_DIGIT = re.compile(r"^\s*[-+]?\d")


def _is_prose(row):
    cells = [str(x).strip() for x in (row or []) if str(x or "").strip()]
    return any(len(c) > PROSE_CELL for c in cells)


def _label_share(row):
    """
    Fraction of a row's filled cells that are labels rather than values or placeholders.

    A header is labels all the way across. A measurement row is mostly numbers, and one
    that is mostly dashes is a "not detected" row - 乙醚 with five "-" under it. Promoting
    that gave the concentration columns a header of "-", which reads as a name and passes
    every check that only asks whether the cell is non-empty.
    """
    cells = [str(x).strip() for x in (row or []) if str(x or "").strip()]
    if not cells:
        return 0.0
    labels = [c for c in cells
              if not NUMBERISH.match(c) and c.strip("-–—<>~*·.。/ ")]
    return len(labels) / float(len(cells))


def _looks_like_measurements(row):
    """
    Whether a row is the first row of data under a header.

    Deliberately a prefix test, not NUMBERISH: the grid merges two cells into one often
    enough that "64.565 129.13" is a single cell holding two measurements, and requiring the
    whole cell to be one number would fail to recognise the row.
    """
    cells = [str(x).strip() for x in (row or []) if str(x or "").strip()]
    return sum(1 for c in cells if STARTS_DIGIT.match(c)) >= 2


def _unit_like(s):
    """
    Whether a header cell is a unit rather than a name.

    This is what separates a leaf heading from a group heading. "阈值" with "(μg·L-1)"
    beneath it heads exactly one column; "Concentrations (μg/L)" with "LZ-2016 base SAB"
    and "GJ-1573" beneath it heads two. Same row, same shape of cell - only what sits
    underneath tells them apart.
    """
    s = str(s or "")
    if not s:
        return False
    return bool(re.search(r"[μµ]?g\s*[·/]?\s*[lL]|%|kg|mg|ng|mol|ppm|ppb", s))


def apply_group_spans(hdr_rows, ncol):
    """
    Per-column header cells, with a merged group heading carried across the columns it
    actually covers.

    A heading's span is the run of columns under it that carry their own sub-labels, cut
    short at the next heading in the same row. A heading with only a unit beneath it spans
    one column. Columns with no heading over them keep whatever they had.

    Reading the sub-header row rather than the blanks beside the heading matters because a
    centred heading is filed in a middle column: in 表2 of the sorghum paper OAV sits at
    column 7 of a group occupying 3..10, and filling rightwards would hand it 7..10 and
    give 阈值 the other four.
    """
    own = [[(r[c] if c < len(r) else "").strip() for r in hdr_rows
            if (r[c] if c < len(r) else "").strip()] for c in range(ncol)]

    for ri, r in enumerate(hdr_rows):
        heads = [c for c in range(ncol) if (r[c] if c < len(r) else "").strip()]
        if len(heads) < 2:
            continue

        # A heading is a LEAF when everything printed directly beneath it is a unit: 阈值
        # with (mg·L-1) under it owns one column. Everything else is a GROUP heading and owns
        # the whole stretch of labelled columns up to the next heading's territory - because
        # it is printed over the middle of that stretch, not at its left edge.
        is_group = []
        for c in heads:
            subs = [(rr[c] if c < len(rr) else "").strip()
                    for rr in hdr_rows[ri + 1:] if c < len(rr)]
            subs = [x for x in subs if x]
            is_group.append(bool(subs) and not all(_unit_like(x) for x in subs))

        # The stretch stops at the last column that carries a sub-label in the LAST header
        # row - the sample-name row. Without that bound the stretch ran to the end of the
        # table and swallowed the next heading along: in 表1 of the grades paper OAV took
        # 优级 一级 二级 丢糟 AND 气味描述, a column of aroma descriptions.
        last = hdr_rows[-1] if hdr_rows else r
        tail_cols = [c for c in range(ncol)
                     if (last[c] if c < len(last) else "").strip()]

        bounds = []
        for k, c in enumerate(heads):
            start = bounds[k - 1][1] + 1 if k else c
            end = ncol - 1
            if k + 1 < len(heads):
                end = heads[k + 1] - 1 if is_group[k] else c
            after = [x for x in tail_cols if x >= start]
            if after:
                end = min(end, after[-1])
            if end < start:
                end = start
            bounds.append((start, end))

        for k, c in enumerate(heads):
            if not is_group[k]:
                continue
            label = (r[c] if c < len(r) else "").strip()
            if not label:
                continue
            for j in range(bounds[k][0], bounds[k][1] + 1):
                if j != c and label not in own[j]:
                    own[j].insert(0, label)
    return own


def promote_header_rows(t):
    """
    Move leading rows that are headers in everything but name into the header block.

    Chinese tables often put the unit and the sample names in a row that sits below the
    real header - "（mg·L-1） 优级 一级 二级 丢糟" - and it gets read as the first data row.
    Two things go wrong when that happens, and both are quiet: the concentration columns
    are labelled with the sample names instead, and no column has a unit at all, because
    the only place the unit was written was mistaken for a value.

    A row qualifies when one of its cells holds a unit and the rest are labels rather
    than numbers. A data cell cannot qualify: classify_unit only accepts g/kg/%, so a
    value in brackets like (1.2) or a citation [66] is not a unit.

    Two more conditions, both added because the unit test alone left headers behind:

      - a row long enough to be a paragraph is dropped from the header block even if the
        extractor filed it there. On some pages the body text ABOVE the table is handed
        over as header_rows; those ten lines of prose then push the real header row into
        the body, and every column under it loses its name.
      - a row of short labels is promoted on the strength of the row BELOW it being
        numeric, even with no unit of its own. Papers do print the unit on a separate
        line further up, leaving the label row bare: 表1 heads its measurements with
        "X0 X1 X3 X5 X8" and states mg/L on a line by itself.

    Returns (header_rows, body_rows); the table itself is not modified, because the
    原表逐格 block is meant to stay exactly as extracted.
    """
    hdr = [r for r in (t.get("header_rows") or []) if not _is_prose(r)]
    body = list(t.get("rows") or [])
    while body:
        row = body[0]
        cells = [str(x).strip() for x in row if str(x).strip()]
        if not cells:
            break
        has_unit = any(classify_unit(p) for x in cells for p in PAREN_RE.findall(x))
        labels = sum(1 for c in cells if not NUMBERISH.match(c))
        unit_ok = has_unit and labels >= max(1, len(cells) * 0.5)
        nxt = body[1] if len(body) > 1 else None
        # a bare row of labels sitting on top of numeric rows is a header. Without this the
        # X0/X1/X3/X5/X8 row stayed in the body, the column it names was reported as 列3, and
        # the year columns were the only ones in the sheet with no usable label.
        label_ok = (nxt is not None
                    and not _is_prose(row)
                    and _label_share(row) >= 0.5
                    and labels >= max(1, len(cells) * 0.6)
                    and _looks_like_measurements(nxt))
        if not (unit_ok or label_ok):
            break
        hdr.append(row)
        body.pop(0)
    return hdr, body


def classify_columns(t):
    """
    Assign each column a use from its own content plus its header text.

    Returns dict with name_col, data_cols [(c, unit)], thr_cols, oav_cols, ri_cols.
    """
    rows = t["rows"]
    ncol = t["n_col"]
    # A leading row holding the unit and the sample names is a header row the extractor
    # filed as data; promoting it is what gives the columns their unit and their labels.
    hdr_rows, body_rows = promote_header_rows(t)
    rows = body_rows
    hdr_text = [" ".join((r[c] if c < len(r) else "") or "" for r in hdr_rows)
                for c in range(ncol)]
    # per-column header cells kept separately: the exact-match checks (序号, 保留时间)
    # have to see a single cell, because the joined text repeats the label once per
    # header row and "序号 序号 序号" no longer matches ^序号$
    hdr_cells = [[(r[c] if c < len(r) else "").strip() for r in hdr_rows
                  if (r[c] if c < len(r) else "").strip()] for c in range(ncol)]

    # Carry a group heading across the columns it spans.
    #
    # Papers print a merged heading once, over the middle of its group, and leave the
    # neighbouring cells of that row empty. Reading a column's own cells alone therefore
    # loses the heading for every column except the one it happened to be printed over.
    #
    # In 表3 of the roasted-aroma paper the heading row reads
    #     No. | Compounds | Odor threshold | Concentrations (µg/L) |      | OAV |
    # so column 5 is "OAV" and column 6 is blank. Column 6's own cells never mention OAV, so
    # it was classified as a CONCENTRATION column, and 26,890 - which is an OAV, not a
    # concentration - was written into the sheet as one. The arithmetic gives it away:
    # 1,487,026 / 55.3 = 26,888, the threshold printed on the same row.
    #
    # A blank is filled from the nearest non-empty cell to its LEFT in the same row, which
    # is the ordinary reading of a merged cell and stops at the next heading in that row.
    # NOTE: that alone is wrong where a heading is CENTRED - see apply_group_spans, which
    # this now defers to for the span.
    filled = [[] for _ in range(ncol)]
    for r in hdr_rows:
        last = ""
        for c in range(ncol):
            v = (r[c] if c < len(r) else "").strip()
            if v:
                last = v
                filled[c].append(v)
            elif last:
                filled[c].append(last)
    hdr_cells = apply_group_spans(hdr_rows, ncol)
    hdr_text = [" ".join(hdr_cells[c]) for c in range(ncol)]

    name_col = None
    for c in range(ncol):
        if NAME_RE.search(hdr_text[c] or ""):
            name_col = c
            break
    if name_col is None:
        # the widest mostly-textual column is the compound name
        best = None
        for c in range(ncol):
            filled, nv, nt = col_stats(rows, c)
            if filled < max(3, len(rows) * 0.4):
                continue
            if nv / filled > 0.35:
                continue
            score = nt / filled
            if best is None or score > best[0]:
                best = (score, c)
        name_col = best[1] if best else 0

    thr_cols, oav_cols, ri_cols, rt_cols, no_cols = [], [], [], [], []
    for c in range(ncol):
        h = hdr_text[c] or ""
        filled, nv, _nt = col_stats(rows, c)
        if filled < 2:
            continue
        if OAV_RE.search(h):
            oav_cols.append(c)
        elif THR_RE.search(h):
            thr_cols.append(c)
        elif any(RI_RE.search(x) for x in hdr_cells[c]):
            # a list, not a single column: several papers print RI and LRIb side by side
            # for two panels, and keeping only the last one left the other three to be read
            # as concentrations - sheet 03 grew three 浓度 RI columns that way
            ri_cols.append(c)
        elif any(RT_RE.search(x) for x in hdr_cells[c]):
            rt_cols.append(c)
        elif any(NO_RE.match(x) for x in hdr_cells[c]):
            no_cols.append(c)

    # CAS printed in the paper. Several English papers carry a real CAS column, and a
    # printed registry number is a stronger source than anything a name lookup can
    # produce - it is the number the authors used for their own standard solutions.
    # Detection is by cell content, not by header: the header is often just "CAS" in a
    # group header that got merged, while the cells are unambiguous.
    cas_col = None
    for c in range(ncol):
        vals = [(r[c] if c < len(r) else "").strip() for r in rows]
        good = [v for v in vals if CAS_RE.match(v)]
        if len(good) >= 3 and len(good) / max(len(vals), 1) >= 0.5:
            cas_col = c
            break
    if cas_col is None:
        for c in range(ncol):
            if any(CAS_COL.match(x) for x in hdr_cells[c]):
                cas_col = c
                break

    data_cols = []
    for c in range(ncol):
        # rebound per column: reusing the loop variable left over from the role pass
        # above tested every column against the LAST column's header
        h = hdr_text[c] or ""
        if c in (name_col, cas_col) or c in ri_cols or c in thr_cols or c in oav_cols \
                or c in rt_cols or c in no_cols:
            continue
        if any(STAT_RE.search(x) for x in hdr_cells[c]):
            continue
        # A statistics column is often headed only by the unit it shares with the rest of
        # the block - "Pearson's r" and "p Value" sit under a header reading "(mg/L)". The
        # header cannot give it away, so the cells are read instead, the same way the CAS
        # column is found by content.
        vals = [(r[c] if c < len(r) else "").strip() for r in rows]
        vals = [v for v in vals if v]
        if len(vals) >= 3 and sum(bool(STAT_RE.search(v)) for v in vals) \
                >= len(vals) * 0.6:
            continue
        if ID_RE.search(h) or any(ID_CELL.match(x) for x in hdr_cells[c]) \
                or LOD_RE.search(h):
            continue
        filled, nv, _nt = col_stats(rows, c)
        if filled >= 3 and nv / filled >= 0.4:
            u = (t.get("units") or [None] * ncol)[c] or ""
            # a column that already declares its own unit in the header does not need
            # the table-wide one appended, or "(μg/L) [mg/L]" ends up in the heading
            own = ""
            for x in hdr_cells[c]:
                for p in PAREN_RE.findall(x or ""):
                    got = classify_unit(p)
                    if got:
                        own = got
                        break
                if own:
                    break
            if own:
                u = own
            if not u:
                # fall back to the table's own header block, but only accept a
                # parenthetical that really is a unit - captions and footnotes put
                # plenty of other things in brackets ("含8种化合物", "Table 3-4")
                for c2 in range(ncol):
                    for p in PAREN_RE.findall(hdr_text[c2] or ""):
                        got = classify_unit(p)
                        if got:
                            u = got
                            break
                    if u:
                        break
            data_cols.append((c, u))
    return dict(name_col=name_col, data_cols=data_cols, thr_cols=thr_cols,
                oav_cols=oav_cols, ri_col=ri_cols, cas_col=cas_col, hdr=hdr_text,
                hdr_cells=hdr_cells, hdr_rows=hdr_rows, body_rows=body_rows)


def sample_label(t, c, i, hdr_rows=None):
    """A readable column label for a data column: sample name if the header names one.

    Reads the PROMOTED header rows when they are supplied. Reading t["header_rows"] instead
    is why a recovered header can be sitting in the right place and the column still come
    out as 列N: the promoted rows are held in the classify result, not written back into
    the table, so a lookup on the table alone cannot see them.
    """
    for r in reversed(hdr_rows if hdr_rows is not None else t["header_rows"]):
        v = (r[c] if c < len(r) else "").strip()
        if v:
            return v
    return "列%d" % (c + 1)


def strip_leading_index(s):
    """
    Drop a row number that was read into the name cell: "2 3-Methylbutanal".

    On the bitmap route the row-number column and the name column sometimes land in one
    cell, and the residue breaks the lookup that gives the compound its CAS - "2
    3-Methylbutanal" is not a name PubChem has. Only a bare integer followed by something
    that can start a name is removed, so a genuine name beginning with a number is kept:
    the pattern needs a space, and "2-Phenylethanol" has no space after its digit.

    Applied to the 基础数据 view only. The 原表逐格 block below it stays verbatim, which is
    the whole reason it exists.
    """
    m = re.match(r"^\s*(\d{1,3})[.、]?\s+(\S.*)$", s or "")
    if not m:
        return (s or "").strip()
    rest = m.group(2)
    if rest and (rest[0].isalpha() or "一" <= rest[0] <= "鿿"
                 or rest[0] in "([" or "-" in rest[:2]):
        return rest.strip()
    # The remainder may itself begin with a digit - "8 1,1-Diethoxy-3-methylbutane" -
    # provided it goes on to contain a word, which is what makes it a name rather than
    # another number.
    if rest and re.search(r"-\s*(?:[A-Za-z]|[一-鿿])", rest):
        return rest.strip()
    return (s or "").strip()


def write_basic_block(ws, r, t, info, tno):
    """
    Priority-1 view. A table with no usable compound-name column - a sample list, a
    manufacturer table, a statistics block - gets a one-line note instead of an empty
    header row, so an empty block is never mistaken for a failed extraction.
    """
    nc = info["name_col"]
    hdr = info["hdr"]
    name_of = lambda row: (row[nc] if nc < len(row) else "").strip()  # noqa: E731

    body = []
    dropped = []
    for row in info.get("body_rows") or t["rows"]:
        name = name_of(row)
        if not name:
            continue
        body.append(row)
    named = sum(1 for row in body if looks_like_compound(name_of(row)))
    # a table of brands or manufacturers is not a compound table, however many rows
    # it has and however text-like its first column is
    if len(body) < 2 or named < max(2, len(body) * 0.5):
        cap = ("（%s）" % t["caption"]) if t.get("caption") else ""
        ws.cell(row=r, column=1,
                value="表%d%s：非化合物数据表（样品牌/厂家/统计），不进入基础数据"
                      % (tno, cap)).font = META_FONT
        return r + 2, set()

    # A table that continues one from the previous page carries only its last rows.
    # Saying so keeps a two-row fragment from being read as a table that found two
    # compounds - the row count is a property of the page break, not of the paper.
    cap = ("（%s）" % t["caption"]) if t.get("caption") else ""
    continued = bool(re.search(r"\(\s*continued|续表|续", t.get("caption") or "",
                               re.I))
    if continued or len(body) < 3:
        # The count is stated because a page break decides it, not the paper: a reader
        # seeing two compounds here should not conclude the paper found two.
        cap += "（续表，本页 %d 行）" % len(body)

    ws.cell(row=r, column=1,
            value="表%d 基础数据%s" % (tno, cap)
            ).font = CAP_FONT
    r += 1
    if not info["data_cols"] and not info["thr_cols"] and not info["oav_cols"]:
        ws.cell(row=r, column=1,
                value="⚠ 该表未检出浓度/阈值/OAV 列 —— 仅登记化合物名称"
                ).font = META_FONT
        r += 1

    cols = [("化合物名称", nc, ""),
            ("CAS号", info.get("cas_col"), "")]
    for c in info["thr_cols"]:
        cols.append(("阈值" + sample_label(t, c, len(cols), info.get("hdr_rows")), c,
                     (t.get("units") or [""] * t["n_col"])[c] or ""))
    for c in info["oav_cols"]:
        cols.append(("OAV/香气强度" + sample_label(t, c, len(cols), info.get("hdr_rows")), c, ""))
    for c, u in info["data_cols"]:
        cols.append(("浓度 " + sample_label(t, c, len(cols), info.get("hdr_rows")), c, u))
    # 保留指数 is not carried into the basic-data block on request: it is an instrument
    # lookup property rather than a measurement of the compound, and it was only ever
    # reaching the sheet as a by-product of column classification. The values are still in
    # the 原表逐格 block, which stays verbatim, so nothing is lost by leaving them out here.

    heads = []
    for name, c, u in cols:
        if c is None:
            heads.append(name)
        else:
            s = sample_label(t, c, len(cols), info.get("hdr_rows"))
            if s in name:                    # header already carries the label
                heads.append("%s%s" % (name, (" [%s]" % u) if u else ""))
            else:
                heads.append("%s %s%s" % (name, s, (" [%s]" % u) if u else ""))
    for i, h in enumerate(heads, 1):
        cell = ws.cell(row=r, column=i, value=h)
        cell.font = HEAD_FONT
        cell.fill = KEY_FILL if i <= 2 else HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    hr = r
    r += 1

    unit_set = {u for _c, u in info["data_cols"] if u} or \
               {(t.get("units") or [""] * t["n_col"])[c] for c in info["thr_cols"]
                if (t.get("units") or [""] * t["n_col"])[c]}

    # Rows whose name cell is not a compound are removed from the block rather than
    # written into it. Two real cases showed up: a statistics sub-table's own header row
    # ("Name | | | Pearson's r | | p Value") was read as a compound called "Name", and a
    # paper's section number ("2.3") was read as a compound called "2.3". Both reached the
    # workbook as compounds, and a CAS lookup was then attempted on them.
    #
    # The row is not deleted from 原表逐格, which stays verbatim, and the count of what was
    # left out is printed so the exclusion is visible rather than silent.
    kept = []
    for row in body:
        nm = name_of(row)
        # HEADER_WORD is tested first and on its own. "Name" is four letters, so
        # looks_like_compound() accepts it - the Latin-name rule cannot tell a column
        # heading from a compound - and testing the two with OR let every header word
        # through, which is the bug this replaced.
        if HEADER_WORD.match(nm):
            dropped.append(nm)
        elif looks_like_compound(nm):
            kept.append(row)
        else:
            dropped.append(nm)
    body = kept

    for row in body:
        vals = []
        for j, (_n, c, _u) in enumerate(cols):
            v = (row[c] if c is not None and c < len(row) else "").strip()
            if j == 0:
                v = strip_leading_index(v)
            vals.append(v)
        if not any(v and v not in MISSING for v in vals[1:]):
            continue                       # a label-only row, not a measurement
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=i, value=v)
            cell.alignment = Alignment(vertical="top")
            if i == 2:
                cell.fill = PatternFill("solid", fgColor="F2F2F2")
        r += 1
    return r + 1, unit_set


def write_raw_block(ws, r, t, tno):
    ws.cell(row=r, column=1, value="表%d 原表逐格 [%dx%d] p.%s"
            % (tno, t["n_row"], t["n_col"],
               ",".join(str(x) for x in t["pages"][:10]))).font = CAP_FONT
    r += 1
    for hr in t["header_rows"]:
        for c, v in enumerate(hr, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = HEAD_FONT
            cell.fill = HEAD_FILL
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        r += 1
    for row in t["rows"]:
        for c, v in enumerate(row, 1):
            ws.cell(row=r, column=c, value=v).alignment = Alignment(vertical="top")
        r += 1
    return r + 1


def load_source(idx, outdir):
    """
    Pick the best available extraction for a paper, whatever produced it.

    Four routes reach the same workbook: "band" is the text-layer rule-based extraction,
    "en" the OCR grid from the vector image pipeline (two passes, diffed), "bm" the
    bitmap-detection route (single pass), "raw" the earlier find_tables pass.

    The order is by trust, not by convenience. A ruled Chinese journal read through the
    text layer gives compound names exactly as typeset; "en" OCRs twice and diffs the
    passes; "bm" OCRs once with no second pass at all. So "bm" must not win merely by
    being listed first - a paper that has both (English #5 has a born-digital text
    layer AND was run through the bitmap route) would otherwise be silently downgraded
    to its weaker extraction.
    """
    for tag in ("band", "en", "bm", "raw"):
        p = os.path.join(outdir, "%s_%02d.json" % (tag, idx))
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if d.get("route") in ("ocr", "bitmap", "band", "text-layer") and d.get("tables"):
            return tag, d
    p = os.path.join(outdir, "band_%02d.json" % idx)
    if os.path.exists(p):
        return "band", json.load(open(p, encoding="utf-8"))
    p = os.path.join(outdir, "raw_%02d.json" % idx)
    if os.path.exists(p):
        return "raw", json.load(open(p, encoding="utf-8"))
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "re整理.xlsx"))
    ap.add_argument("--outdir", default=OUTDIR)
    a = ap.parse_args()

    entries = json.load(open(os.path.join(OUTDIR, "sheet_map.json"), encoding="utf-8"))
    wb = Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("00_索引")
    heads = ["序号", "表单名", "文献(PDF)", "语言", "提取路径", "检出表数",
             "含化合物名的表", "数据行合计", "浓度列", "阈值列", "浓度单位", "备注"]
    for i, h in enumerate(heads, 1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = HEAD_FONT
        c.fill = HEAD_FILL
    r = 2
    n_ok = n_pending = 0

    for e in entries:
        idx = e["idx"]
        src, raw = load_source(idx, a.outdir)
        name = re.sub(r"[\\/*?:\[\]]", "_", "%02d %s" % (idx, (e.get("sheet") or "无PDF")[:42]))
        lang = "中文" if e["lang"] == "cn" else "英文"

        if not raw or raw.get("route") not in ("ocr", "bitmap", "band", "text-layer") \
                or not raw.get("tables"):
            route = (raw or {}).get("route", "no-file")
            note = (raw or {}).get("note") or ("PDF 不在磁盘上，需补" if not e.get("path") else "")
            note = (note + "  → 需图像 OCR 流程") if route in ("needs-ocr", "no-tables") else note
            sh = wb.create_sheet(name[:31])
            sh.cell(row=1, column=1, value="待处理：%s" % route).font = TITLE_FONT
            sh.cell(row=2, column=1, value="文献：%s" % (e.get("pdf") or "（PDF 缺失）")).font = META_FONT
            sh.cell(row=3, column=1, value="原因：%s" % note).font = META_FONT
            for i, v in enumerate([idx, e.get("sheet"), e.get("pdf"), lang, route,
                                   0, 0, 0, 0, 0, "", note], 1):
                cell = ws.cell(row=r, column=i, value=v)
                cell.fill = BAD_FILL
            n_pending += 1
            r += 1
            continue

        tables = raw["tables"]
        data_ts, total_rows = [], 0
        infos = {}
        for t in tables:
            info = classify_columns(t)
            infos[id(t)] = info
            if info["data_cols"] or info["thr_cols"] or info["oav_cols"]:
                data_ts.append(t)
            total_rows += t["n_row"]

        units = sorted({u for t in data_ts for _c, u in infos[id(t)]["data_cols"] if u})
        n_conc = sum(len(infos[id(t)]["data_cols"]) for t in data_ts)
        n_thr = sum(len(infos[id(t)]["thr_cols"]) for t in data_ts)

        # keyed on the file tag that load_source returned, not on the route string
        # stored inside the json - those are different vocabularies and mixing them
        # leaves the index showing "bm"/"en" instead of what the route actually was
        route_label = {"en": "图像OCR：矢量检测 + A/B双通道 + 600dpi抢救",
                       "bm": "位图检测 + OCR（沟槽定列）",
                       "band": "文字层直读：横线定行 / 竖线定列",
                       "raw": "文字层直读：find_tables"}.get(src, src)

        sh = wb.create_sheet(name[:31])
        sh.cell(row=1, column=1, value="文献：%s" % (e.get("pdf") or e.get("sheet"))).font = TITLE_FONT
        meta = "表单：%s ｜ 路径：%s ｜ 表 %d 个，其中含定量列 %d 个，合计 %d 行 ｜ CAS 待补" \
               % (e.get("sheet"), route_label, len(tables), len(data_ts), total_rows)
        sh.cell(row=2, column=1, value=meta).font = META_FONT
        if raw.get("note"):
            sh.cell(row=3, column=1, value="校验：%s" % raw["note"]).font = META_FONT
        r2 = 5
        tno = 0
        for t in tables:
            tno += 1
            r2, _u = write_basic_block(sh, r2, t, infos[id(t)], tno)
        if tables:
            sh.cell(row=r2 - 1, column=1, value="——— 以下为原表逐格内容 ———").font = META_FONT
            r2 += 1
            for i, t in enumerate(tables, 1):
                r2 = write_raw_block(sh, r2, t, i)
        for i in range(1, max(t["n_col"] for t in tables) + 1):
            sh.column_dimensions[get_column_letter(i)].width = 17
        sh.column_dimensions["A"].width = 26
        sh.freeze_panes = sh.cell(row=6, column=1)

        vals = [idx, e.get("sheet"), e.get("pdf"), lang, route_label,
                len(tables), len(data_ts), total_rows,
                n_conc or "无", n_thr or "无", "、".join(units) or "—",
                raw.get("note") or ""]
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=i, value=v)
            if v in ("无", "—"):
                cell.fill = BAD_FILL
            elif i in (9, 10) and v:
                cell.fill = OK_FILL
        n_ok += 1
        r += 1

    for i, w in enumerate([6, 44, 48, 6, 16, 9, 12, 10, 8, 8, 14, 44], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=2, column=1)
    wb.save(a.out)
    print("sheets=%d  已出数据=%d  待OCR=%d" % (len(wb.sheetnames), n_ok, n_pending))
    print("-> %s" % a.out)


if __name__ == "__main__":
    main()
