# -*- coding: utf-8 -*-
"""
Handle papers whose tables are printed sideways.

The problem
-----------
Food Chemistry prints oversized tables rotated 90 degrees on a portrait page, with the
table's caption and footnotes running vertically in the margin. Every stage downstream
assumes text runs horizontally: the detector finds interior blank COLUMNS and uses them
as the column separators, but on a rotated table those same blank bands are horizontal
in page coordinates, so they carry no column information. Cropping and OCRing the
fragment as-is returns sideways text and a grid built on the wrong axis.

Why rotate the file instead of rotating the image
-------------------------------------------------
Rotating a rendered image fixes the text but breaks the detector: the gutters it recorded
are in the unrotated page frame, and after a 90-degree turn they no longer separate
columns. Re-running detection on rotated pages is the only way to get separators in the
same frame as the OCR boxes. Rather than fork the detector, the page rotation is written
into a copy of the PDF (PyMuPDF's set_rotation) so the existing detect/crop/OCR/grid
chain runs unmodified.

Choosing the rotation
---------------------
Rotating is not free - it costs another detection pass over the whole paper - so it is
only done when it actually helps. The test is objective: a real table yields several
interior gutters, a page of body text yields one. Whichever orientation produces more
multi-gutter fragments wins, and a tie keeps the original.

Usage:
    python src/rotate_pdf.py --paper 11            # probe, then write the better copy
    python src/rotate_pdf.py --paper 11 --force 90 # skip the probe
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REOUT = os.path.join(ROOT, "out", "re整理")
MAP = os.path.join(REOUT, "sheet_map.json")
PY = sys.executable or "python"


def write_rotated(src, dst, deg):
    import pymupdf
    d = pymupdf.open(src)
    for p in d:
        p.set_rotation(deg)
    d.save(dst, garbage=0, deflate=False)
    d.close()


def count_tables(pdf, outdir):
    """Run the detector on a throwaway output dir and count multi-gutter fragments."""
    subprocess.run([PY, os.path.join(HERE, "cn_detect_tables.py"), pdf,
                    "--out", outdir],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
    p = os.path.join(outdir, "candidates.json")
    if not os.path.exists(p):
        return 0, 0
    c = json.load(open(p, encoding="utf-8")).get("candidates", [])
    return len(c), sum(1 for x in c if len(x.get("gutters") or []) >= 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=int, required=True)
    ap.add_argument("--force", type=int, default=0, choices=[0, 90, 180, 270])
    a = ap.parse_args()

    e = {x["idx"]: x for x in json.load(open(MAP, encoding="utf-8"))}[a.paper]
    src = e["path"]
    work = os.path.join(ROOT, "out", "bm%02d_rot" % a.paper)
    os.makedirs(work, exist_ok=True)

    if a.force:
        deg = a.force
        print("#%d using forced rotation %d" % (a.paper, deg))
    else:
        tot0, good0 = count_tables(src, os.path.join(work, "probe0"))
        print("#%d original: %d candidates, %d with >=3 gutters" % (a.paper, tot0, good0))
        deg, good = 0, good0
        for cand in (90, 270):
            tmp = os.path.join(work, "r%d.pdf" % cand)
            write_rotated(src, tmp, cand)
            t, g = count_tables(tmp, os.path.join(work, "probe%d" % cand))
            print("#%d rotated %3d: %d candidates, %d with >=3 gutters" % (a.paper, cand, t, g))
            if g > good:
                deg, good = cand, g
        if deg == 0:
            print("#%d original orientation wins; nothing rotated" % a.paper)
            return

    out = os.path.join(work, "rotated.pdf")
    if not os.path.exists(out):
        write_rotated(src, out, deg)
    print("#%d -> %s (rotation %d)" % (a.paper, out, deg))
    print("run next:  python src/run_bitmap_batch.py --papers %d --lang en "
          "--cand %s  (after re-detecting from the rotated pdf)" % (a.paper, out))


if __name__ == "__main__":
    main()
