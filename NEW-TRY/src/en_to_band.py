# -*- coding: utf-8 -*-
"""
Convert the English OCR grids into the same intermediate shape the Chinese band
extractor produces, so one Excel writer serves both.

Why a conversion step at all: the text-layer path (extract_band.py) and the image path
(s1..s5) see the same tables by completely different means - vector rules plus word
boxes versus OCR boxes plus a pass-A/pass-B diff - and store them differently. Letting
each keep its own format would mean two Excel writers, two sets of column-inference
bugs, and two places to fix when a header role is wrong. Normalising here keeps
build_rec整理.py as the single place where a column becomes "the name column" or "a
concentration column".

What carries over, and why each field matters:
    caption    表1/Table 1 text sits above the table and names what the table is
    note       the footnote under it, which is where the unit is often declared
    header     every header row, kept whole - a group header like "Concentration
               (μg/L)" spans two sample columns and splitting it loses the unit
    rows       the body grid, cell by cell, exactly as verified by s3/s4
    verify     the A/B agreement figures, so a suspicious cell can be traced back

Usage:
    python src/en_to_band.py [--only 1,3]
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bitmap_grid as bm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REOUT = os.path.join(ROOT, "out", "re整理")
BATCH = os.path.join(ROOT, "out", "en_batch")
MAP = os.path.join(REOUT, "sheet_map.json")

# Umi-OCR occasionally returns a cell as several boxes; span counts how many boxes
# were merged into that cell, which is a weak signal for "this cell was assembled
# from fragments and may be wrong".
SPAN_SUSPECT = 3


def cell_text(c):
    t = c.get("text")
    if t is None:
        return ""
    return re.sub(r"\s+", " ", str(t).replace("\u00a0", " ")).strip()


def grid_rows(rows):
    out = []
    for r in rows or []:
        out.append([cell_text(c) for c in r])
    if not out:
        return out
    n = max(len(r) for r in out)
    return [r + [""] * (n - len(r)) for r in out]


def spans_of(rows):
    out = []
    for r in rows or []:
        out.append([int(c.get("span") or 0) for c in r] +
                   [0] * (max((len(x) for x in rows), default=0) - len(r)))
    return out


def suspicious(rows, spans):
    """Cells that were stitched from several OCR boxes - flagged, never silently kept."""
    bad = []
    for i, r in enumerate(rows):
        sp = spans[i] if i < len(spans) else []
        for j, c in enumerate(r):
            if j < len(sp) and sp[j] >= SPAN_SUSPECT and c:
                bad.append((i, j, c))
    return bad


def convert(idx):
    d = os.path.join(BATCH, "%02d" % idx)
    files = sorted(glob.glob(os.path.join(d, "grid", "*_grid.json")))
    tables, notes = [], []
    for g in files:
        try:
            t = json.load(open(g, encoding="utf-8"))
        except Exception as e:
            print("   skip %s: %s" % (os.path.basename(g), e))
            continue
        hdr = grid_rows(t.get("header"))
        body = grid_rows(t.get("body"))
        if not body:
            continue
        ncol = t.get("n_col") or max((len(r) for r in hdr + body), default=0)
        # The vector pipeline splits rows the same way the bitmap one does: a name too
        # long for its column keeps its hyphen at the end of one row and continues in the
        # next, leaving an otherwise empty line. Reuse the bitmap repairs rather than
        # writing a second version, since the two routes must produce the same shape.
        if ncol:
            # merge FIRST, then drop orphans. A continuation row holds only the tail of
            # a name and looks exactly like an orphan - dropping it first would delete
            # the second half of "2,3-Diethyl-5- / methylpyrazine" and leave the name
            # truncated with no trace of why.
            body, _n_cont = bm.merge_continuation_rows(body, ncol)
            body, _n_orph = bm.drop_orphan_rows(body, ncol)
        else:
            _n_cont = _n_orph = 0
        sp = spans_of(t.get("body"))
        flag = suspicious(body, sp)
        notes.extend("%s r%d c%d %r" % (t.get("id"), i, j, c) for i, j, c in flag[:40])
        tables.append(dict(
            caption=(t.get("caption_text") or "").strip(),
            note=(t.get("note_text") or "").strip(),
            header_rows=hdr,
            rows=body,
            n_row=len(body),
            n_col=ncol,
            pages=[t.get("page")],
            src_id=t.get("id"),
            long_table=bool(t.get("long_table")),
            verify=t.get("verify") or {},
            n_suspect=len(flag),
        ))
    tables.sort(key=lambda z: (z["pages"][0] or 0))
    agree = [t["verify"].get("agree_pct") for t in tables
             if isinstance(t["verify"].get("agree_pct"), (int, float))]
    return dict(idx=idx, route="ocr" if tables else "ocr-empty",
                note=("A/B agree %.1f%% min, %.1f%% avg" %
                      (min(agree), sum(agree) / len(agree))) if agree else "",
                tables=tables, suspects=notes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()

    entries = {e["idx"]: e for e in json.load(open(MAP, encoding="utf-8"))}
    only = {int(x) for x in a.only.split(",") if x.strip()}
    done = 0
    for idx, e in sorted(entries.items()):
        if only and idx not in only:
            continue
        if not os.path.isdir(os.path.join(BATCH, "%02d" % idx)):
            continue
        r = convert(idx)
        payload = dict(r)
        payload.update(idx=idx, sheet=e.get("sheet"), pdf=e.get("pdf"))
        with open(os.path.join(REOUT, "en_%02d.json" % idx), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        tot = sum(t["n_row"] for t in r["tables"])
        print("  #%-3d tables=%-3d rows=%-5d suspect=%-4d %s"
              % (idx, len(r["tables"]), tot,
                 sum(t["n_suspect"] for t in r["tables"]), r["note"][:52]))
        done += 1
    print("\nconverted %d papers" % done)


if __name__ == "__main__":
    main()
