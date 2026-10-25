# -*- coding: utf-8 -*-
"""
Audit the concentration columns and their units.

The compound name and the CAS are only two thirds of what the workbook claims to
deliver; the third is the concentration, and a number without a unit is not a result.
Three things are checked:

  units      every concentration column states its unit. A column whose header carries
             no unit and whose cells carry none is reported, because a reader cannot
             tell mg/L from mg/kg from the value alone.

  numbers    concentration cells should parse as numbers. A cell that does not is either
             a footnote, a range, or a failed merge, and each of those needs a different
             answer.

  ranges     "1.02± 0.695" arrives as two numbers once OCR has split the line. Those are
             counted, because treating the standard deviation as a second sample is the
             most likely way to double the apparent sample count of a table.

Run: python verify_values.py [--sheet SUBSTRING]
"""

import argparse
import re
import sys

sys.path.insert(0, "src")

sys.stdout.reconfigure(encoding="utf-8")

XLSX = "out/re整理/re整理.xlsx"

# The block finder is shared: a 基础数据 block is identified by having both the name
# column and the CAS column, which the writer always emits. 化合物名称 alone is not
# enough - it also appears as a header row inside the verbatim block.
import blocks  # noqa: E402

# A number in a results table is rarely a bare number, and reading every variant as text
# buries the cells that really are wrong under a wall of false alarms. What actually turns
# up, all of it counted here as a number:
#
#     26,890      thousands separator with a comma
#     1 016       thousands separator with a space - common in the Chinese tables, and
#                 OCR leaves the space in, so "9 27" is 927
#     4.200,000   the european decimal comma, reversed
#     32,600.0c   a footnote letter from the table's caption
#     58b*        a footnote star
#     32551.6[66] a citation marker
#     7.59 ±      a dispersion whose second half was cut off by the column edge
#     <q.l.       below the quantification limit

_FULLWIDTH = str.maketrans("\uff0d\uff0b\uff0f\uff1c\uff1e\uff05", "-+-<>%")

_TRAIL_MARK = re.compile(r"(?:\[[^\]]*\]|\*+|#+|[a-f])\s*$")


def _digits_only(s):
    """Strip everything that is not part of the number itself."""
    t = s.translate(_FULLWIDTH).strip()
    t = _TRAIL_MARK.sub("", t)
    t = re.sub(r"(?i)\s*(?:q\.?\s*l\.?|ng\.?l\.?|lod|loq)\s*$", "", t)
    t = t.replace("\u00a0", " ").replace("\ufffd", "")
    return re.sub(r"[\s,\u00a0]", "", t)


def classify(s):
    """
    -> one of: "num", "pm", "range", "lt", "notdetected", "text"

    "text" is the only bucket that means a fault, so it is worth the trouble to keep it
    small enough to be worth reading.
    """
    raw = (s or "").strip()
    if not raw:
        return None
    low = raw.lower()
    # An em dash and an "n.d" without its final dot are both ordinary ways of
    # saying the compound was not found in that sample.
    if re.match(r"^\s*[-/\\–—]+\s*$", raw.translate(_FULLWIDTH)) \
            or low.rstrip(".") in ("nd", "na", "n/a", "n.d") \
            or low in ("\u672a\u68c0\u51fa",
                       "\u672a\u68c0\u6d4b", "\u672a\u9274\u5b9a") \
            or re.match(r"^[<\uff1c]\s*(q\.?\s*l\.?|\d)", low) \
            or re.match(r"^[<\uff1c]\s*\d", raw.translate(_FULLWIDTH)):
        return "notdetected"
    if re.search(r"\d\s*(?:\u00b1|\+/-)\s*\d", raw):
        return "pm"
    if re.search(r"\d\s*(?:\u00b1|\+/-)\s*$", raw):
        return "pm"
    if re.search(r"\d\s*[-\u2013~]\s*\d", raw) and not raw.strip().startswith("-"):
        return "range"
    body = _digits_only(raw)
    if not body:
        return "text"
    if re.match(r"^[<>]?\d{1,3}(?:\.\d{3})*,\d+$", body):   # 4.200,000
        return "num"
    if re.match(r"^[<>]?\d+(\.\d+)?$", body):
        return "pm" if "\u00b1" in raw else ("lt" if body[0] == "<" else "num")
    if re.match(r"^\d+(\.\d+)?[a-zA-Z\u00b5\u03bc%\/]*$", body):
        return "num"
    return "text"

