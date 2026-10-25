# -*- coding: utf-8 -*-
"""Render the header region of an OCR-route table so the real column labels can be read."""
import json
import os
import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8")

idx = int(sys.argv[1])
grid = sys.argv[2]
outdir = os.path.join("scratch", "render")
os.makedirs(outdir, exist_ok=True)

mp = json.load(open(os.path.join("out", "re整理", "sheet_map.json"), encoding="utf-8"))
pdf = [e["path"] for e in mp if e.get("idx") == idx][0]

g = json.load(open(os.path.join("out", grid), encoding="utf-8"))
rect = pymupdf.Rect(g["src_pdf_rect"])

doc = pymupdf.open(pdf)
pg = doc[g["page"] - 1]
# the header sits at the top of the table rectangle
top = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + (rect.y1 - rect.y0) * 0.13)
pix = pg.get_pixmap(matrix=pymupdf.Matrix(3.4, 3.4), clip=top)
p = os.path.join(outdir, "hdr_%s_p%02d.png" % (os.path.basename(grid).split("_")[0],
                                               g["page"]))
pix.save(p)
print(p, pix.width, "x", pix.height)
doc.close()