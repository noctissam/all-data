# -*- coding: utf-8 -*-
"""
Run the bitmap route over papers the vector route cannot handle.

When this is the right route
---------------------------
s1_detect_tables.py reads rules and glyph paths out of the PDF. That works when the
producer leaves them at page level and fails when they are wrapped in Form XObjects -
papers 02, 03, 05, 06 and 07 were all rejected with "median runs/row 2.0 < 3" while
their tables were plainly visible on the page. Reading pixels is immune to how the file
was written, so these go through:

    detect   cn_detect_tables.py  find each fragment and its interior blank gutters
    ocr      cn_crop_ocr.py       render the fragment, OCR it
    grid     bitmap_grid.py       the gutters become the column separators

Candidate filtering
-------------------
The detector also flags ordinary body text, as a single-gutter fragment spanning the
page. Those are dropped: a table has interior column gaps, running prose does not. This
matters for cost as much as for correctness - on the English papers roughly half the
candidates were prose, and OCRing them would burn the whole OCR budget for nothing.

Usage:
    python src/run_bitmap_batch.py --papers 2,3,5,6,7 --lang en
    python src/run_bitmap_batch.py --papers 27 --lang cn --cand out/cn27/candidates_sel.json
"""

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REOUT = os.path.join(ROOT, "out", "re整理")
MAP = os.path.join(REOUT, "sheet_map.json")
PY = sys.executable or "python"


def sh(script, args, logf, timeout=7200):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    t0 = time.time()
    with open(logf, "a", encoding="utf-8") as fh:
        fh.write("\n===== %s %s =====\n" % (script, " ".join(args)))
        fh.flush()
        try:
            p = subprocess.run([PY, os.path.join(HERE, script)] + args,
                               env=env, stdout=fh, stderr=subprocess.STDOUT,
                               timeout=timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            fh.write("TIMEOUT\n")
            rc = -9
    return rc, time.time() - t0


def filter_candidates(src, dst, min_gutters):
    d = json.load(open(src, encoding="utf-8"))
    cands = d["candidates"]
    keep = [c for c in cands if len(c.get("gutters") or []) >= min_gutters]
    out = dict(d)
    out["candidates"] = keep
    out["filtered_from"] = len(cands)
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(cands), len(keep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", required=True, help="comma separated sheet indices")
    ap.add_argument("--lang", default="en", choices=["en", "cn"])
    ap.add_argument("--min-gutters", type=int, default=2)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--cand", default="", help="use this candidate file instead of detecting")
    ap.add_argument("--pdf", default="", help="read a different PDF (e.g. a rotated copy)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    entries = {e["idx"]: e for e in json.load(open(MAP, encoding="utf-8"))}
    papers = [int(x) for x in a.papers.split(",") if x.strip()]
    langA = "English" if a.lang == "en" else "简体中文"
    langB = "简体中文" if a.lang == "en" else "English"

    for idx in papers:
        e = entries[idx]
        outdir = os.path.join(ROOT, "out", "bm%02d" % idx)
        os.makedirs(outdir, exist_ok=True)
        logf = os.path.join(outdir, "run.log")
        final = os.path.join(REOUT, "bm_%02d.json" % idx)
        if os.path.exists(final) and not a.force:
            print("#%-3d skip (bm json exists)" % idx, flush=True)
            continue
        if not e.get("path") or not os.path.exists(e["path"]):
            print("#%-3d skip (no pdf)" % idx, flush=True)
            continue

        cand = os.path.join(outdir, "candidates_sel.json")
        if a.cand:
            cand = a.cand
        else:
            # a rotated copy is a different file, so detection must run against that
            # one - the gutters have to come from the frame the OCR boxes will be in
            pdf = a.pdf or e["path"]
            print("#%-3d detect ..." % idx, flush=True)
            rc, dt = sh("cn_detect_tables.py", [pdf, "--out", outdir], logf)
            if rc != 0:
                print("     detect rc=%d (%.0fs)" % (rc, dt), flush=True)
                continue
            tot, kept = filter_candidates(os.path.join(outdir, "candidates.json"),
                                          cand, a.min_gutters)
            print("     candidates %d -> %d (gutters>=%d)  %.0fs"
                  % (tot, kept, a.min_gutters, dt), flush=True)

        ocr = os.path.join(outdir, "ocr_raw.json")
        print("#%-3d ocr (%s) ..." % (idx, langA), flush=True)
        args = ["--pdf", a.pdf or e["path"], "--cand", cand, "--dpi", str(a.dpi),
                "--lang", langA, "--imgdir", os.path.join(outdir, "img"),
                "--out", ocr]
        if a.lang == "cn":
            args += ["--lang-b", langB]
        else:
            args += ["--no-pass-b"]
        rc, dt = sh("cn_crop_ocr.py", args, logf)
        print("     rc=%d %.0fs" % (rc, dt), flush=True)
        if rc != 0:
            continue

        print("#%-3d grid ..." % idx, flush=True)
        rc, dt = sh("bitmap_grid.py", ["--paper", str(idx), "--cand", cand,
                                       "--ocr", ocr, "--dpi", str(a.dpi),
                                       "--tag", "bm"], logf)
        print("     rc=%d %.0fs" % (rc, dt), flush=True)


if __name__ == "__main__":
    main()
