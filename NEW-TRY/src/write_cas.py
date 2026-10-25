# -*- coding: utf-8 -*-
"""
Write the resolved CAS numbers back into the workbook.

Two sources, and the difference matters
---------------------------------------
Seven of the papers print a CAS column of their own. Those values win. A printed registry
number is the one the authors used for their own standard solutions, so it outranks
anything a name lookup produces, and discarding it in favour of a database hit would
throw away the better answer. Where the two disagree anyway the sheet says so in a
separate column rather than silently preferring one: a genuine mismatch usually means the
name was OCR'd into a neighbouring compound, which is exactly the kind of error that is
invisible otherwise.

Unresolved names stay blank with the reason recorded, so a gap reads as a gap and not as
an oversight.

Usage:
    python src/write_cas.py --cas out/re整理/cas_map.json --xlsx out/re整理/re整理.xlsx
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import blocks      # noqa: E402
import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))

CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

OK_FILL = PatternFill("solid", fgColor="E2EFDA")
CONFLICT_FILL = PatternFill("solid", fgColor="FFF2CC")
MISS_FILL = PatternFill("solid", fgColor="FCE4E4")
DIM_FONT = Font(size=9, color="808080")


def load_cas(path):
    """
    Accept either shape of the CAS file.

    cas_map.json is keyed by the name and stores a status alongside the value, so the
    value has to be filtered by status - an entry recorded as "no-cid" has an empty CAS,
    but one recorded after a transport failure must not be mistaken for a real answer.
    cas_by_name.json is the pre-filtered {name: cas} pair written by write_cas's helper.
    """
    d = json.load(open(path, encoding="utf-8"))
    if "cas" in d and isinstance(d["cas"], dict):
        return {k: v for k, v in d["cas"].items() if v}
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            if v.get("cas") and str(v.get("status", "")).startswith("ok"):
                out[k] = v["cas"]
        elif isinstance(v, str) and v:
            out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cas", default=os.path.join(REOUT, "cas_by_name.json"))
    ap.add_argument("--xlsx", default=os.path.join(REOUT, "re整理.xlsx"))
    ap.add_argument("--col-verify", default="CAS核对",
                    help="extra column recording printed-vs-resolved differences")
    ap.add_argument("--cross", default="",
                    help="cas_cross.json: PubChem cross-checked against NIST WebBook")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    cas = load_cas(a.cas) if os.path.exists(a.cas) else {}
    print("usable CAS entries: %d" % len(cas))

    # Second-source agreement. cas_cross.json holds what PubChem and NIST each said about
    # every name; only a number both agree on, or one that only one source has, is written.
    # A disagreement is left blank on purpose: there is nothing in the evidence that makes
    # one database right about a name the other read differently, and picking one would put
    # a confident number in a priority-1 column on a coin flip.
    cross = {}
    disagree = []
    if a.cross and os.path.exists(a.cross):
        cross = json.load(open(a.cross, encoding="utf-8"))
        agree = sum(1 for v in cross.values() if v.get("status") == "agree")
        print("cross-check: agree %d, nist-only %d, disagree %d"
              % (agree, sum(1 for v in cross.values() if v.get("status") == "nist-only"),
                 sum(1 for v in cross.values() if v.get("status") == "disagree")))

    wb = openpyxl.load_workbook(a.xlsx)
    stat = Counter()
    conflicts = []

    for sn in wb.sheetnames:
        if sn == "00_索引":
            continue
        ws = wb[sn]

        # Every basic-data block on the sheet, not just the first.
        #
        # The previous version took the first 化合物名称 header and stopped when that
        # block ended. A sheet can hold thirty-one tables - sheet 29 does - so thirty of
        # them were never looked at and reached the workbook with no CAS at all, while the
        # sheets that happen to have one table looked complete. That is the worst kind of
        # gap: it looks like a coverage figure rather than a bug.
        #
        # A header is only a data-block header if the CAS column is there too.
        # 化合物名称 on its own also appears as an ordinary header row inside the
        # 原表逐格 block, and starting there wrote concentrations into 87 CAS cells.
        hdr_rows = [r for r in range(1, ws.max_row + 1)
                    if blocks.is_data_header([ws.cell(row=r, column=c).value
                                              for c in range(1, 5)])]

        for hdr_row in hdr_rows:
            vcol = None
            for c in range(2, ws.max_column + 1):
                hv = ws.cell(row=hdr_row, column=c).value
                if hv and str(hv).startswith("CAS"):
                    vcol = c
                    break
            if vcol is None:
                continue

            ws.cell(row=hdr_row, column=vcol + 1, value=a.col_verify)
            ws.cell(row=hdr_row, column=vcol + 1).font = DIM_FONT

            # where this block ends: the next header, or the end of the sheet
            stop = ws.max_row + 1
            for nxt in hdr_rows:
                if nxt > hdr_row:
                    stop = nxt
                    break

            for r in range(hdr_row + 1, stop):
                name = ws.cell(row=r, column=1).value
                if name is None or not str(name).strip():
                    continue
                s = str(name)
                if blocks.BLOCK_END.match(s):
                    break
                # a second data-block header in the same row means a nested table
                # started; blocks.is_data_header is the same test the readers use
                if blocks.is_data_header([ws.cell(row=r, column=c).value or ""
                                          for c in range(1, 5)]):
                    break

                printed = str(ws.cell(row=r, column=vcol).value or "").strip()
                printed_ok = CAS_RE.match(printed)
                got = (cas.get(s.strip()) or cas.get(s) or "").strip()
                cr = cross.get(s.strip()) or cross.get(s) or {}
                # An ADJUDICATED disagreement outranks the single-source answer.
                # cas_crosscheck --resolve decides these on evidence - PubChem answered with
                # the racemate for a name that specified L(--), NIST served a registry number
                # it does not itself hold - and stores the number it settled on in `cas`.
                # Taking PubChem's value first would have kept the wrong one and only
                # recorded the correct reasoning beside it.
                if cr.get("status") in ("stereo-resolved", "title-match",
                                        "stereo-variant", "nist-bad-hit") \
                        and cr.get("cas"):
                    got = cr["cas"]
                # NIST's answer is used when PubChem has none. Without this the second
                # database only ever annotated the first one's results, and the six names
                # NIST knew and PubChem did not stayed blank - which is the entire reason
                # a second source was added. A disagreement carries no cas in `cross`, so
                # this cannot quietly fill in a contested value.
                if not got and cr.get("cas"):
                    got = cr["cas"]

                if printed_ok and got and printed_ok.group(0) != got:
                    # Not necessarily an error. Isoamyl acetate is listed under more than
                    # one registry number, so a printed CAS and a resolved one can differ
                    # while both naming the same compound. The printed value is kept either
                    # way; the note records both so the difference is visible rather than
                    # resolved by fiat.
                    ws.cell(row=r, column=vcol + 1,
                            value="印刷%s / 反查%s" % (printed, got)).font = DIM_FONT
                    ws.cell(row=r, column=vcol + 1).fill = CONFLICT_FILL
                    conflicts.append((sn, s.strip(), printed, got))
                    stat["conflict"] += 1
                    continue

                if printed_ok:
                    ws.cell(row=r, column=vcol).fill = OK_FILL
                    stat["printed"] += 1
                    continue

                if got:
                    ws.cell(row=r, column=vcol, value=got)
                    # marked so the reader can tell a number the paper printed from one
                    # supplied here; without it the two are indistinguishable. The mark also
                    # says WHICH source answered, because a number both databases agree on
                    # is a stronger answer than one only PubChem had.
                    stt = cr.get("status", "")
                    mark = {"agree": "反查·双库一致",
                            "nist-only": "反查·NIST",
                            "pubchem-only": "反查·PubChem",
                            # disagreements that evidence settled, and why
                            "stereo-resolved": "反查·按构型判定",
                            "title-match": "反查·按名称判定",
                            "stereo-variant": "反查·构型标注差异",
                            "nist-bad-hit": "反查·NIST坏命中已剔除",
                            "disagree": "双库不一致·未写"}.get(stt, "反查")
                    ws.cell(row=r, column=vcol + 1, value=mark).font = DIM_FONT
                    if stt == "disagree":
                        disagree.append((sn, s.strip(), cr.get("pubchem", ""),
                                         cr.get("nist", "")))
                    stat["filled"] += 1
                else:
                    if cr.get("status") == "disagree":
                        ws.cell(row=r, column=vcol + 1,
                                value="双库不一致 %s/%s"
                                      % (cr.get("pubchem", "?"), cr.get("nist", "?"))).font \
                            = DIM_FONT
                        ws.cell(row=r, column=vcol + 1).fill = CONFLICT_FILL
                        disagree.append((sn, s.strip(), cr.get("pubchem", ""),
                                         cr.get("nist", "")))
                    else:
                        ws.cell(row=r, column=vcol + 1, value="未解析").font = DIM_FONT
                        ws.cell(row=r, column=vcol + 1).fill = MISS_FILL
                    stat["unresolved"] += 1

            ws.column_dimensions[get_column_letter(vcol + 1)].width = 26

    out = a.out or a.xlsx
    wb.save(out)
    print("printed kept: %d   filled from lookup: %d   conflicts: %d"
          % (stat["printed"], stat["filled"], stat["conflict"]))
    for k, v in sorted(stat.items()):
        if k.startswith("unresolved"):
            print("   %-34s %d" % (k, v))
    if cross:
        marks = Counter()
        for sn in wb.sheetnames:
            if sn == "00_索引":
                continue
            ws2 = wb[sn]
            for row in ws2.iter_rows():
                for c in row:
                    if c.value == "反查·双库一致":
                        marks["双库一致"] += 1
                    elif c.value == "反查·NIST":
                        marks["仅NIST有"] += 1
                    elif c.value == "反查·PubChem":
                        marks["仅PubChem有"] += 1
        print("   %-34s %d" % ("反查标记·双库一致", marks["双库一致"]))
        print("   %-34s %d" % ("反查标记·仅NIST有", marks["仅NIST有"]))
        print("   %-34s %d" % ("反查标记·仅PubChem有", marks["仅PubChem有"]))
    if disagree:
        print()
        print("两库不一致，未写入 CAS（需要人工判断哪个库把名字读错了）: %d" % len(disagree))
        for sn, nm, p, nn in disagree[:30]:
            print("   %-30s %-24s pubchem %-12s nist %s" % (sn[:30], nm[:24], p, nn))
    if conflicts:
        print()
        print("conflicts (printed vs resolved) - kept the printed value:")
        for sn, nm, p, g in conflicts[:40]:
            print("   %-38s %-22s printed %-13s resolved %s" % (sn[:38], nm[:22], p, g))
        # written out so the disagreements can be audited on their own merits instead of
        # being settled by this script's blanket policy - see audit_cas_conflicts.py
        cpath = os.path.join(os.path.dirname(out or a.xlsx), "conflicts.json")
        try:
            json.dump([{"sheet": sn, "name": nm, "printed": p, "resolved": g}
                       for sn, nm, p, g in conflicts],
                      open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("\nconflicts -> %s" % cpath)
        except OSError as e:
            print("could not write conflicts.json: %s" % e)
    print("\n-> %s" % out)


if __name__ == "__main__":
    main()
