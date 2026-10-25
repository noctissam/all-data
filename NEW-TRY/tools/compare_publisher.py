# -*- coding: utf-8 -*-
"""
Measure the OCR pipeline against the publisher's own cell strings.

The article was captured from ScienceDirect under institutional access, so
out/../publisher_tables.json holds exactly what the typesetter produced. Comparing
that against the OCR reconstruction answers the question that matters for the
priority-1 fields: how often is a concentration, a threshold or a compound name wrong,
and when it is wrong, does the pipeline notice?

Two numbers per table:
  exact      cell identical after normalising dashes / spaces
  wrong      digits or letters differ  -> this is what would corrupt a dataset
  missed     publisher has a glyph, OCR produced nothing (a "-" placeholder lost)
  extra      OCR invented something the publisher did not print

Usage:
    python tools/compare_publisher.py
"""

import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from common import GRID_DIR, load_json, load_tables  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

# publisher table index -> our reconstructed table id
MAP = {"T0": "T01_p02", "T1": "T02_p04", "T2": "T03_p05",
       "T3": "T04_p10", "T4": "T05_p11", "T5": "T06_p12"}


def norm(s):
    """Compare like-for-like: unify dash variants, thin spaces, and strip."""
    s = unicodedata.normalize("NFKC", s or "")
    for d in "−–—‒‐":
        s = s.replace(d, "-")
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def digits(s):
    return re.sub(r"[^0-9]", "", norm(s))


def flat_cells(g):
    """Reconstructed grid -> {(section,row,col): text} with merged cells dropped."""
    out = {}
    for sec in ("header", "body"):
        for r, row in enumerate(g[sec]):
            for c, cell in enumerate(row):
                if cell["span"] >= 0:
                    out[(sec, r, c)] = cell["text"]
    return out


KEY_RE = re.compile(r"^\d{1,2}(-\d{1,2})?$")


def keyed_rows(rows, keycol=0):
    """
    Index data rows by the paper's own compound number instead of by position.

    Aligning on row order produces nonsense here: the publisher's Table 2 spans pages
    3-4 and our crop only sees the page-4 tail, and the omission-analysis table uses
    rowspan so one printed row becomes several extracted rows. Both are structural
    facts about the source, not recognition errors, and matching on the key keeps the
    comparison about cell CONTENT.
    """
    keyed = {}
    order = []
    for r in rows:
        if not r:
            continue
        k = (r[keycol] or "").strip()
        if not KEY_RE.match(k):
            continue
        keyed.setdefault(k, []).append(r)
        order.append(k)
    return keyed, order


def merge_multi(rows):
    """Collapse the several extracted lines one printed row produced."""
    w = max(len(r) for r in rows)
    out = []
    for c in range(w):
        parts = [r[c] for r in rows if c < len(r) and r[c]]
        out.append(" ".join(parts))
    return out


def pub_body_rows(tbl):
    """Publisher grid -> list of 7-wide rows, header rows removed."""
    rows = [[norm(x) for x in r] for r in tbl]
    body = []
    for r in rows:
        # a data row always starts with the paper's own compound index
        if r and re.fullmatch(r"\d{1,2}", r[0] or "") and len(r) > 2:
            body.append(r)
    return body


def pub_header_rows(tbl):
    rows = [[norm(x) for x in r] for r in tbl]
    head = []
    for r in rows:
        if r and re.fullmatch(r"\d{1,2}", r[0] or ""):
            break
        head.append(r)
    return head


