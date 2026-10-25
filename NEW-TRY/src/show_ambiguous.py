# -*- coding: utf-8 -*-
"""
Render the page region holding an ambiguous name, so a human can read it.

The problem this solves
-----------------------
Ten names are stuck because OCR swallowed one character and the survivors are equally
plausible: 1-」醇 is 1-butanol or 1-propanol or 1-heptanol, and 乙酸已酯 is eight
different esters. No string rule can choose, because the information is not in the
string - it is in the pixels, where the character either is present or is not.

So the fragment is found in its own PDF and rendered, cropped to the name column, at a
resolution where one hanzi is unmistakable. The crop is taken from the ORIGINAL page,
not from the OCR crop, so nothing the pipeline decided about it can bias the view.

Usage:
    python src/show_ambiguous.py
    python src/show_ambiguous.py --only 3      # just 2-丁酮
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymupdf

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REOUT = os.path.join(ROOT, "out", "re整理")
OUTDIR = os.path.join(ROOT, "out", "review")

# name -> where it was found, filled in at run time
AMBIGUOUS = ["1-」醇", "2-丁酮", "2-了醇", "2-甲基「酸乙酯", "2-羟基丙酸乙酯",
             "2-羟基已酸乙酯", "』酸乙酯", "乙酸已酯", "已酸异戊酯", "庚酸-3-甲基丁酯"]


def locate(names):
    """Which paper and page each ambiguous name appears on, from the OCR json."""
    hits = {n: [] for n in names}
    for fn in sorted(os.listdir(REOUT)):
        m = re.match(r"^(bm|en)_\d+\.json$", fn)
        if not m:
            continue
        idx = int(fn.split("_")[1].split(".")[0])
        d = json.load(open(os.path.join(REOUT, fn), encoding="utf-8"))
        for t in d.get("tables", []):
            for r in t.get("rows", []):
                for cell in r:
                    c = (cell or "").strip()
                    if c in hits:
                        hits[c].append((idx, t["pages"][0] if t.get("pages") else 0,
                                        m.group(1)))
    return hits


def render(name, where):
    """Crop the name column around one occurrence and save it as a PNG."""
    idx, page_no, tag = where
    entries = json.load(open(os.path.join(REOUT, "sheet_map.json"), encoding="utf-8"))
    e = [x for x in entries if x["idx"] == idx][0]
    pdf = e["path"]
    doc = pymupdf.open(pdf)
    if page_no < 1 or page_no > doc.page_count:
        doc.close()
        return None
    page = doc[page_no - 1]
    # the name sits in the leftmost populated column, so crop the left third of the
    # fragment; a full page at 100dpi renders hanzi too small to judge
    rect = pymupdf.Rect(0, 0, page.rect.width * 0.62, page.rect.height)
    pix = page.get_pixmap(clip=rect, dpi=190)
    os.makedirs(OUTDIR, exist_ok=True)
    safe = re.sub(r"[^\w一-鿿]", "_", name)
    out = os.path.join(OUTDIR, "p%02d_%s.png" % (idx, safe))
    pix.save(out)
    doc.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma separated names")
    ap.add_argument("--dpi", type=int, default=190)
    a = ap.parse_args()

    names = [x.strip() for x in a.only.split(",") if x.strip()] or AMBIGUOUS
    hits = locate(names)
    os.makedirs(OUTDIR, exist_ok=True)

    print("ambiguous names and where to look:\n")
    made = []
    for n in names:
        wh = hits.get(n) or []
        if not wh:
            print("  %-22s (not found in any OCR json)" % n)
            continue
        idx, pg, tag = wh[0]
        # render from the original pdf page
        e = [x for x in json.load(open(os.path.join(REOUT, "sheet_map.json"),
                                        encoding="utf-8")) if x["idx"] == idx][0]
        doc = pymupdf.open(e["path"])
        pg = min(max(pg, 1), doc.page_count)
        page = doc[pg - 1]
        rect = pymupdf.Rect(0, 0, page.rect.width * 0.60, page.rect.height)
        pix = page.get_pixmap(clip=rect, dpi=a.dpi)
        safe = re.sub(r"[^\w一-鿿]", "_", n)
        out = os.path.join(OUTDIR, "p%02d_%s.png" % (idx, safe))
        pix.save(out)
        doc.close()
        made.append((n, idx, pg, out))
        print("  %-22s paper #%d p%d  -> %s" % (n, idx, pg, os.path.basename(out)))

    print("\n%d images -> %s" % (len(made), OUTDIR))


if __name__ == "__main__":
    main()