# A unit can be written in any of the three bracket styles the papers use. Checking only
# parentheses reported every "[mg/L]" column as unitless, which buried the real faults.
UNIT_IN_HEAD = re.compile(r"[\(\[]\s*[^)\]]{1,14}\s*[\)\]]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default="")
    ap.add_argument("--out", default="",
                    help="also write the report to this file, in UTF-8")
    a = ap.parse_args()
    import report_out
    sys.stdout = report_out.open_report(a.out)

    import openpyxl
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)

    grand = dict(sheets=0, rows=0, cols=0, unitless=0, nonnum=0, pm=0,
                 rng=0, lt=0, blanks=0, nd=0)
    for sn in wb.sheetnames:
        if sn == "00_索引" or a.sheet not in (sn, ""):
            continue
        if a.sheet and a.sheet not in sn:
            continue
        rows = list(wb[sn].iter_rows(values_only=True))
        for start, end in blocks.find_data_blocks(rows):
            heads = rows[start]
            ncols = len([h for h in heads if h is not None])
            data_cols = [(ci, str(h)) for ci, h in enumerate(heads)
                         if h and re.match(r"^(浓度|阈值|OAV|香气强度)", str(h))]
            if not data_cols:
                continue
            grand["sheets"] += 1
            grand["cols"] += len(data_cols)
            unitless = []
            for ci, head in data_cols:
                # An OAV is a ratio of concentration to threshold, so it has no unit and
                # must not be reported as missing one.
                if head.startswith("OAV"):
                    continue
                has_unit = bool(UNIT_IN_HEAD.search(head))
                n = nonnum = pm = rng = lt = blanks = 0
                texts = []
                nd = 0
                for row in rows[start + 1:end]:
                    if not row or row[0] is None or not str(row[0]).strip():
                        continue
                    v = row[ci] if ci < len(row) else None
                    if v is None or str(v).strip() == "":
                        blanks += 1
                        continue
                    n += 1
                    s = str(v).strip()
                    # Classify before judging. "1.02± 0.695" is a legitimate mean with its
                    # standard deviation and a lone "-" means not detected; lumping either
                    # in with prose buries the cells that really are wrong.
                    kind = classify(s)
                    if kind == "notdetected":
                        nd += 1
                    elif kind == "pm":
                        pm += 1
                    elif kind == "range":
                        rng += 1
                    elif kind == "lt":
                        lt += 1
                    elif kind == "text":
                        nonnum += 1
                        if len(texts) < 8:
                            texts.append(s)
                grand["rows"] += n
                grand["nonnum"] += nonnum
                grand["pm"] += pm
                grand["rng"] += rng
                grand["lt"] += lt
                grand["blanks"] += blanks
                grand["nd"] += nd
                if not has_unit:
                    unitless.append((head, n))
                if texts:
                    print("  文本值    %-16s %-30s %s"
                          % (sn[:16], head[:30], " / ".join(t[:14] for t in texts[:4])))
            if unitless:
                grand["unitless"] += len(unitless)
                for head, n in unitless:
                    print("  无单位列  %-16s %-34s %d 个值"
                          % (sn[:16], head[:34], n))
    wb.close()

    print()
    print("=" * 66)
    print("CONCENTRATION AUDIT")
    print("=" * 66)
    print("   basic-data blocks        %d" % grand["sheets"])
    print("   concentration columns     %d" % grand["cols"])
    print("   value cells               %d" % grand["rows"])
    print("   columns with no unit      %d" % grand["unitless"])
    print("   empty cells               %d" % grand["blanks"])
    print("   plain numbers             %d"
          % (grand["rows"] - grand["nonnum"] - grand["pm"] - grand["rng"] - grand["lt"]))
    print("   mean +/- sd               %d   (a value plus its dispersion)"
          % grand["pm"])
    print("   ranges                    %d" % grand["rng"])
    print("   below-detection limits    %d" % grand["lt"])
    print("   reported not detected    %d" % grand["nd"])
    print("   TEXT where a number belongs %d" % grand["nonnum"])
    return 0


if __name__ == "__main__":
    sys.exit(main())