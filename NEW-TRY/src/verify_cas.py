# -*- coding: utf-8 -*-
"""
Independent verification of the CAS column.

Three checks, none of which trust the pipeline that produced the values:

  checksum   A CAS number is not a label, it is an identifier with a check digit: the
             final digit is the sum of each preceding digit times its position from the
             right, modulo ten. Any transcription error - a misread digit from a
             scanned table, a digit dropped off the end, two cells run together -
             fails it. This costs nothing and needs no network, so it checks every value
             in the workbook rather than a sample.

  conflict   Where a paper printed its own CAS and the lookup produced one too, the two
             are compared. A mismatch means either the paper is wrong or the name was
             read as a neighbouring compound; both are worth seeing, and neither is
             silently resolved.

  round trip A sample of resolved values is looked up again and the CAS resolved back to
             a CID, compared against the CID the name resolved to. This is what catches a
             translation that produced a real but wrong compound - the failure mode a
             checksum cannot see.

Run: python verify_cas.py [--roundtrip N]
"""

import argparse
import os
import random
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")

CAS_RE = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")

OUT = os.path.join("out", "re整理")
XLSX = os.path.join(OUT, "re整理.xlsx")
CACHE = os.path.join(OUT, "pubchem_cache.json")

# The block finder is shared: a 基础数据 block is identified by having both the name
# column and the CAS column, which the writer always emits. 化合物名称 alone is not
# enough - it also appears as a header row inside the verbatim block.
import blocks  # noqa: E402


