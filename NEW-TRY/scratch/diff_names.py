# -*- coding: utf-8 -*-
"""Did the wrapped-name rejoin change anything it should not have?

Compares the compound names in the band files before and after: names that got longer are
expected (the rejoin), names that DISAPPEARED or changed into something else are not.
"""
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
NEW = "out/re整理"
OLD = "out/re整理/band_backup_prewrap"

ADDED, REMOVED, CHANGED = [], [], []
for f in sorted(glob.glob(os.path.join(NEW, "band_*.json"))):
    b = os.path.basename(f)
    o = os.path.join(OLD, b)
    if not os.path.exists(o):
        continue
    def names(path):
        d = json.load(open(path, encoding="utf-8"))
        out = set()
        for t in d.get("tables", []):
            for r in t.get("rows", []):
                v = str(r[0] or "").strip() if r else ""
                if v:
                    out.add(v)
        return out
    a, c = names(o), names(f)
    ADDED += sorted(a - c)
    REMOVED += sorted(c - a)

print("names that disappeared (%d):" % len(REMOVED))
for n in REMOVED[:40]:
    print("   %s" % n)
print()
print("names that appeared (%d):" % len(ADDED))
for n in ADDED[:40]:
    print("   %s" % n)