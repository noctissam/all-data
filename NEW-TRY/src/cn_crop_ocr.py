# -*- coding: utf-8 -*-
"""
Crop each detected table fragment at full resolution and OCR it with Umi-OCR.

The thesis pages are 300 dpi scans, so 300 dpi is the ceiling - rendering higher would
upsample and invent no detail.

  pass A  Simplified Chinese  primary. This is a Chinese document, and the Chinese
                                dictionary is also the only one here that carries the
                                Greek letters and "+/-".
  pass B  English             verification, as in the English pipeline.

Usage:
    python src/cn_crop_ocr.py --pdf "<pdf>" [--dpi 300] [--pad-pt 5] [--no-pass-b]
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

from common import save_json  # noqa: E402

API = "http://127.0.0.1:1224/api/ocr"


def api_ready(timeout=8.0, tries=12, pause=5.0):
    """
    Wait for the engine instead of failing the first time.

    Umi-OCR serves one request at a time. When another job already has a long page in
    flight, the port still accepts connections but the probe does not come back within
    a short timeout, and a single-shot check reports "engine is not answering" while
    the engine is perfectly alive and merely busy. Retrying for a minute turns a
    spurious abort into a short queue.
    """
    for k in range(tries):
        try:
            urllib.request.urlopen(API.replace("/api/ocr", "/api/ocr/get_options"),
                                   timeout=timeout).read()
            return True
        except Exception:
            time.sleep(pause)
    return False


def ocr_b64(b64, lang, timeout=900):
    body = json.dumps({"base64": b64, "options": {
        "ocr.language": lang, "ocr.angle": False, "ocr.maxSideLen": 999999,
        "tbpu.parser": "none", "data.format": "dict"}}).encode("utf-8")
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    res = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return res["data"] if res.get("code") == 100 else []


def text_block_left(arr):
    """x of the leftmost inked column, matching what the detector assumed."""
    col = arr < 128
    body = np.where(col.mean(axis=1) > 0.01)[0]
    if len(body) == 0:
        return 0
    return int(col[:, body.min():body.max()].any(axis=0).argmax())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--cand", default=os.path.join("out", "cn", "candidates.json"))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--pad-pt", type=float, default=5.0)
    ap.add_argument("--lang", default="简体中文")
    ap.add_argument("--lang-b", default="English")
    ap.add_argument("--no-pass-b", action="store_true")
    ap.add_argument("--imgdir", default=os.path.join("out", "cn", "img"))
    ap.add_argument("--out", default=os.path.join("out", "cn", "ocr_raw.json"))
    a = ap.parse_args()

    if not api_ready():
        raise SystemExit("Umi-OCR engine is not answering on 127.0.0.1:1224")

    cand = json.load(open(a.cand, encoding="utf-8"))
    os.makedirs(a.imgdir, exist_ok=True)
    doc = pymupdf.open(a.pdf)
    cache = {}

    def gray(pno):
        if pno not in cache:
            page = doc[pno - 1]
            pix = page.get_pixmap(dpi=cand["dpi"], colorspace=pymupdf.csGRAY, alpha=False)
            cache[pno] = (page, np.asarray(Image.frombytes(
                "L", (pix.width, pix.height), pix.samples)))
        return cache[pno]

    out = []
    for i, c in enumerate(cand["candidates"], 1):
        pno = c["page"]
        page, arr = gray(pno)
        pr = page.rect
        ys = int(c["y_top_pt"] * cand["dpi"] / 72.0)
        ye = int(c["y_bot_pt"] * cand["dpi"] / 72.0)
        blk = arr[max(0, ys):ye + 1]
        inked = np.where((blk < 128).mean(axis=0) > 0.02)[0]
        if len(inked) == 0:
            continue

        # BOTH crop edges come from the fragment's own inked extent, in page coordinates.
        # Two earlier versions got this wrong in opposite directions: deriving the left
        # edge from the first detected gutter amputated the first column (the widest
        # blank strip on p30 is the page margin, not a column gutter), and then adding
        # tx0 on top of `inked` double-counted the offset and shrank the crop to a third
        # of the table. `blk` is sliced from the full-page array, so its columns are
        # already absolute - do not shift them again.
        # `inked` indexes `blk`, which was sliced from the array rendered at the DETECT
        # dpi, so it must be converted with cand["dpi"] - dividing by the render dpi
        # halved every crop width.
        k = cand["dpi"] / 72.0
        x_lo = (int(inked.min()) - 14) / k
        x_hi = (int(inked.max()) + 14) / k
        rect = pymupdf.Rect(x_lo - a.pad_pt, c["y_top_pt"] - a.pad_pt,
                            x_hi + a.pad_pt, c["y_bot_pt"] + a.pad_pt) & pr
        if rect.is_empty:
            continue

        pix = page.get_pixmap(clip=rect, dpi=a.dpi, colorspace=pymupdf.csRGB, alpha=False)
        name = "T%02d_p%02d" % (i, pno)
        img_path = os.path.join(a.imgdir, name + ".png")
        pix.save(img_path)
        b64 = base64.b64encode(open(img_path, "rb").read()).decode("ascii")

        t0 = time.time()
        boxes_a = ocr_b64(b64, a.lang)
        rec = dict(id="T%02d" % i, page=pno, img=img_path,
                   rect=[round(v, 1) for v in rect],
                   kind=c["kind"], height_pt=c["height_pt"],
                   n_gutters_detect=c["n_gutters"],
                   passA=dict(lang=a.lang, boxes=boxes_a))
        if not a.no_pass_b:
            rec["passB"] = dict(lang=a.lang_b, boxes=ocr_b64(b64, a.lang_b))
        rec["seconds"] = round(time.time() - t0, 1)
        out.append(rec)
        sc = [b["score"] for b in boxes_a]
        print("  %-9s p%-3d %4dx%-4d gutters=%-2d boxes=%-4d avg=%.3f %.1fs" % (
            name, pno, pix.width, pix.height, c["n_gutters"], len(boxes_a),
            sum(sc) / max(len(sc), 1), rec["seconds"]))

    save_json(dict(pdf=os.path.abspath(a.pdf), dpi=a.dpi, n=len(out), tables=out), a.out)
    print("done: %d crops -> %s" % (len(out), a.out))


if __name__ == "__main__":
    main()
