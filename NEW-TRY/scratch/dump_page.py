# -*- coding: utf-8 -*-
"""Show the text-layer lines around a table, to see what the paper actually prints."""
import json
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scratch")
sys.stdout.reconfigure(encoding="utf-8")

import pymupdf            # noqa: E402
import extract_band as E  # noqa: E402
from recover_headers import group_lines, match_table, pdf_for  # noqa: E402

IDX, TI = int(sys.argv[1]), int(sys.argv[2])
band = json.load(open("out/re整理/band_%02d.json" % IDX, encoding="utf-8"))["tables"][TI]
page_no = (band.get("pages") or [None])[0]
doc = pymupdf.open(pdf_for(IDX))
pg = doc[page_no - 1]
t = match_table(E.page_tables(pg), band)
print("page %d bounds=%s" % (page_no, [round(x, 1) for x in t["bounds"]]))
print("rows:")
for r in band.get("rows", [])[:4]:
    print("   ", json.dumps(r, ensure_ascii=False)[:130])
print()
print("--- text layer ---")
for y, ws in group_lines(pg.get_text("words")):
    ws = sorted(ws, key=lambda w: w[0])
    print("y=%7.1f  %s" % (y, " | ".join("%.0f:%s" % (w[0], w[4]) for w in ws)[:190]))
doc.close()