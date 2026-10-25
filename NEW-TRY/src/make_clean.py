# -*- coding: utf-8 -*-
"""
Build 清洗后数据.xlsx - the flat, cleaned extract.

What this produces, and why it is shaped this way:

  Long, not wide.  A table in these papers measures one compound across several samples
  (LZ-2016 base SAB / GJ-1573 / ...), so a wide sheet needs one column per sample and the
  column set differs from paper to paper - twenty-odd ragged columns that cannot be read as
  a table.  One row per (paper, compound, sample) is four fixed columns instead.

  Only 文献名 + the measurements.  No title block, no index sheet, no note rows, no units
  row: a header line and the data.

  One number per cell.  The papers print mean ± standard deviation, sometimes with a
  superscript significance letter ("0.25b"), and sometimes with a thin-space thousands
  separator.  All of that is stripped so the column is numeric and can be summed, averaged
  or plotted without touching it again.

Cleaning rules, applied in this order:
  1. take the mean side of "x ± y"
  2. drop a trailing significance letter, but ONLY when what remains is a number -
     otherwise "ND" would be silently reduced to an empty cell, which turns "not detected"
     into "no data"
  3. drop thousands separators and spaces inside the number
  4. anything still not numeric is kept verbatim (ND, <1, tr, -), because throwing it away
     would lose a reported value

Usage:
    python src/make_clean.py [--src out/re整理/re整理.xlsx] [--out 清洗后数据.xlsx]
"""
import argparse
import importlib.util
import json
import os
import re
import sys

import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

sys.stdout.reconfigure(encoding="utf-8")

# The compound test lives in the builder, whose filename is Chinese and so cannot be
# imported by name. Loaded by path so this script and the builder cannot drift apart: a
# second, looser copy of the test here would let through rows the workbook already treats
# as labels.
HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "builder", os.path.join(HERE, "build_rec整理.py"))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)

# "ND ND" -> "ND". Two adjacent cells carrying the same marker arrive merged as one cell on
# the OCR route; the repeat is not information.
DUP_TOKEN = re.compile(r"^(\S+)(?:\s+\1)+$")

HEAD_FILL = None
NUM_RE = re.compile(r"^[\d.]+(?:[eE][-+]?\d+)?$")
# "0.25b" -> "0.25"; guarded by requiring digits in front, so "ND" and "tr" are untouched
TAIL_ALPHA = re.compile(r"^([\d][\d.,]*)\s*[A-Za-z]+\s*$")
THIN = "    "


