# -*- coding: utf-8 -*-
"""Prototype: recover one lost column header from the PDF text layer."""
import json
import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import pymupdf          # noqa: E402
import extract_band as E  # noqa: E402
sys.path.insert(0, "scratch")
from _pdfidx import pdf_for  # noqa: E402

IDX, TI, COL = 12, 0, 3

band = json.load(open("out/re整理/band_%02d.json" % IDX, encoding="utf-8"))["tables"][TI]
page_no = (band.get("pages") or [None])[0]
pdf = pdf_for(IDX)
doc = pymupdf.open(pdf)
pg = doc[page_no - 1]
tables = E.page_tables(pg)
print("page %d: page_tables found %d" % (page_no, len(tables)))
for k, t in enumerate(tables):
    same = [r for r in t["rows"] if r and str(r[0] or "").strip()]
    print("  cand %d bbox=%s n_col=%s first_row=%s"
          % (k, [round(x, 1) for x in t["bbox"]], t["n_col"],
             json.dumps(same[0], ensure_ascii=False)[:90] if same else "-"))

t = tables[0]
b = t["bounds"]
print("\nbounds:", [round(x, 1) for x in b])
lo, hi = b[COL], b[COL + 1]
words = [w for w in pg.get_text("words")
         if lo <= (w[0] + w[2]) / 2 < hi]
words.sort(key=lambda w: w[1])
print("\nwords in column %d (x %.0f..%.0f):" % (COL, lo, hi))
for w in words[:14]:
    print("   y=%7.1f x0=%6.1f  %s" % (w[1], w[0], w[4]))
doc.close()