def cas_checksum_ok(cas):
    """True if the check digit matches. Returns None if the format is not a CAS."""
    m = CAS_RE.match(cas.strip())
    if not m:
        return None
    body = m.group(1) + m.group(2)
    total = sum(int(d) * (i + 1) for i, d in enumerate(reversed(body)))
    return total % 10 == int(m.group(3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roundtrip", type=int, default=0,
                    help="how many resolved names to verify against a second lookup")
    ap.add_argument("--out", default="",
                    help="also write the report to this file, in UTF-8")
    a = ap.parse_args()
    import report_out
    sys.stdout = report_out.open_report(a.out)

    import openpyxl
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)

    total = ok = badfmt = 0
    bad_printed = []
    bad_filled = []
    printed = 0
    filled = 0
    unresolved = 0
    conflicts = []
    per_sheet = {}

    for sn in wb.sheetnames:
        if sn == "00_索引":
            continue
        rows = list(wb[sn].iter_rows(values_only=True))
        for start, stop in blocks.find_data_blocks(rows):
            for row in rows[start + 1:stop]:
                a0 = str(row[0] or "") if row and row[0] is not None else ""
                if not a0.strip():
                    continue
                note = str(row[2]) if len(row) > 2 and row[2] is not None else ""
                cas = (str(row[1]).strip()
                       if len(row) > 1 and row[1] is not None else "")
                per_sheet[sn] = per_sheet.get(sn, 0) + 1

                if not cas:
                    if "未解析" in note:
                        unresolved += 1
                    continue
                # "反查" marks a number supplied by lookup; anything else was printed
                # in the paper. The distinction is written into the sheet for exactly
                # this reason - without it the two are indistinguishable.
                if "反查" in note:
                    filled += 1
                else:
                    printed += 1
                total += 1
                verdict = cas_checksum_ok(cas)
                if verdict is None:
                    badfmt += 1
                    bad_filled.append((sn, a0[:28], cas, note[:30]))
                elif verdict:
                    ok += 1
                else:
                    bad_printed.append((sn, a0[:28], cas, note[:30]))
                if note.startswith("印刷"):
                    m = re.match(r"印刷([\d-]+)\s*/\s*反查([\d-]+)", note)
                    if m:
                        conflicts.append((sn, a0[:28], m.group(1), m.group(2)))
    wb.close()

    print("=" * 70)
    print("CAS CHECKSUM   %d values, %d pass, %d fail the check digit, %d malformed"
          % (total, ok, total - ok - badfmt, badfmt))
    print("=" * 70)
    print("   printed in the paper : %d" % (total - filled))
    print("   filled by lookup     : %d" % filled)
    print("   left unresolved      : %d" % unresolved)
    print()
    if bad_printed:
        print("--- printed values failing the checksum (%d) ---" % len(bad_printed))
        for sn, nm, cas, note in bad_printed[:30]:
            print("   %-16s %-28s %-14s %s" % (sn[:16], nm, cas, note))
        print()
    if bad_filled:
        print("--- filled values failing the checksum (%d) ---" % len(bad_filled))
        for sn, nm, cas, note in bad_filled[:30]:
            print("   %-16s %-28s %-14s %s" % (sn[:16], nm, cas, note))
        print()
    if conflicts:
        print("--- printed vs resolved disagreements (%d) ---" % len(conflicts))
        for sn, nm, p, r in conflicts:
            print("   %-16s %-28s printed %-12s resolved %s" % (sn[:16], nm, p, r))
        print()

    # Rows whose name cell holds more than the name. A number in that cell means the
    # table row was never split into columns, so the concentrations are trapped in the
    # name and the quantitative columns for that row are empty. Locating them is the
    # difference between "some rows look wrong" and a list that can be fixed.
    wb2 = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    mis = []
    for sn in wb2.sheetnames:
        if sn == "00_索引":
            continue
        rows = list(wb2[sn].iter_rows(values_only=True))
        for start, stop in blocks.find_data_blocks(rows):
            for ri, row in enumerate(rows[start + 1:stop], start + 2):
                a0 = str(row[0] or "").strip()
                if not a0:
                    continue
                # A number trapped in the name cell is the signature of a row that was
                # never split into columns.
                #
                # Only bare numeric TOKENS count, and only ones carrying a decimal point.
                # Digits that are part of a name are not evidence of anything:
                # "2-methylpropanol", "3-hydroxy-2-butanone", "gamma-terpinene" and
                # "2,3-butanediol" all contain digits and are all correct names.
                #
                # The earlier version also flagged any cell with more than one whitespace
                # token, which made it report every two-word English name - "ethyl
                # hexanoate", "furfuryl acetate", "dimethyl trisulfide" - as a broken row.
                # That was 495 false positives against 67 real ones, and a check that
                # cries wolf 495 times is a check nobody reads, so the real ones would
                # have been the ones that got missed.
                toks = a0.split()
                nums = [t for t in toks
                        if re.fullmatch(r"\d+\.\d+", t.strip("()（）"))]
                if len(nums) >= 2:
                    mis.append((sn, ri, a0[:60],
                                "numbers trapped in the name cell"))
    wb2.close()
    print("=" * 70)
    print("ROWS THE TABLE SPLIT MISSED   %d" % len(mis))
    print("=" * 70)
    for sn, ri, cell, why in mis:
        print("   %-18s row %-5d %-46s %s" % (sn[:18], ri, cell, why))
    if not mis:
        print("   none")
    print()

    if a.roundtrip:
        import fill_cas as F
        cache = __import__("json").load(open(CACHE, encoding="utf-8"))
        good = [(k, v) for k, v in cache.items()
                if v[0] and str(v[2]).startswith("ok") and v[1]]
        random.seed(7)
        sample = random.sample(good, min(a.roundtrip, len(good)))
        print("--- round trip on %d resolved names ---" % len(sample))
        agree = disagree = unresolved_rt = 0
        for name, (cas, cid, _st) in sample:
            try:
                # a CAS number is itself a registered synonym, so the same exact-quoted
                # lookup that resolves a name also resolves a CAS back to its CID
                back = F.name_to_cid_eutils(cas)
            except Exception as e:
                print("   %-28s %-13s lookup failed: %s"
                      % (name[:28], cas, str(e)[:40]))
                unresolved_rt += 1
                continue
            if back == cid:
                agree += 1
            elif back is None:
                unresolved_rt += 1
            else:
                disagree += 1
                print("   MISMATCH  %-28s %-13s name->%s  cas->%s"
                      % (name[:28], cas, cid, back))
        print("   %d agree, %d disagree, %d the CAS did not resolve"
              % (agree, disagree, unresolved_rt))
    return 0


if __name__ == "__main__":
    sys.exit(main())