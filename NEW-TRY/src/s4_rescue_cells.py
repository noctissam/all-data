# -*- coding: utf-8 -*-
"""
Step 4 - targeted rescue of individual suspicious cells.

The whole-page pass can lose a glyph that a close-up reads perfectly: on T01 the "+/-"
of "717.6 +/- 38.8" never came back as its own box at page scale, but re-rendering just
that cell at 600 dpi puts it right there and the Chinese model reads it correctly.
(1200 dpi is worse - the detector starts splitting the cell and the reading order
reverses - so 600 is the ceiling.)

Which cells get a second look:
  - cells where passes A and B disagreed
  - cells below the confidence threshold
  - cells shaped like "number <separator> number" where the separator is missing or is
    an ASCII stand-in from {+ * : = ~ H} - the signature of a "+/-" that went missing

Arbitration is deliberately conservative. A rescue reading is adopted when it
introduces a whitelisted symbol (see s3.DONOR_CHARS) with an unchanged alphanumeric
skeleton - the same rule the symbol-donor pass uses. Anything else needs a strictly
higher score AND an unchanged skeleton, so a close-up can never silently rewrite a
word or a number. Every rescue is written to <name>_rescue.csv.

Usage:
    python src/s4_rescue_cells.py [--dpi 600] [--conf 0.80] [--max-cells 400]
"""

import argparse
import base64
import csv
import json
import os
import re
import statistics
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymupdf  # noqa: E402

import s3_verify_grid as S  # noqa: E402
from common import (GRID_DIR, LOG_DIR, OCR_DIR, UMI_API_PORT, ensure_dirs,  # noqa: E402
                    load_json, load_tables, log)

API = "http://127.0.0.1:%d/api/ocr" % UMI_API_PORT

# "1,234.5  67"  or  "622,200 + 1786"  - two numbers with something between them
PAIR_RE = re.compile(r"^\s*[\d][\d.,]*\s*(.*?)\s*[\d][\d.,]*\s*$")
STANDIN = set("+*:=~H|^<>Λ")


def suspicious(text, flagged):
    if flagged:
        return "flagged"
    m = PAIR_RE.match(text)
    if not m:
        return None
    sep = m.group(1)
    if sep == "":
        return "missing_sep"
    if all(ch in STANDIN for ch in sep):
        return "standin_sep"
    return None


