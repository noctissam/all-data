# -*- coding: utf-8 -*-
"""The real list of data columns the builder ends up labelling 列N.

Checks after promote_header_rows(), which is what the builder actually uses - the raw
header_rows in the band file is not the same thing, because extract_band files a dozen lines
of body prose as the header while the real header sits in rows[0].
"""
import glob
import importlib.util
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
spec = importlib.util.spec_from_file_location("b", "src/build_rec整理.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

found = []
for f in sorted(glob.glob("out/re整理/band_*.json")):
    if ".orig." in f:
        continue
    idx = os.path.basename(f)[5:7]
    d = json.load(open(f, encoding="utf-8"))
    for ti, t in enumerate(d.get("tables", [])):
        try:
            info = B.classify_columns(t)
        except Exception as e:
            print("  band_%s t%d classify failed: %s" % (idx, ti, e))
            continue
        cols = []
        for c, _u in info["data_cols"]:
            if B.sample_label(t, c, 0, info.get("hdr_rows")).startswith("列"):
                cols.append(c)
        if cols:
            found.append((idx, ti, t.get("pages"), cols, info["ncol"] if "ncol" in info
                          else t.get("n_col"), str(t.get("caption", ""))[:34],
                          t.get("has_name")))

print("最终仍被标成 列N 的数据列：%d 张表" % len(found))
for r in found:
    print("  band_%s t%-3d pages=%-12s 列 %s (共%s列) 有名字列=%s  %s"
          % (r[0], r[1], str(r[2]), r[3], r[4], r[6], r[5]))