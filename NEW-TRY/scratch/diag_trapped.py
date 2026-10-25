# -*- coding: utf-8 -*-
"""Locate band tables whose rows were never split into columns.

A merged cell is recognisable without knowing the table: a cell that holds a name and
then two or more numbers is one OCR box spanning several printed columns.
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))

NUM = r"[-+]?\d[\d,]*\.?\d*"
# a cell is "merged" when it ends in >=2 numbers after some leading text
MERGED = re.compile(r"^(?P<head>.*\S)\s+(?P<n1>%s)\s+(?P<n2>%s)(?P<rest>.*)$" % (NUM, NUM))


def scan(idx):
    path = os.path.join(REOUT, "band_%02d.json" % idx)
    d = json.load(open(path, encoding="utf-8"))
    hits = []
    for ti, t in enumerate(d["tables"]):
        for ri, row in enumerate(t.get("rows", [])):
            for ci, cell in enumerate(row):
                s = str(cell or "").strip()
                if not s:
                    continue
                m = MERGED.match(s)
                if m and m.group("head").strip():
                    hits.append((ti, ri, ci, s, len(t.get("rows", [])),
                                 t.get("n_col"), str(t.get("caption", ""))[:45]))
    return d, hits


def main():
    for idx in (21, 29, 31):
        d, hits = scan(idx)
        print("=" * 78)
        print("band_%02d.json  route=%s  tables=%d" % (idx, d.get("route"), len(d["tables"])))
        bytab = {}
        for ti, ri, ci, s, nrow, ncol, cap in hits:
            bytab.setdefault(ti, []).append((ri, ci, s, nrow, ncol, cap))
        for ti in sorted(bytab):
            g = bytab[ti]
            print("  table %-3d  %d merged cells   n_row=%s n_col=%s  %s"
                  % (ti, len(g), g[0][3], g[0][4], g[0][5]))
            cols = sorted(set(x[1] for x in g))
            print("           merged columns: %s" % cols)
            for ri, ci, s, *_ in g[:4]:
                print("           r%-4d c%-2d %s" % (ri, ci, s[:60]))
            if len(g) > 4:
                print("           ... %d more" % (len(g) - 4))


if __name__ == "__main__":
    main()