# -*- coding: utf-8 -*-
"""Compound names that look like the first fragment of a wrapped name.

A name printed across two or three baselines leaves a piece that ends mid-word: 3-乙基-,
亚油酸乙, 三甲基吡. None of them is a substance, and each resolves to a real-looking CAS,
which is what makes them worth hunting.
"""
import collections
import os
import re
import sys

import openpyxl

sys.stdout.reconfigure(encoding="utf-8")
P = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月\re整理.xlsx"

COMPLETE = r"(酯|醇|酸|醛|酮|酚|醚|烯|烷|腈|肼|吡嗪|内酯|硫|胺|腙)$"
# ends mid-word: a trailing 基/甲/乙/二 with no functional group behind it
FRAGMENT = re.compile(r"(?:基|甲|乙|二|[\d,]|[A-Za-z])\s*$")
COMPLETE_RE = re.compile(COMPLETE)

wb = openpyxl.load_workbook(P, data_only=True, read_only=True)
frag = collections.Counter()
cas = {}
for sn in wb.sheetnames:
    if sn == "00_索引":
        continue
    head = None
    for row in wb[sn].iter_rows(values_only=True):
        cells = list(row)
        first = str(cells[0] or "").strip()
        if "基础数据" in first:
            head = None
            continue
        if head is None:
            if first.startswith("化合物名称"):
                head = [str(x or "") for x in cells]
            continue
        if not first:
            continue
        cjk = re.search(r"[一-鿿]", first)
        if not cjk:
            continue
        if COMPLETE_RE.search(first):
            continue
        if FRAGMENT.search(first) and len(first) <= 8:
            frag[first] += 1
            cas.setdefault(first, str(cells[1] or "").strip())
wb.close()

print("疑似半截名字：%d 种 / %d 次" % (len(frag), sum(frag.values())))
for n, k in frag.most_common(40):
    print("   %-22s x%-3d  CAS=%s" % (n, k, cas.get(n) or "-"))