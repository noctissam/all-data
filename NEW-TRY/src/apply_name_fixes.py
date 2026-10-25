# -*- coding: utf-8 -*-
"""
Apply the hand-checked name corrections, and refuse everything else.

Scope, and why it is this narrow
--------------------------------
Every entry below restores a character the OCR dropped or turned into a stray glyph.
None of them decides between two isomers, because that is chemistry and not string
repair:

    3-甲基」醇   ->  3-甲基丁醇      the 「 is a broken glyph; 丁醇 is what baijiu contains
    —一酸乙酯     ->  十一酸乙酯      the dash ate the 十, leaving 一
    y-己内酯      ->  γ-己内酯        gamma mis-set as y

Deliberately NOT applied, even though the earlier report listed them as candidates:

    3-甲基-2-丁醇  ->  3-甲基-2-己醇   a C4 becoming a C6 is a different compound
    乙酸-2-甲基丙酯 ->  己酸-2-甲基丙酯  two different esters
    肉桂酸乙酯      ->  月桂酸乙酯      an aromatic acid against a saturated one

Each correction is matched on the WHOLE cell, never as a substring. A partial match here
would rewrite every row containing 乙酸 in it, which is a large fraction of the corpus.

Usage:
    python src/apply_name_fixes.py [--dry-run]
"""

import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))

# whole-cell match -> replacement, with the reason it is safe
FIXES = {
    # a broken glyph standing in for a real character
    "3-甲基」醇": "3-甲基丁醇",
    "乙酸-3-甲基厂酯": "乙酸-3-甲基丁酯",
    # the leading stroke of a number eaten by a dash
    "—一酸乙酯": "十一酸乙酯",
    "2-十—酮": "2-十一酮",
    # gamma set as a latin letter
    "Y-壬内酯": "γ-壬内酯",
    "y-己内酯": "γ-己内酯",
    # a trailing character dropped by the column edge
    "辛酸-3-甲基丁": "辛酸-3-甲基丁酯",
    "4-乙基愈创木": "4-乙基愈创木酚",
    # an english name sitting in a chinese column: same compound, unify the spelling
    "4-Methylphenol": "4-甲基苯酚",
    "1-Heptanol": "1-庚醇",
    "2-ethylphenol": "2-乙基苯酚",
}

# Corrections that were proposed and then withdrawn, kept here so the decision is
# recorded rather than re-litigated on the next run.
REJECTED = {
    "3-甲基-2-丁醇": "3-甲基-2-己醇   -- changes the carbon count, a different compound",
    "乙酸-2-甲基丙酯": "己酸-2-甲基丙酯  -- a different ester",
    "异丁酸异戊酯": "异戊酸异戊酯     -- a different acid",
    "肉桂酸乙酯": "月桂酸乙酯       -- aromatic vs saturated, entirely different",
    "2-乙基-5-甲基呋喃": "2-乙酰基-5-甲基呋喃 -- 乙基 is ethyl, 乙酰基 is acetyl",
    "1,1-二乙氧基": "truncated; the full name cannot be recovered from the fragment",
    "2-呋喃甲酸乙酯": "a synonym, not an error - 呋喃甲酸 and 呋喃羧酸 are one compound",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(REOUT)
                   if re.match(r"^(bm|en|band|raw)_\d+\.json$", f))
    hits = {k: 0 for k in FIXES}
    changed_files = 0
    cells = 0

    for fn in files:
        p = os.path.join(REOUT, fn)
        d = json.load(open(p, encoding="utf-8"))
        changed = False
        for t in d.get("tables", []):
            for key in ("rows", "header_rows"):
                for row in t.get(key, []):
                    for j, cell in enumerate(row):
                        key_s = (cell or "").strip()
                        if key_s in FIXES:
                            row[j] = FIXES[key_s]
                            hits[key_s] += 1
                            changed = True
                            cells += 1
        if changed:
            changed_files += 1
            if not a.dry_run:
                json.dump(d, open(p, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)

    print("corrections defined: %d" % len(FIXES))
    for k, v in FIXES.items():
        print("   %-22s -> %-20s %s" % (k, v, ("x%d" % hits[k]) if hits[k] else "NOT FOUND"))
    print()
    print("cells rewritten: %d   files touched: %d" % (cells, changed_files))
    print()
    print("withdrawn on purpose (kept for the record):")
    for k, why in REJECTED.items():
        print("   %-22s  %s" % (k, why))
    if a.dry_run:
        print("\n(dry run - nothing written)")


if __name__ == "__main__":
    main()
