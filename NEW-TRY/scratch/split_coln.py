# -*- coding: utf-8 -*-
"""For each still-unnamed data column: is it a DEAD column (no data at all) or a NAMED one?"""
import glob
import importlib.util
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
spec = importlib.util.spec_from_file_location("b", "src/build_rec整理.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

dead_total = named_total = 0
print("%-16s %-28s %s" % ("表", "列", "判定"))
for f in sorted(glob.glob("out/re整理/band_*.json")):
    if ".orig." in f:
        continue
    idx = int(os.path.basename(f)[5:7])
    d = json.load(open(f, encoding="utf-8"))
    for ti, t in enumerate(d["tables"]):
        try:
            info = B.classify_columns(t)
        except Exception:
            continue
        tg = [c for c, _ in info["data_cols"]
              if B.sample_label(t, c, 0, info.get("hdr_rows")).startswith("列")]
        if not tg:
            continue
        body = info.get("body_rows") or t.get("rows") or []
        for c in tg:
            filled = sum(1 for r in body
                         if c < len(r) and str(r[c] or "").strip())
            nums = sum(1 for r in body
                       if c < len(r) and B.NUMBERISH.match(str(r[c] or "").strip()))
            kind = "空列(应剔除)" if filled == 0 else \
                   "有值但无名(%d格/%d数值)" % (filled, nums)
            if filled == 0:
                dead_total += 1
            else:
                named_total += 1
            print("band_%02d t%-3d      col%-3d %s   %s"
                  % (idx, ti, c, kind, str(t.get("caption", ""))[:22]))

print()
print("空列 %d 个，有值但无名 %d 个" % (dead_total, named_total))