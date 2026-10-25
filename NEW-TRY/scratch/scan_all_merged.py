# -*- coding: utf-8 -*-
"""Count merged cells (one OCR box spanning several printed columns) in every band file."""
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))

NUM = r"[-+]?\d[\d,]*\.?\d*"
MERGED = re.compile(r"^(?P<head>.*\S)\s+(?P<n1>%s)\s+(?P<n2>%s)(?P<rest>.*)$" % (NUM, NUM))

total = 0
for f in sorted(glob.glob(os.path.join(REOUT, "band_*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    idx = os.path.basename(f)[5:7]
    out = []
    for ti, t in enumerate(d["tables"]):
        n = sum(1 for row in t.get("rows", [])
                for cell in row
                if str(cell or "").strip() and MERGED.match(str(cell).strip()))
        if n:
            out.append((ti, n, t.get("n_col"), str(t.get("caption", ""))[:34]))
    if out:
        total += sum(x[1] for x in out)
        print("band_%s  merged=%d" % (idx, sum(x[1] for x in out)))
        for ti, n, nc, cap in out:
            print("    t%-3d %3d cells  n_col=%-4s %s" % (ti, n, nc, cap))
print("GRAND TOTAL merged cells:", total)