def clean_value(v):
    """
    Reduce one cell to the single number it reports.

    Returns a float when the result is numeric, otherwise the cleaned text.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    s = re.split("[±]", s, 1)[0].strip()
    m = TAIL_ALPHA.match(s)
    if m:
        s = m.group(1)
    for ch in THIN + " ":
        s = s.replace(ch, "")
    s = s.replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        m = DUP_TOKEN.match(s)
        return m.group(1) if m else s


# What counts as a reported measurement, once the spread notation is gone.
#
# Two-panel tables put a category or a method note in the right half, and that half ends up
# classified as a concentration column because it sits where values sit. What fills those
# cells is 水果香, LLME-GC-MS, "MS, RI, odor, Std", 沂蒙老区 - 4961 cells of it. They are not
# measurements and keeping them leaves a numeric column with a quarter of its entries as
# prose.
#
# Accepted: a number, a bounded number ("<1", ">0.1", "<q.l."), and the standard
# not-detected spellings. Everything else is dropped rather than guessed at.
BOUNDED = re.compile(r"^[<>≤≥]\s*[\d.]+(?:\s*q\.?\s*l\.?)?$", re.I)
NOT_DETECTED = re.compile(
    r"^(?:n\.?\s*d\.?|nd|na|n\.a|tr|trace|tc|not\s*detected|not\s*found|"
    r"未检出|未检测|未测出|未定量|未定量检出|[-–—/])$", re.I)


def clean_title(s, fallback=""):
    """
    The 文献 line of a sheet is not a title: it carries the table number, the file
    extension, and for the Chinese papers the author.

        "文献：2  Characterization of key odorants ... in.pdf"
        "文献：三种香型白酒的ICP-OES和GC-QTOF_MS分析及判别研究_卓俊纳.pdf"

    becomes a plain title. The author is stripped only when it is CJK, because
    GC-QTOF_MS also contains an underscore and cutting on "_" would leave
    "三种香型白酒的ICP-OES和GC".

    The leading number is NOT stripped here. It is ambiguous - "28  酱香型和浓香型…" is the
    table number, but "3 个年份浓香型白酒香气成分比较研究" has a 3 that belongs to the title,
    and a rule that removed it turned that paper into "个年份浓香型白酒…". Titles come from
    the source PDF's filename instead; this is only the fallback.
    """
    s = re.sub(r"^\s*[:：]\s*", "", s)        # the caller has already cut "文献"
    s = re.sub(r"^\s*\d{1,2}\s+(?=[一-鿿A-Za-z])", "", s)
    s = re.sub(r"\.pdf\s*$", "", s, flags=re.I)
    s = re.sub(r"_[一-鿿]{1,8}\s*$", "", s)   # _作者名, and only that
    s = s.strip(" ._-")
    return s or fallback


def title_map(reout):
    """
    Sheet index -> the source PDF's own filename, minus extension and author.

    Authoritative and complete, which the 文献 line is not: it is built from the caption of
    whichever table the sheet is named after, so it is truncated wherever that caption was.

    The English filenames carry their bibliography number ("5  Impact of Pulsed Electric
    Fields…"). Two or more spaces is what separates that from a title that genuinely begins
    with a digit - "3个年份浓香型白酒…" has no space and is left alone.
    """
    out = {}
    p = os.path.join(reout, "sheet_map.json")
    if not os.path.exists(p):
        return out
    for e in json.load(open(p, encoding="utf-8")):
        path = e.get("path") or ""
        if not path:
            continue
        name = os.path.splitext(os.path.basename(path))[0]
        name = re.sub(r"^\d{1,3}\s{2,}", "", name)
        name = re.sub(r"_[一-鿿]{1,8}$", "", name)
        out[e.get("idx")] = name.strip()
    return out


def is_measurement(v):
    if isinstance(v, float):
        return True
    s = str(v or "").strip()
    if not s:
        return False
    return bool(BOUNDED.match(s) or NOT_DETECTED.match(s))


def sample_name(header, prefix):
    """
    "浓度 GJ-1573 [μg/l]" -> "GJ-1573"; "浓度 优级" -> "优级".

    The unit is dropped because it is now implied by the column header, and keeping it would
    make every sample name a different string.
    """
    s = str(header or "").strip()
    if s.startswith(prefix):
        s = s[len(prefix):].strip()
    s = re.sub(r"\[[^\]]*\]\s*$", "", s).strip()
    s = re.sub(r"[（(][^)）]*[)）]\s*$", "", s).strip()
    return s or str(header or "").strip()


def is_header_row(cells):
    return bool(cells) and str(cells[0] or "").strip().startswith("化合物名称")


# Markers that close the current block. Everything else inside a 基础数据 block is data.
BLOCK_END = ("逐格", "校验", "文献", "原表")


def extract(src):
    wb = openpyxl.load_workbook(src, data_only=True)
    titles = title_map(os.path.join(HERE, "..", "out", "re整理"))
    rows = []
    papers = 0
    skipped_blocks = 0
    label_rows = 0
    noise = 0

    for sn in wb.sheetnames:
        if sn == "00_索引":
            continue
        title = ""
        blocks = []
        cur = None
        try:
            idx = int(str(sn).strip()[:2])
        except ValueError:
            idx = None
        from_file = titles.get(idx, "")

        for row in wb[sn].iter_rows(values_only=True):
            cells = list(row)
            first = str(cells[0] or "").strip() if cells else ""

            if not title and first.startswith("文献"):
                title = clean_title(first[len("文献"):], sn)

            if "基础数据" in first:
                cur = {"caption": first, "head": None, "data": []}
                blocks.append(cur)
                continue

            if cur is None:
                continue

            if any(m in first for m in BLOCK_END):
                cur = None
                continue

            if cur["head"] is None:
                if is_header_row(cells):
                    cur["head"] = cells
                continue

            if not first:
                continue
            row_s = [str(x).strip() if x is not None else "" for x in cells]
            if sum(1 for x in row_s if x) < 2:
                continue
            cur["data"].append(cells)

        for b in blocks:
            head = b["head"]
            if head is None:
                continue
            head_s = [str(x or "") for x in head]
            # 化合物名称 | CAS号 | CAS核对 | 阈值… | OAV/香气强度… | 浓度 …
            #
            # All three measures go into the same long table, tagged by 数据类型. They are
            # the same shape - one value per sample - and they belong to the same row of the
            # paper, so splitting them into separate sheets would mean re-joining them on the
            # compound name anyway. The tag is what keeps them from being averaged together.
            meas = []
            for j, h in enumerate(head_s):
                for kind, pre in (("浓度", "浓度"),
                                  ("OAV", "OAV/香气强度"),
                                  ("阈值", "阈值")):
                    if not h.startswith(pre):
                        continue
                    label = sample_name(h, pre)
                    if not label or label.startswith("列"):
                        label = ""
                    meas.append((j, kind, label))
                    break
            if not meas:
                skipped_blocks += 1
                continue
            conc = meas

            cas_col = 1 if len(head_s) > 1 and head_s[1].startswith("CAS") else None
            papers += 1
            for d in b["data"]:
                name = str(d[0] or "").strip()
                if not name:
                    continue
                # Group-label rows ride along with the measurements: 水果香, 花香, 酱香,
                # IS8, LLME-GC-MS, "MS, RI, odor, Std", 沂蒙老区. They are a class heading or
                # a method note, not a substance, and they carry no measurement of their own -
                # what sits beside them is the internal-standard row or a blank. Emitting
                # them puts 4961 rows of non-numbers into the value column.
                if not B.looks_like_compound(name):
                    label_rows += 1
                    continue
                cas = ""
                if cas_col is not None and cas_col < len(d):
                    cas = str(d[cas_col] or "").strip()
                for j, kind, label in conc:
                    if j >= len(d):
                        continue
                    val = clean_value(d[j])
                    if val is None:
                        continue
                    if not is_measurement(val):
                        noise += 1
                        continue
                    rows.append((from_file or title or sn, name, cas, kind, label, val))

    wb.close()
    return rows, papers, skipped_blocks, label_rows, noise


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))
    ap.add_argument("--src", default=os.path.join(here, "..", "out", "re整理",
                                                   "re整理.xlsx"))
    ap.add_argument("--out", default=os.path.join(root, "清洗后数据.xlsx"))
    a = ap.parse_args()

    rows, papers, skipped, label_rows, noise = extract(a.src)
    print("源文件: %s" % a.src)
    print("含浓度列的表块: %d   无浓度列而略过: %d" % (papers, skipped))
    print("剔除的分类行/方法名行: %d" % label_rows)
    print("剔除的非测量值格（分类/方法名/说明）: %d" % noise)
    print("数据行: %d" % len(rows))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "清洗后数据"
    heads = ["文献名", "化合物", "CAS号", "数据类型", "样品", "数值"]
    bold = Font(bold=True)
    for j, h in enumerate(heads, 1):
        c = ws.cell(row=1, column=j, value=h)
        c.font = bold
        c.alignment = Alignment(vertical="center")

    for i, r in enumerate(rows, 2):
        for j, v in enumerate(r, 1):
            ws.cell(row=i, column=j, value=v)

    for j, w in enumerate((46, 32, 14, 10, 26, 14), 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"
    if HEAD_FILL:
        for j in range(1, len(heads) + 1):
            ws.cell(row=1, column=j).fill = HEAD_FILL

    wb.save(a.out)
    print("-> %s  (%d 行 x %d 列, %.0f KB)"
          % (a.out, len(rows), len(heads), os.path.getsize(a.out) / 1024.0))


if __name__ == "__main__":
    main()