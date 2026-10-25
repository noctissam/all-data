# -*- coding: utf-8 -*-
"""Dump the text-layer lines above a table, to read its real header."""
import json
import os
import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8")
mp = json.load(open(os.path.join("out", "re整理", "sheet_map.json"), encoding="utf-8"))

WANT = [(21, 37), (21, 39), (26, 58), (26, 62), (26, 63), (28, 4)]

for idx, page in WANT:
    pdf = [e["path"] for e in mp if e.get("idx") == idx][0]
    doc = pymupdf.open(pdf)
    pg = doc[page - 1]
    lines = {}
    for w in pg.get_text("words"):
        lines.setdefault(round(w[1], 0), []).append(w)
    print("=" * 96)
    print("idx=%d page=%d" % (idx, page))
    for y in sorted(lines)[:26]:
        ws = sorted(lines[y], key=lambda w: w[0])
        print("  y=%6.1f  %s" % (y, " | ".join("%.0f:%s" % (w[0], w[4]) for w in ws)[:185]))
    doc.close()