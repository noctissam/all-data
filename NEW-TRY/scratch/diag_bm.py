# -*- coding: utf-8 -*-
"""Diagnose the 列N columns on the bitmap route, with the grid geometry that explains them."""
import importlib.util
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
spec = importlib.util.spec_from_file_location("b", "src/build_rec整理.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

TARGET = [2, 11, 27, 32]
for idx in TARGET:
    p = os.path.join("out", "re整理", "bm_%02d.json" % idx)
    if not os.path.exists(p):
        continue
    d = json.load(open(p, encoding="utf-8"))
    for ti, t in enumerate(d.get("tables") or []):
        try:
            info = B.classify_columns(t)
        except Exception as e:
            print("bm_%02d t%d classify failed: %s" % (idx, ti, e))
            continue
        tg = [(c, u) for c, u in info["data_cols"]
              if B.sample_label(t, c, 0, info.get("hdr_rows")).startswith("列")]
        if not tg:
            continue
        print("=" * 96)
        print("bm_%02d t%-2d pages=%s ncol=%s  无名列=%s"
              % (idx, ti, t.get("pages"), t.get("n_col"), [c for c, _ in tg]))
        for r in (info.get("hdr_rows") or [])[:6]:
            print("   H %s" % json.dumps(r, ensure_ascii=False)[:170])
        body = info.get("body_rows") or t.get("rows") or []
        for r in body[:3]:
            print("   R %s" % json.dumps(r, ensure_ascii=False)[:170])
        for c, u in tg:
            filled = sum(1 for r in body if c < len(r) and str(r[c] or "").strip())
            ex = next((str(r[c]) for r in body if c < len(r) and str(r[c] or "").strip()), "")
            print("     col%-3d %d格  例=%r" % (c, filled, ex[:44]))