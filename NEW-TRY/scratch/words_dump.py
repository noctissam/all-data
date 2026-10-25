# -*- coding: utf-8 -*-
"""
Dump the text-layer words with coordinates for one region of a page.

Used to see whether a compound name is one word or several, and where the next column
starts - the band grid drops the tail of a name when the name is split across words and the
column boundary is drawn between them rather than after them.
"""
import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import pymupdf   # noqa: E402

pdf, page = sys.argv[1], int(sys.argv[2])
y0 = float(sys.argv[3]) if len(sys.argv) > 3 else None
y1 = float(sys.argv[4]) if len(sys.argv) > 4 else None

doc = pymupdf.open(pdf)
p = doc[page - 1]
for w in p.get_text("words"):      # x0, y0, x1, y1, word, block, line, wordno
    x0, yy0, x1, yy1, word = w[0], w[1], w[2], w[3], w[4]
    if y0 is not None and not (y0 <= yy0 <= (y1 or y0)):
        continue
    print("x0=%7.2f x1=%7.2f y0=%7.2f  %s" % (x0, x1, yy0, word))
doc.close()