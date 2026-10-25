# -*- coding: utf-8 -*-
"""Render a page's header region so a disputed column layout can be read directly."""
import json
import os
import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8")
idx = int(sys.argv[1])
page_no = int(sys.argv[2])
frac = float(sys.argv[3]) if len(sys.argv) > 3 else 0.13

mp = json.load(open(os.path.join("out", "re整理", "sheet_map.json"), encoding="utf-8"))
pdf = [e["path"] for e in mp if e.get("idx") == idx][0]
doc = pymupdf.open(pdf)
pg = doc[page_no - 1]

words = pg.get_text("words")
if not words:
    print("no text layer")
    raise SystemExit
# the table region is where the words are densest; use the full text block for the page
y0 = min(w[1] for w in words)
y1 = max(w[3] for w in words)
clip = pymupdf.Rect(0, y0, pg.rect.x1, y0 + (y1 - y0) * frac)
outdir = os.path.join("scratch", "render")
os.makedirs(outdir, exist_ok=True)
p = os.path.join(outdir, "p%02d_%02d.png" % (idx, page_no))
pix = pg.get_pixmap(matrix=pymupdf.Matrix(3.2, 3.2), clip=clip)
pix.save(p)
print(p, pix.width, "x", pix.height)
doc.close()