def main():
    pub = json.load(open(os.path.join(ROOT, "publisher_tables.json"), encoding="utf-8"))
    print("publisher tables: " + ", ".join("%s(%dx%d)" % (k, len(v), len(v[0]))
                                           for k, v in sorted(pub.items())))
    print()
    tot = dict(exact=0, wrong=0, missed=0, extra=0)
    diffs = []

    for pk, ours_id in MAP.items():
        gp = os.path.join(GRID_DIR, "%s_grid.json" % ours_id)
        if not os.path.exists(gp):
            print("  %s missing" % ours_id)
            continue
        g = load_json(gp)
        pbody = pub_body_rows(pub[pk])
        obody = [[c["text"] for c in row if c["span"] >= 0] for row in g["body"]]

        pk_map, _po = keyed_rows(pbody)
        ok_map, _oo = keyed_rows(obody)

        only_pub = [k for k in pk_map if k not in ok_map]
        only_ocr = [k for k in ok_map if k not in pk_map]
        shared = [k for k in pk_map if k in ok_map]

        st = dict(exact=0, wrong=0, missed=0, extra=0)
        for k in shared:
            pr = merge_multi(pk_map[k]) if len(pk_map[k]) > 1 else pk_map[k][0]
            orr = merge_multi(ok_map[k]) if len(ok_map[k]) > 1 else ok_map[k][0]
            for j in range(max(len(pr), len(orr))):
                a = pr[j] if j < len(pr) else ""
                b = orr[j] if j < len(orr) else ""
                if a == b:
                    st["exact"] += 1
                elif a == "" and b != "":
                    st["extra"] += 1
                    diffs.append([ours_id, k, j + 1, "extra", a, b])
                elif a != "" and b == "":
                    st["missed"] += 1
                    diffs.append([ours_id, k, j + 1, "missed", a, b])
                elif digits(a) == digits(b) and len(a) == len(b):
                    st["exact"] += 1
                else:
                    kind = "digits_differ" if digits(a) != digits(b) else "text_differ"
                    st["wrong"] += 1
                    diffs.append([ours_id, k, j + 1, kind, a, b])

        for k in only_pub:
            n = len(pk_map[k][0])
            st["missed"] += n
            diffs.append([ours_id, k, -1, "row_not_detected",
                          " | ".join(pk_map[k][0])[:60], ""])
        for k in only_ocr:
            n = len(ok_map[k][0])
            st["extra"] += n
            diffs.append([ours_id, k, -1, "row_not_in_publisher",
                          "", " | ".join(ok_map[k][0])[:60]])

        n = sum(st.values())
        print("  %-9s rows pub/ocr=%-3d/%-3d matched=%-3d | cells=%-5d exact=%-5d wrong=%-4d missed=%-4d extra=%d"
              % (ours_id, len(pk_map), len(ok_map), len(shared), n, st["exact"],
                 st["wrong"], st["missed"], st["extra"]))
        if only_pub:
            print("             rows the publisher has that we did not extract: %s"
                  % ", ".join(only_pub[:14]) + (" ..." if len(only_pub) > 14 else ""))
        for k in tot:
            tot[k] += st[k]

    n = sum(tot.values())
    print()
    print("TOTAL data cells=%d  exact=%d (%.2f%%)  wrong=%d (%.3f%%)  missed=%d  extra=%d"
          % (n, tot["exact"], 100.0 * tot["exact"] / max(n, 1),
             tot["wrong"], 100.0 * tot["wrong"] / max(n, 1),
             tot["missed"], tot["extra"]))

    import csv
    outp = os.path.join(ROOT, "out", "ocr_vs_publisher.csv")
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    with open(outp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["table", "row", "col", "kind", "publisher", "ocr"])
        w.writerows(diffs)
    print("diffs -> %s  (%d rows)" % (os.path.relpath(outp, ROOT), len(diffs)))

    # group the differences so the pattern is visible rather than the individual cells
    import collections
    kinds = collections.Counter(d[3] for d in diffs)
    print()
    print("difference kinds: " + ", ".join("%s=%d" % (k, v) for k, v in kinds.most_common()))

    numeric_bad = [d for d in diffs if d[3] == "digits_differ"]
    if numeric_bad:
        print()
        print("--- numeric disagreements (these would corrupt a dataset) ---")
        for d in numeric_bad[:25]:
            print("  %-9s row#%-4s col%-3d publisher=%-18r ocr=%r"
                  % (d[0], d[1], d[2], d[4][:18], d[5][:18]))
        if len(numeric_bad) > 25:
            print("  ... %d more" % (len(numeric_bad) - 25))

    missed_glyph = [d for d in diffs if d[3] == "missed"]
    if missed_glyph:
        vals = collections.Counter(d[4] for d in missed_glyph)
        print()
        print("--- missed glyphs: what the publisher printed that we returned empty ---")
        print("   ", ", ".join("%r x%d" % (k[:14], v) for k, v in vals.most_common(12)))


if __name__ == "__main__":
    main()
