# -*- coding: utf-8 -*-
"""Dump the header rows and first data rows of every table that still has unnamed columns."""
import importlib.util
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
spec = importlib.util.spec_from_file_location("b", "src/build_rec整理.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

TARGETS = [(21, 2), (21, 6), (21, 8), (24, 1), (26, 7), (26, 21), (26, 22)]

for idx, ti in TARGETS:
    f = os.path.join("out", "re整理", "band_%02d.json" % idx)
    d = json.load(open(f, encoding="utf-8"))
    if ti >= len(d["tables"]):
        print("band_%02d has no t%d (%d tables)" % (idx, ti, len(d["tables"])))
        continue
    t = d["tables"][ti]
    info = B.classify_columns(t)
    tg = [c for c, _ in info["data_cols"]
          if B.sample_label(t, c, 0, info.get("hdr_rows")).startswith("列")]
    print("=" * 78)
    print("band_%02d t%-2d pages=%s  ncol=%s  无名列=%s"
          % (idx, ti, t.get("pages"), t.get("n_col"), tg))
    print("  caption: %s" % str(t.get("caption", ""))[:60])
    for r in (info.get("hdr_rows") or [])[:5]:
        print("   H %s" % json.dumps(r, ensure_ascii=False)[:150])
    for r in (info.get("body_rows") or [])[:3]:
        print("   R %s" % json.dumps(r, ensure_ascii=False)[:150])