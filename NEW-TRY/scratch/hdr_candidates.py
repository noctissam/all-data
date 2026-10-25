# -*- coding: utf-8 -*-
"""Print every candidate header line for one table, with the scoring detail."""
import json
import os
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scratch")
sys.stdout.reconfigure(encoding="utf-8")

import pymupdf            # noqa: E402
import extract_band as E  # noqa: E402
from recover_headers import col_of, group_lines, match_table, pdf_for  # noqa: E402

IDX, TI = int(sys.argv[1]), int(sys.argv[2])

band = json.load(open("out/re整理/band_%02d.json" % IDX, encoding="utf-8"))["tables"][TI]
page_no = (band.get("pages") or [None])[0]
doc = pymupdf.open(pdf_for(IDX))
pg = doc[page_no - 1]
t = match_table(E.page_tables(pg), band)
b, (x_lo, y_lo, x_hi, y_hi) = t["bounds"], t["bbox"]
print("page %d  bounds=%s" % (page_no, [round(x, 1) for x in b]))
print("bbox=%s" % [round(x, 1) for x in (x_lo, y_lo, x_hi, y_hi)])

words = [w for w in pg.get_text("words")
         if y_lo - 2 <= w[1] <= y_hi and x_lo - 2 <= w[0] <= x_hi + 2]
lines = group_lines(words)

body_sig = None
for r in band.get("rows", []):
    cells = [str(x or "").strip() for x in r if str(x or "").strip()]
    if cells:
        body_sig = cells[:2]
        break
print("body_sig =", body_sig)

data_y = None
for y, ws in lines:
    texts = [w[4].strip() for w in ws]
    if all(any(x == t2 or x in t2 for t2 in texts) for x in body_sig):
        data_y = y
        break
print("data_y =", data_y)
print()
for y, ws in lines:
    if data_y is not None and y > data_y + 2:
        continue
    cells = {}
    for w in ws:
        c = col_of((w[0] + w[2]) / 2, b)
        if c is not None and c not in cells:
            cells[c] = w[4].strip()
    if not cells:
        continue
    mx = max(len(v) for v in cells.values())
    print("y=%7.1f d=%6.1f cols=%d maxlen=%2d  %s"
          % (y, data_y - y if data_y else 0, len(cells), mx,
             json.dumps(cells, ensure_ascii=False)[:130]))
doc.close()