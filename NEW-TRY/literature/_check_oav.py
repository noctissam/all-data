# -*- coding: utf-8 -*-
"""
Unit / arithmetic self-check for the reconstructed tables.

The paper reports OAV = concentration / odor threshold, so the reported OAV is an
independent check on the concentration, the threshold AND their unit at once. If a
column were really mg/L while we believed ug/L, the recomputed OAV would be off by
exactly 1000x and would not match the printed value.

This is a stronger guarantee than the two-pass OCR comparison: two passes share the
same misreadings, whereas this check compares the numbers against each other.

Handles:
  - footnote superscripts glued to values   "55.3c", "0.4c"  -> strip
  - mean +/- SD pairs                        "7,606,936 +- 17,161"
  - en/em dashes and thousands separators
  - reported OAV rounded to few digits      compare with a rounding-aware tolerance

Usage:
    python _check_oav.py <table_grid.json> [name_col] [thr_col] [conc_col] [oav_col]
"""

import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DASHES = "−–—‒‐"
FOOTNOTE = re.compile(r"^([−–—‒\-]?\d[\d.,]*)\s*(.*)$")


def strip_footnote(s):
    """"55.3c" -> ("55.3", "c"); the superscript letter is a literature footnote."""
    s = (s or "").strip()
    for d in DASHES:
        s = s.replace(d, "-")
    m = FOOTNOTE.match(s)
    if not m:
        return s, ""
    head, tail = m.group(1), m.group(2).strip()
    if tail and re.fullmatch(r"[a-z]{1,2}", tail):
        return head, tail
    return s, ""


def parse_mean_sd(s):
    """"7,606,936 +- 17,161" -> (7606936.0, 17161.0); plain number -> (x, None)."""
    base, _fn = strip_footnote(s)
    t = base.replace(",", "").replace(" ", "")
    m = re.match(r"^(-?\d+(?:\.\d+)?)(?:[±+*](\d+(?:\.\d+)?))?$", t)
    if not m:
        return None, None
    return float(m.group(1)), (float(m.group(2)) if m.group(2) else None)


def parse_plain(s):
    v, _sd = parse_mean_sd(s)
    return v


def cmp_oav(calc, rep):
    """
    True when the recomputed OAV is consistent with the printed one.
    Printed OAV may be rounded, so allow: same to 2%, or same after rounding the
    recomputed value to the precision the paper printed (count of decimals / digits).
    """
    if rep in (None, 0) or calc is None:
        return False, float("nan")
    ratio = calc / rep
    if 0.98 <= ratio <= 1.02:
        return True, ratio
    # paper rounded: e.g. printed "1" for a true 0.75
    for q in (0, 1, 2, 3):
        if round(calc, q) == round(rep, q) and abs(calc - rep) <= 0.5 * 10 ** -q + 1e-9:
            return True, ratio
    # or printed with 3 significant figures
    if abs(calc - rep) / max(abs(rep), 1e-9) <= 0.005:
        return True, ratio
    return False, ratio


def main():
    path = sys.argv[1]
    ci_name = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    ci_thr = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    ci_conc = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    ci_oav = int(sys.argv[5]) if len(sys.argv) > 5 else 5

    g = json.load(open(path, encoding="utf-8"))
    print("id=%s page=%s  cols=%d  (name=%d thr=%d conc=%d oav=%d)"
          % (g["id"], g["page"], g["n_col"], ci_name, ci_thr, ci_conc, ci_oav))

    ok = bad = skip = 0
    ratios = []
    print()
    print("%-36s %-14s %-11s %11s %11s %8s" %
          ("compound", "conc", "threshold", "OAV_calc", "OAV_paper", "ratio"))
    for row in g["body"]:
        cells = [c["text"] for c in row]
        if len(cells) <= max(ci_name, ci_thr, ci_conc, ci_oav):
            skip += 1
            continue
        nm = cells[ci_name]
        base = strip_footnote(cells[ci_name])[0]
        conc, _sd = parse_mean_sd(cells[ci_conc])
        thr = parse_plain(cells[ci_thr])
        rep = parse_plain(cells[ci_oav])
        if not base or conc is None or not thr or rep is None:
            skip += 1
            continue
        calc = conc / thr
        good, ratio = cmp_oav(calc, rep)
        ratios.append(ratio)
        if good:
            ok += 1
        else:
            bad += 1
            print("%-36s %-14s %-11s %11.2f %11s %8.3f  <== CHECK" % (
                nm[:36], cells[ci_conc][:14], cells[ci_thr][:11], calc, cells[ci_oav][:11], ratio))

    print()
    print("rows=%d  consistent=%d  inconsistent=%d  skipped=%d"
          % (len(g["body"]), ok, bad, skip))
    if ratios:
        ratios.sort()
        print("ratio  min=%.4f  median=%.4f  max=%.4f  (1.000 = unit and values both right)"
              % (ratios[0], ratios[len(ratios) // 2], ratios[-1]))


if __name__ == "__main__":
    main()
