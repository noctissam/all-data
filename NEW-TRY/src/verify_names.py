# -*- coding: utf-8 -*-
"""
List the name cells that are not compound names.

A cell in the 化合物名称 column should hold a compound name. Three kinds of cell do not,
and each means a different fault upstream:

  a bare number          the row's columns were shifted, or a retention index landed in
                         the name column.
  a number run           the table row was never split into columns, so the whole row is
                         sitting in the first one.
  running prose          body text from the paper, not a table cell at all.

They are listed with the sheet and row so they can be looked at, because a name that is
not a name poisons everything computed from the row.

Run: python verify_names.py
"""

import argparse
import re
import sys
from collections import Counter

sys.path.insert(0, "src")

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")

XLSX = "out/re整理/re整理.xlsx"
# The block finder is shared: a 基础数据 block is identified by having both the name
# column and the CAS column, which the writer always emits. 化合物名称 alone is not
# enough - it also appears as a header row inside the verbatim block.
import blocks  # noqa: E402

BARE_NUM = re.compile(r"^\s*[<>]?\s*\d+(?:[.,]\d+)*\s*(?:[a-zA-Z%°/]*)\s*$")
LATIN = re.compile(r"[A-Za-z]{3,}")
LEADING_INDEX = re.compile(r"^\s*\d{1,3}[.、]?\s+\S")
TRAILING_NUMBERS = re.compile(r"^\S+\s+\d[\d.,]*\s+\d[\d.,±]*")

# Prose has to be told apart from a name, and the first attempt at this over-reported:
# a match on any Chinese comma flagged 2,4-二甲基苯酚. It now needs both a length that no
# compound name reaches and a phrase that only appears in a sentence.
PROSE = re.compile(r"(通常|因此|表明|具有|赋予|研究|方法|结果|讨论|结论|样品|"
                   r"酒中|香气特征|风味特征)")


def kind_of(s):
    if BARE_NUM.match(s):
        return "bare-number"
    if LEADING_INDEX.match(s):
        # should be gone: write_basic_block strips a row number read into this cell
        return "leading-index"
    if len(s) >= 20 and PROSE.search(s):
        return "prose"
    if TRAILING_NUMBERS.search(s):
        return "number-run"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="also write the report here, in UTF-8")
    a = ap.parse_args()
    import report_out
    sys.stdout = report_out.open_report(a.out)

    import openpyxl
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    kinds = Counter()
    per_sheet = Counter()
    listed = []
    for sn in wb.sheetnames:
        if sn == "00_索引":
            continue
        rows = list(wb[sn].iter_rows(values_only=True))
        for start, stop in blocks.find_data_blocks(rows):
            for r in rows[start + 1:stop]:
                a0 = str(r[0] or "") if r else ""
                s = a0.strip()
                if not s:
                    continue
                k = kind_of(s)
                if k:
                    kinds[k] += 1
                    per_sheet[sn] += 1
                    listed.append((sn, start + 2, k, s))
    wb.close()

    print("=" * 70)
    print("NAME CELLS THAT ARE NOT COMPOUND NAMES   %d" % len(listed))
    print("=" * 70)
    for k, n in kinds.most_common():
        print("   %-14s %d" % (k, n))
    print()
    print("affected sheets:")
    for sn, n in per_sheet.most_common(12):
        print("   %-24s %d" % (sn[:24], n))
    print()
    print("first 40 of each kind:")
    for k in kinds:
        shown = [x for x in listed if x[2] == k][:12]
        print("   --- %s" % k)
        for sn, ri, _k, s in shown:
            print("       %-20s row %-5d %s" % (sn[:20], ri, s[:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())