def ocr_b64(b64, lang, timeout=600):
    data = {"base64": b64,
            "options": {"ocr.language": lang, "ocr.angle": False,
                        "ocr.maxSideLen": 999999, "tbpu.parser": "none",
                        "data.format": "dict"}}
    req = urllib.request.Request(API, data=json.dumps(data).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    res = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return res["data"] if res.get("code") == 100 else []


def line_geometry(ocr, table, cfg):
    """Row y-extents and run lists for the body, so a cell can be located in the PDF."""
    boxes = S.to_points(ocr, table)
    med_h = statistics.median([b["y1"] - b["y0"] for b in boxes])
    boxes = [b for b in boxes if not S.rule_like(b, med_h, med_h)]
    S.tag_zones(boxes, table, med_h)
    body = S.lines_of([b for b in boxes if b["zone"] == "body"],
                      cfg["row_gap"] * med_h, cfg["min_gap"])
    return body, med_h


def crop_cell(doc, table, run_bbox, dpi):
    x0, y0, x1, y1 = run_bbox
    rect = pymupdf.Rect(x0 - 2.0, y0 - 2.5, x1 + 2.0, y1 + 2.5)
    rect = rect & doc[table["page"] - 1].rect
    if rect.is_empty or rect.width < 1 or rect.height < 1:
        return None
    return doc[table["page"] - 1].get_pixmap(clip=rect, dpi=dpi,
                                             colorspace=pymupdf.csRGB, alpha=False)


def admissible(current, cand):
    """
    Guard for the score-based rewrite: a close-up may only ADD detail, never remove it,
    and never introduce a non-ASCII character outside the donor whitelist. Two real
    regressions motivated this:

        "- 0.0005" -> " 0.0005"     highest-scoring reading had lost the minus sign
        "<1"       -> "\u039b1"      Chinese close-up read the "<" as Greek capital lamda

    Requiring the candidate to contain every non-space character of the current value
    blocks the first; requiring its non-ASCII characters to be whitelisted blocks the
    second. The price is that a spurious character added at page level cannot be
    removed here - the cell stays flagged for review instead.

    This deliberately does NOT gate the symbol path. Replacing "+" with "+/-" removes
    the "+" and is the whole point of that path; s3.repair already restricts it to
    whitelisted characters with an unchanged alphanumeric skeleton.
    """
    cur = {ch for ch in current if not ch.isspace()}
    new = {ch for ch in cand if not ch.isspace()}
    if not cur <= new:
        return False
    for ch in cand:
        if ord(ch) > 127 and ch not in S.DONOR_CHARS:
            return False
    return True


def choose(current, cur_score, readings):
    """
    readings: list of (text, score) from the close-up passes.

    The current value competes as a candidate - comparing only the close-ups against
    each other threw away a "+/-" that the symbol-donor pass had already established,
    because the English close-up outscores the page-level reading it was replacing.
    A candidate that spells a whitelisted symbol the others cannot is preferred over
    one that does not, whatever the scores say: the glyph is on the page.
    """
    cands, seen = [], set()
    for txt, sc in [(current, cur_score)] + list(readings):
        key = S.norm(txt)
        if key and key not in seen:
            seen.add(key)
            cands.append((txt, sc if sc is not None else 0.0))
    if not cands:
        return current, "no_reading"
    for txt, _sc in cands:
        if S.repair(current, txt)[1] == "repaired_C":
            return txt, "rescued_symbol"

    skel = S.skeleton(current)
    pool = [c for c in cands if S.skeleton(c[0]) == skel and admissible(current, c[0])]
    if not pool:
        return current, "kept"
    donors = [c for c in pool if any(ch in S.DONOR_CHARS for ch in c[0])]
    if donors:
        pool = donors
    best = max(pool, key=lambda c: c[1])
    if best[0] != current:
        return best[0], "rescued_score"
    return current, "kept"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpi", type=int, default=600)
    ap.add_argument("--conf", type=float, default=0.80)
    ap.add_argument("--min-gap", type=float, default=4.5)
    ap.add_argument("--row-gap", type=float, default=0.55)
    ap.add_argument("--lang", default="English")
    ap.add_argument("--lang-c", default="简体中文")
    ap.add_argument("--max-cells", type=int, default=400)
    a = ap.parse_args()
    cfg = dict(min_gap=a.min_gap, row_gap=a.row_gap)

    logfile = os.path.join(LOG_DIR, "s4_rescue.log")
    if os.path.exists(logfile):
        os.remove(logfile)
    log("STEP 4 - targeted cell rescue at %d dpi" % a.dpi, logfile)

    db = load_tables()
    doc = pymupdf.open(db["meta"]["pdf"])
    grand = dict(symbol=0, score=0, kept=0, none=0)

    for t in db["tables"]:
        name = t["name"]
        gp = os.path.join(GRID_DIR, "%s_grid.json" % name)
        ap_ = os.path.join(OCR_DIR, "%s_A.json" % name)
        if not (os.path.exists(gp) and os.path.exists(ap_)):
            continue
        grid = load_json(gp)
        flagged = set()
        dp = os.path.join(GRID_DIR, "%s_diff.csv" % name)
        if os.path.exists(dp):
            for row in list(csv.reader(open(dp, encoding="utf-8-sig")))[1:]:
                if row[6].startswith("conflict"):
                    flagged.add((row[3], int(row[4]) - 1, int(row[5]) - 1))
        low = set()
        lp = os.path.join(GRID_DIR, "%s_lowconf.csv" % name)
        if os.path.exists(lp):
            for row in list(csv.reader(open(lp, encoding="utf-8-sig")))[1:]:
                low.add((row[3], int(row[4]) - 1, int(row[5]) - 1))

        body_lines, med_h = line_geometry(load_json(ap_), t, cfg)
        rows_out, n_done = [], 0
        for sec, sec_lines in (("body", body_lines), ("header", None)):
            if sec == "header":
                continue
            for ri, row in enumerate(grid["body"]):
                if ri >= len(sec_lines):
                    continue
                for ci, cell in enumerate(row):
                    if cell["span"] < 0 or ci >= len(grid["bands"]):
                        continue
                    key = (sec, ri, ci)
                    why = suspicious(cell["text"], key in flagged or key in low)
                    if not why:
                        continue
                    band = grid["bands"][ci]
                    sel = [r for r in sec_lines[ri]
                           if r["x0"] < band[1] - 0.5 and r["x1"] > band[0] + 0.5]
                    if not sel:
                        continue
                    bbox = (min(r["x0"] for r in sel), min(r["y0"] for r in sel),
                            max(r["x1"] for r in sel), max(r["y1"] for r in sel))
                    pix = crop_cell(doc, t, bbox, a.dpi)
                    if pix is None:
                        continue
                    b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
                    readings = []
                    for lang in (a.lang_c, a.lang):
                        try:
                            for bx in ocr_b64(b64, lang):
                                readings.append((bx["text"], bx["score"]))
                        except Exception as e:
                            log("  %s %s%d/%d ocr failed: %s" % (t["id"], sec, ri, ci, e), logfile)
                    if not readings:
                        continue
                    new_txt, status = choose(cell["text"], cell["score"], readings)
                    n_done += 1
                    if status == "rescued_symbol":
                        grand["symbol"] += 1
                    elif status == "rescued_score":
                        grand["score"] += 1
                    elif status == "kept":
                        grand["kept"] += 1
                    else:
                        grand["none"] += 1
                    if new_txt != cell["text"]:
                        rows_out.append([t["id"], name, t["page"], sec, ri + 1, ci + 1,
                                         why, status, cell["text"], new_txt,
                                         " | ".join("%s(%.2f)" % (x, s) for x, s in readings)])
                    cell["text"] = new_txt
                    if n_done >= a.max_cells:
                        break
        grid["verify"]["n_rescued"] = len(rows_out)
        grid["verify"]["rescue_dpi"] = a.dpi
        S.save_json(grid, gp)
        with open(os.path.join(GRID_DIR, "%s_rescue.csv" % name), "w",
                  newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["table_id", "name", "pdf_page", "section", "row", "col",
                        "suspicion", "status", "before", "after", "readings"])
            w.writerows(rows_out)
        log("  %s p%02d  examined=%d  changed=%d  -> %s_rescue.csv"
            % (t["id"], t["page"], n_done, len(rows_out), name), logfile)

    doc.close()
    log("rescued: symbol=%d score=%d kept=%d no_reading=%d"
        % (grand["symbol"], grand["score"], grand["kept"], grand["none"]), logfile)


if __name__ == "__main__":
    main()
