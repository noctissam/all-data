# -*- coding: utf-8 -*-
"""List the band tables that still have unnamed data columns ("列N").

"列N" is sample_label()'s fallback: every header row in header_rows is empty at that
column. For a band table that usually means the grid never captured the header line, not
that the paper does not print one - the text layer has it.
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")


def main():
    rows = []
    for f in sorted(glob.glob("out/re整理/band_*.json")):
        idx = os.path.basename(f)[5:7]
        d = json.load(open(f, encoding="utf-8"))
        for ti, t in enumerate(d.get("tables", [])):
            ncol = t.get("n_col") or 0
            hr = t.get("header_rows") or []
            if not hr:
                rows.append((idx, ti, t.get("pages"), "整表无表头", ncol,
                             str(t.get("caption", ""))[:40]))
                continue
            empty = [c for c in range(ncol)
                     if not any((r[c] if c < len(r) else "").strip() for r in hr)]
            # a column that is empty in the header but holds numbers in the body is the
            # one worth recovering; a wholly empty column is just padding
            dead = []
            for c in empty:
                vals = sum(1 for r in t.get("rows", [])
                           if c < len(r) and str(r[c] or "").strip())
                if vals >= 3:
                    dead.append(c)
            if dead:
                rows.append((idx, ti, t.get("pages"),
                             "空表头列 %s / 共%d" % (dead, ncol), ncol,
                             str(t.get("caption", ""))[:40]))

    print("有数据但表头为空的列，共 %d 张表：" % len(rows))
    for r in rows:
        print("  band_%s t%-3d pages=%-9s %-22s %s"
              % (r[0], r[1], str(r[2]), r[3], r[5]))


if __name__ == "__main__":
    main()