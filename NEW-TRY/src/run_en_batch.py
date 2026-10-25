# -*- coding: utf-8 -*-
"""
Batch-run the English raster pipeline (s1..s5) over every mapped PDF that has no text
layer.

Why a batch runner rather than five looped calls: the five steps pass work through
files on disk (tables.json, img/, ocr/, grid/), so each paper needs its own output
tree. Setting NEWTRY_OUT per paper redirects every path in common.py at once, which
is the only place the steps read their directories from - the steps themselves are
unchanged and stay usable one paper at a time.

Steps, per paper:
    s1 detect three-line tables, render two crops each (300dpi pass A, 400dpi pass B)
    s2 Umi-OCR: pass A English, pass B English, pass C Chinese as a symbol donor
    s3 rebuild the grid from OCR boxes, diff A against B, repair symbols
    s4 re-render disagreeing cells at 600dpi and take the admissible value
    s5 write one workbook per paper

Resumable: a paper whose step-5 workbook already exists is skipped unless --force.
OCR is by far the slowest stage, so an interrupted run continues where it stopped.

Usage:
    python src/run_en_batch.py                 # every English paper needing OCR
    python src/run_en_batch.py --only 1,3      # only these sheet indices
    python src/run_en_batch.py --force         # redo even if finished
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REOUT = os.path.join(ROOT, "out", "re整理")
BATCH = os.path.join(ROOT, "out", "en_batch")
MAP = os.path.join(REOUT, "sheet_map.json")

PY = sys.executable or "python"
STEPS = ["s1_detect_tables.py", "s2_umi_ocr.py", "s3_verify_grid.py",
         "s4_rescue_cells.py", "s5_to_excel.py"]


def run(script, args, outdir, logf, timeout):
    env = dict(os.environ)
    env["NEWTRY_OUT"] = outdir
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
            fh.write("TIMEOUT after %ss\n" % timeout)
            rc = -9
    return rc, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma separated sheet indices")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-pages", type=int, default=0, help="limit pages (debug)")
    ap.add_argument("--timeout", type=int, default=3600, help="per-step seconds")
    ap.add_argument("--start", default="s1_detect_tables.py", choices=STEPS)
    a = ap.parse_args()

    entries = json.load(open(MAP, encoding="utf-8"))
    only = {int(x) for x in a.only.split(",") if x.strip()}
    os.makedirs(BATCH, exist_ok=True)

    todo = []
    for e in entries:
        if only and e["idx"] not in only:
            continue
        if e.get("lang") != "en" or not e.get("path") \
                or not os.path.exists(e["path"]):
            continue
        todo.append(e)

    print("English papers needing the image pipeline: %d" % len(todo))
    si = STEPS.index(a.start)
    for n, e in enumerate(todo, 1):
        idx = e["idx"]
        od = os.path.join(BATCH, "%02d" % idx)
        os.makedirs(od, exist_ok=True)
        xlsx = os.path.join(od, "tables_extracted.xlsx")
        if os.path.exists(xlsx) and not a.force:
            print("[%d/%d] #%-3d skip (workbook exists)" % (n, len(todo), idx), flush=True)
            continue
        logf = os.path.join(od, "run.log")
        print("[%d/%d] #%-3d %s" % (n, len(todo), idx,
                                    (e.get("pdf") or "")[:52]), flush=True)
        t0 = time.time()
        for s in STEPS[si:]:
            args = []
            if s == "s1_detect_tables.py":
                args = [e["path"]]
                if a.max_pages:
                    args += ["--max-pages", str(a.max_pages)]
            rc, dt = run(s, args, od, logf, a.timeout)
            print("      %-24s rc=%-3d %6.1fs" % (s, rc, dt), flush=True)
            if rc != 0:
                print("      ABORT at %s (see %s)" % (s, logf), flush=True)
                break
        print("      total %.1fs -> %s" % (time.time() - t0, od), flush=True)

    print("\nall done -> %s" % BATCH)


if __name__ == "__main__":
    main()
