# -*- coding: utf-8 -*-
"""
Normalise compound names that OCR has corrupted.

The problem
-----------
Names read through the text layer are exactly as typeset. Names read through OCR are
not: the CNKI and Elsevier OCR models mis-set the rare chemical glyphs, which is why
this project's own experiments turned 酯 up as 酷 and 阈 up as 阂, and why the 2023
aroma table came back with "3-甲基」醇" where the paper says "3-甲基丁醇". A wrong
character in a name is the worst kind of extraction error here, because the row still
looks complete - it has a name, a concentration and a threshold - so nothing flags it.

The fix uses the corpus itself as the dictionary
-------------------------------------------------
The 24 papers read through the text layer carry names that OCR never touched, and they
cover the same common baijiu volatiles. So for each OCR-derived name, look for a
text-layer name one character edit away. If there is exactly one, the OCR reading is
that name with a typo, and it is corrected.

Why one edit and not a fuzzy match
----------------------------------
己酸乙酯 and 乙酸己酯 are the same pair of carbons written the other way round. A
similarity search that allowed transpositions or two edits would happily swap them, and
the result would still look like a plausible compound. Restricting to a single edit and
requiring the match to be unique means a name is only changed when there is exactly one
explanation, and a transposition is left alone for a human to look at.

Every change is written to a CSV with both the original and the corrected spelling, so
each one can be checked rather than trusted.

Usage:
    python src/normalize_names.py                 # propose and apply
    python src/normalize_names.py --dry-run       # report only
"""

import argparse
import csv
import difflib
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REOUT = os.path.join(ROOT, "out", "re整理")

# Superscript footnote markers a paper prints next to a name (1-丙醇a, 1-丙醇b). Only
# ever applied to CHINESE names: the same pattern on a latin name strips the final
# letter of "Ethyl acetate" and turns it into "Ethyl aceta", which then matches nothing.
SUPERSCRIPT = re.compile(r"(?<=[一-鿿])([a-zA-Z])$")
HAS_CJK = re.compile(r"[一-鿿]")
UNIT_TAIL = re.compile(r"[（(]\s*[^)）]{0,24}\s*[)）]$")
TRAIL_NUM = re.compile(r"\s+[\d.,;；]+\s*$")
CJK = re.compile(r"[一-鿿]")


def base_name(s):
    """Strip footnote markers, a trailing unit, and trailing page numbers."""
    s = (s or "").strip()
    s = UNIT_TAIL.sub("", s).strip()
    if HAS_CJK.search(s):
        s = SUPERSCRIPT.sub("", s).strip()
    s = TRAIL_NUM.sub("", s).strip()
    return s


def digits(s):
    return [c for c in s if c.isdigit()]


