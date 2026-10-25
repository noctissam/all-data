# -*- coding: utf-8 -*-
"""
Step 2 - run Umi-OCR on every table image.

    pass A  *_A.png  (dpi 300, English)  -> primary extraction
    pass B  *_B.png  (dpi 400, English)  -> verification extraction, same content
    pass C  *_A.png  (dpi 300, Chinese)  -> symbol donor, see s3.repair()

Pass C exists because the English model is driven by dict_en.txt - 94 entries, all
ASCII - so it has no mu, no plusminus, no gamma and can only ever emit a wrong ASCII
lookalike. The Chinese model's dictionary does contain them. Pass C is never trusted
for words or numbers, only for characters pass A and B cannot spell at all.

All passes keep the raw box coordinates (data.format=dict) and skip the layout
parser (tbpu.parser=none), because a three-line table has no paragraphs - the grid is
rebuilt from box geometry in step 3.

The Umi-OCR engine is the local install
    C:\\UMI-OCR\\Umi-OCR_Rapid_v2.1.3\\Umi-OCR.exe
driven over its local HTTP API (127.0.0.1:1224).  If the engine is not running it is
started once and reused; results are cached on disk so a re-run skips finished images.

Usage:
    python src/s2_umi_ocr.py [--lang English] [--max-side 999999] [--restart]
"""

import argparse
import base64
import glob
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (IMG_DIR, LOG_DIR, OCR_DIR, UMI_API_PORT, UMI_EXE, UMI_DATA,  # noqa: E402
                    ensure_dirs, load_tables, log, save_json)

API = "http://127.0.0.1:%d/api/ocr" % UMI_API_PORT


def api_ready(timeout=1.5):
    try:
        urllib.request.urlopen(API.replace("/api/ocr", "/api/ocr/get_options"),
                               timeout=timeout).read()
        return True
    except Exception:
        return False


def start_engine(logfile):
    log("Umi-OCR engine not running - starting %s" % UMI_EXE, logfile)
    subprocess.Popen([UMI_EXE], cwd=UMI_DATA,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for i in range(90):
        time.sleep(1.0)
        if api_ready():
            log("engine ready after %ds" % (i + 1), logfile)
            return True
    log("engine failed to start within 90s", logfile)
    return False


def ocr_file(path, opts, logfile, retries=2):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    body = json.dumps({"base64": b64, "options": opts}).encode("utf-8")
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(API, data=body,
                                         headers={"Content-Type": "application/json"})
            res = json.loads(urllib.request.urlopen(req, timeout=900).read())
        except Exception as e:
            log("  request failed (%s) - retry %d" % (e, attempt + 1), logfile)
            time.sleep(3)
            if not api_ready() and not start_engine(logfile):
                return None
            continue
        if res.get("code") != 100:
            log("  engine returned code=%s %s" % (res.get("code"), res.get("data")), logfile)
            time.sleep(2)
            continue
        return dict(image=os.path.basename(path), seconds=round(time.time() - t0, 1),
                    options=opts, boxes=res["data"])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="English", help="model for passes A and B")
    ap.add_argument("--lang-c", default="简体中文",
                    help="model for the symbol-donor pass C (needs a dictionary "
                         "containing mu / +- / gamma; English's has none)")
    ap.add_argument("--no-pass-c", dest="pass_c", action="store_false",
                    help="skip pass C, disabling symbol repair")
    ap.add_argument("--max-side", type=int, default=999999)
    ap.add_argument("--angle", action="store_true")
    ap.add_argument("--restart", action="store_true", help="ignore cached ocr json")
    a = ap.parse_args()      # pass_c defaults to True (store_false)

    ensure_dirs()
    logfile = os.path.join(LOG_DIR, "s2_ocr.log")
    if os.path.exists(logfile):
        os.remove(logfile)

    db = load_tables()
    opts = {"ocr.language": a.lang, "ocr.angle": a.angle,
            "ocr.maxSideLen": a.max_side, "tbpu.parser": "none",
            "data.format": "dict"}

    log("STEP 2 - Umi-OCR multi pass", logfile)
    log("engine: %s" % UMI_EXE, logfile)
    log("pass A/B: lang=%s   pass C: lang=%s (symbol donor)"
        % (a.lang, a.lang_c if a.pass_c else "disabled"), logfile)
    log("options: maxSideLen=%s parser=none format=dict" % a.max_side, logfile)

    if a.restart:
        for p in glob.glob(os.path.join(OCR_DIR, "*.json")):
            os.remove(p)
    if not api_ready() and not start_engine(logfile):
        raise SystemExit("Umi-OCR engine unavailable")
    else:
        log("engine already running on port %d" % UMI_API_PORT, logfile)

    # pass A and B: English model, two independent renders -> the extraction + its check
    # pass C:        Chinese model on image A -> symbol donor only (see s3.repair)
    passes = [
        ("A", "img_a", db["meta"]["dpi_main"], a.lang, opts),
        ("B", "img_b", db["meta"]["dpi_check"], a.lang, opts),
        ("C", "img_a", db["meta"]["dpi_main"], a.lang_c, dict(opts, **{"ocr.language": a.lang_c})),
    ]

    total = fail = 0
    t_start = time.time()
    for t in db["tables"]:
        for pass_id, key, dpi, lang, popts in passes:
            if pass_id == "C" and not a.pass_c:
                continue
            rel = t[key]
            src = os.path.join(IMG_DIR, os.path.basename(rel))
            dst = os.path.join(OCR_DIR, "%s_%s.json" % (t["name"], pass_id))
            total += 1
            if os.path.exists(dst) and not a.restart:
                log("  %s pass %s  cached" % (t["id"], pass_id), logfile)
                continue
            if not os.path.exists(src):
                log("  %s pass %s  MISSING IMAGE %s" % (t["id"], pass_id, src), logfile)
                fail += 1
                continue
            r = ocr_file(src, popts, logfile)
            if not r:
                log("  %s pass %s  FAILED" % (t["id"], pass_id), logfile)
                fail += 1
                continue
            r["table_id"] = t["id"]
            r["page"] = t["page"]
            r["pass"] = pass_id
            r["language"] = lang
            r["dpi"] = dpi
            r["src_pdf_rect"] = t["crop"]
            save_json(r, dst)
            n = len(r["boxes"])
            log("  %s pass %s  %5.1fs  boxes=%d  score_avg=%.3f  -> %s" % (
                t["id"], pass_id, r["seconds"], n,
                sum(b["score"] for b in r["boxes"]) / max(n, 1), os.path.basename(dst)), logfile)

    log("done: %d images, %d failed, %.1fs total" % (
        total, fail, time.time() - t_start), logfile)


if __name__ == "__main__":
    main()
