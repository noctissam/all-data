# -*- coding: utf-8 -*-
"""Show the header cells of a band table, with the role regexes applied."""
import json
import os
import re
import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")

idx = int(sys.argv[1])
ti = int(sys.argv[2]) if len(sys.argv) > 2 else 0
d = json.load(open(os.path.join("out", "re整理", "band_%02d.json" % idx), encoding="utf-8"))
t = d["tables"][ti]
print("caption:", str(t.get("caption", ""))[:60])
print("n_col:", t.get("n_col"), " roles:", t.get("roles"))
print("header:", json.dumps(t.get("header"), ensure_ascii=False))
for i, hr in enumerate(t.get("header_rows") or []):
    for j, c in enumerate(hr):
        if str(c or "").strip():
            print("  hdr[%d][%d] = %r" % (i, j, c))

sys.path.insert(0, "src")
import build_rec整理 as B   # noqa: E402
print()
print("RI_RE  =", B.RI_RE.pattern)
print("LOD_RE =", B.LOD_RE.pattern)
hdr = t.get("header") or []
for j, c in enumerate(hdr):
    s = str(c or "")
    print("  col%-2d %-28r RI=%-5s LOD=%-5s THR=%-5s"
          % (j, s[:28], bool(B.RI_RE.search(s)), bool(B.LOD_RE.search(s)),
             bool(B.THR_RE.search(s))))