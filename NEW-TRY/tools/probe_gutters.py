# -*- coding: utf-8 -*-
"""Probe the gutter statistics of a known table region, to calibrate the detector."""
import sys

import numpy as np
import pymupdf
from PIL import Image

sys.path.insert(0, "src")
import cn_detect_tables as D  # noqa: E402

pdf = sys.argv[1]
page_no = int(sys.argv[2])
y0_pt = float(sys.argv[3])
y1_pt = float(sys.argv[4])
dpi = int(sys.argv[5]) if len(sys.argv) > 5 else 150

doc = pymupdf.open(pdf)
page = doc[page_no - 1]
arr = D.page_array(page, dpi)
s = dpi / 72.0
y0, y1 = int(y0_pt * s), int(y1_pt * s)
print("region px y%d-%d  (%d rows of %d)" % (y0, y1, y1 - y0, arr.shape[0]))

rowink = (arr[y0:y1] < 128)
rows = rowink.mean(axis=1) > 0.004
print("inked text rows: %d" % rows.sum())
ink = rowink[rows].mean(axis=0)
cols = np.where(ink > 0.004)[0]
a, b = int(cols.min()), int(cols.max())
nrows = int(rows.sum())

print("text block x%d-%d (width %d)" % (a, b, b - a))
for thr in (0.004, 0.01, 0.02, 0.04, 0.08):
    prof = ink[a:b + 1]
    blank = prof <= thr
    strips = []
    i = 0
    while i < len(blank):
        if not blank[i]:
            i += 1
            continue
        j = i
        while j < len(blank) and blank[j]:
            j += 1
        if j - i >= 12:
            strips.append((a + i, a + j, j - i))
        i = j
    cons = []
    for x0, x1, w in strips:
        c = float((~rowink[rows][:, x0:x1 + 1].any(axis=1)).sum()) / nrows
        cons.append((x0, w, round(c, 2)))
    print("  thr=%.3f  strips>=12px: %-3d  %s" % (thr, len(strips), cons[:8]))