def edits_at_most_one_loose(a, b):
    """Any single-character difference, digits included. Used only to shortlist, so that
    a real candidate is at least examined; safe_correction decides whether it may be
    applied automatically."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = j = 0
    skipped = False
    while i < len(short) and j < len(long_):
        if short[i] == long_[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def truncation_fix(ocr, cand):
    """
    Restore a name the OCR cut short.

    This is the dominant failure in the OCR papers, and it is not a character
    substitution: a table column is narrower than the word, so the engine returns
    "ethyl hexanoat" where the paper prints "ethyl hexanoate", and "2-Heptanon" where it
    prints "2-Heptanol". A one-character-difference test cannot tell that from a typo,
    which is why an earlier version of this script "corrected" 1-Heptano to 2-Heptanol
    and 2-甲基丁醇 to 2-甲基丙醇.

    A prefix relationship with the digit sequence unchanged is unambiguous in the way an
    edit distance is not: the OCR reading is a strict prefix of a real name, so the name
    can only be the longer one. The digit check keeps "1-Heptano" from reaching for
    "2-Heptanol" while still letting it reach its own "1-Heptanol".
    """
    if not ocr or not cand or ocr == cand:
        return False
    if digits(ocr) != digits(cand):
        return False
    if len(cand) <= len(ocr):
        return False
    if len(cand) - len(ocr) > 4:          # a near-match, not a clipped word
        return False
    return cand.lower().startswith(ocr.lower())


def safe_correction(ocr, cand):
    """
    Is correcting `ocr` to `cand` safe to do without asking a chemist?

    Three things have to hold, and the first one rules out most of what a naive fuzzy
    match would have done here:

      the digit sequences must be identical - "1-Heptano" and "2-Heptano" are 1-heptanol
        and 2-heptanol, two different compounds, and a corpus that happens to contain
        only the second must not be allowed to rewrite the first;

      at most one character differs, and that character must not be a digit;

      the strings must differ in more than case only, or this is a capitalisation
        difference to fold rather than a typo to fix.

    A single differing HANZI still passes all three, and that is the honest limit of
    what can be decided automatically: 2-甲基丁醇 and 2-甲基丙醇 differ by one
    non-digit character exactly as a mis-read 丁 would, and nothing in the corpus
    distinguishes the typo from the isomer. Chinese names are therefore reported and
    left for review.
    """
    if ocr == cand:
        return False
    if digits(ocr) != digits(cand):
        return False
    if ocr.lower() == cand.lower():
        return False
    if abs(len(ocr) - len(cand)) > 1:
        return False
    if len(ocr) == len(cand):
        diff = [(x, y) for x, y in zip(ocr, cand) if x != y]
        if len(diff) != 1:
            return False
        x, y = diff[0]
        return not (x.isdigit() or y.isdigit())
    short, long_ = (ocr, cand) if len(ocr) < len(cand) else (cand, ocr)
    i = j = 0
    while i < len(short) and j < len(long_):
        if short[i] == long_[j]:
            i += 1
            j += 1
        else:
            extra = long_[j]
            j += 1
            if not extra.isdigit():
                return False
    return True


def case_only_fix(ocr, cand):
    """Same letters, different capitalisation - a folding, not a correction."""
    return ocr != cand and ocr.lower() == cand.lower()


def is_code(s):
    """Sample or internal-standard labels (NA4, SC1, X0) are not compound names."""
    return bool(re.fullmatch(r"[A-Za-z]{0,3}[0-9]{0,3}", s)) and bool(re.search(r"\d", s))


def load_all():
    """
    Compound names per paper, split by how much they can be trusted.

    Text-layer papers are the dictionary. OCR papers are what gets corrected. The
    vector-OCR route is included on the suspect side even though it double-checks its
    passes, because its agreement rate is not a guarantee about any single cell.
    """
    sys.path.insert(0, HERE)
    from build_rec整理 import load_source, classify_columns

    entries = json.load(open(os.path.join(REOUT, "sheet_map.json"), encoding="utf-8"))
    trusted, suspect = Counter(), Counter()
    detail = []
    for e in entries:
        tag, raw = load_source(e["idx"], REOUT)
        if not raw:
            continue
        trusted_src = raw.get("route") == "band"
        for t in raw.get("tables", []):
            try:
                info = classify_columns(t)
            except Exception:
                continue
            nc = info["name_col"]
            for row in t.get("rows", []):
                v = row[nc] if nc < len(row) else ""
                v = base_name(v)
                if len(v) < 2:
                    continue
                (trusted if trusted_src else suspect)[v] += 1
                detail.append((e["idx"], tag, v, trusted_src))
    return trusted, suspect, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-len", type=int, default=3)
    ap.add_argument("--min-freq", type=int, default=1,
                    help="a dictionary name must appear this often to be trusted as a target")
    a = ap.parse_args()

    trusted, suspect, detail = load_all()
    dict_names = [n for n, c in trusted.items()
                  if len(n) >= a.min_len and c >= a.min_freq and not is_code(n)]
    print("text-layer names: %d (dictionary targets %d)" % (len(trusted), len(dict_names)))
    print("OCR-derived names: %d" % len(suspect))

    # A clipped name can only be repaired against a dictionary entry long enough to be
    # the real thing, so the trusted set is also scanned at every length an OCR reading
    # could be a prefix of - not only at the lengths a one-edit typo would need.
    by_len = {}
    for d in dict_names:
        by_len.setdefault(len(d), []).append(d)

    need = [n for n in suspect
            if n not in trusted and len(n) >= a.min_len and not is_code(n)]
    print("OCR names with no clean-text-layer match: %d" % (len(need) - sum(
        1 for n in need if is_code(n))))

    by_len = {}
    for d in dict_names:
        by_len.setdefault(len(d), []).append(d)

    fixes, casefix, ambiguous, review = {}, {}, [], []
    for n in sorted(need):
        safe, loose = [], []
        for L in range(len(n) - 1, len(n) + 6):
            for d in by_len.get(L, ()):
                if n.lower() == d.lower():
                    casefix.setdefault(n, d)
                elif truncation_fix(n, d) or safe_correction(n, d):
                    safe.append(d)
                elif edits_at_most_one_loose(n, d):
                    loose.append(d)
        safe = sorted(set(safe))
        loose = sorted(set(loose) - set(safe))
        if len(safe) == 1:
            if CJK.search(n):
                review.append((n, safe[0]))
            else:
                fixes[n] = safe[0]
        elif len(safe) > 1 or (safe and loose):
            ambiguous.append((n, sorted(set(safe + loose))))
        elif len(loose) == 1:
            # differing only in a digit, or in a hanzi that could be a real isomer
            review.append((n, loose[0]))

    print()
    print("auto-applied (latin names, digits identical): %d" % len(fixes))
    print("case folds: %d" % len(casefix))
    print("NEEDS REVIEW (chinese, one hanzi differs): %d" % len(review))
    print("ambiguous, left alone: %d" % len(ambiguous))
    print()
    for n, d in sorted(fixes.items(), key=lambda z: z[0]):
        print("   FIX    %-26s -> %s" % (n, d))
    print()
    for n, d in sorted(review, key=lambda z: z[0]):
        print("   REVIEW %-26s -> %s" % (n, d))
    if ambiguous:
        print()
        print("ambiguous, NOT changed:")
        for n, c in ambiguous[:20]:
            print("   %-26s -> %s" % (n, " | ".join(c)))

    csv_path = os.path.join(REOUT, "name_fixes.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ocr_name", "suggested_name", "action", "ocr_rows", "why"])
        for n, d in sorted(fixes.items()):
            w.writerow([n, d, "AUTO", suspect[n], "latin, identical digits"])
        for n, d in sorted(casefix.items()):
            w.writerow([n, d, "AUTO-CASE", suspect[n], "capitalisation only"])
        for n, d in sorted(review, key=lambda z: z[0]):
            w.writerow([n, d, "REVIEW", suspect[n],
                        "one hanzi differs - could be a mis-read or a real isomer"])
        for n, c in ambiguous:
            w.writerow([n, "", "AMBIGUOUS", suspect[n], " | ".join(c)])
    print("\n-> %s" % csv_path)

    if a.dry_run:
        return
    applied = apply_all(fixes, casefix)
    print("cells rewritten: %d" % applied)


def apply_all(fixes, casefix):
    """Rewrite matching cells in the intermediate json files, in place."""
    mapping = dict(fixes)
    mapping.update(casefix)
    applied = 0
    for fn in sorted(os.listdir(REOUT)):
        if not re.match(r"^(bm|en|band|raw)_\d+\.json$", fn):
            continue
        p = os.path.join(REOUT, fn)
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        changed = False
        for t in d.get("tables", []):
            for row in t.get("rows", []):
                for j, cell in enumerate(row):
                    f = mapping.get(base_name(cell))
                    if f and cell != f:
                        row[j] = f
                        changed = True
                        applied += 1
            for hr in t.get("header_rows", []):
                for j, cell in enumerate(hr):
                    f = mapping.get(base_name(cell))
                    if f and cell != f:
                        hr[j] = f
                        changed = True
                        applied += 1
        if changed:
            json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return applied


if __name__ == "__main__":
    main()
