# -*- coding: utf-8 -*-
"""
Step 3 - rebuild a plain grid from the Umi-OCR boxes, then verify pass A against pass B.

Grid reconstruction (no vertical rules exist in a three-line table, so columns come
from geometry):
  1. map every OCR box back to PDF points, tag it caption / header / body / note using
     the three detected rules;
  2. inside each body line, split boxes into "runs" wherever the horizontal gap is wide;
  3. column separators = gaps that no run in ANY line crosses  (so one long overflowing
     cell cannot hide a real column boundary, because its neighbours fill the gap);
  4. lines -> rows by y clustering; runs -> cells by column; a run crossing several
     columns becomes a merged cell;
  5. pass B is rebuilt the same way AND re-gridded onto pass A's columns, so the two
     extractions can be compared cell by cell.

Outputs per table in out/grid/:
    <name>_grid.json    caption, header rows, body rows, columns, per-cell confidence
    <name>_diff.csv     every cell where A and B disagree
    <name>_lowconf.csv  cells whose OCR confidence is below the threshold

Usage:
    python src/s3_verify_grid.py [--conf 0.80] [--row-gap 0.55]
"""

import argparse
import csv
import math
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (GRID_DIR, LOG_DIR, OCR_DIR, UMI_DATA, ensure_dirs, load_json,  # noqa: E402
                    load_tables, log, save_json)

# OCR confusions that are formatting noise rather than a real disagreement
NOISE = [
    ("–", "-"), ("—", "-"), ("−", "-"), ("‐", "-"), ("‑", "-"),
    ("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
    (" ", " "), ("ﬁ", "fi"), ("ﬂ", "fl"),
]


def norm(s):
    """Loose normalisation used only for the A/B equality test."""
    s = s.strip()
    for a, b in NOISE:
        s = s.replace(a, b)
    return re.sub(r"\s+", "", s).lower()


# --------------------------------------------------------------------------- repair
# Umi-OCR's English model is driven by dict_en.txt: 94 entries, every one of them
# ASCII. mu, plusminus, gamma and superscript-2 are simply not in the vocabulary, so
# the English pass can only ever emit a wrong ASCII lookalike (mu -> g, +- -> +, *).
# The Chinese model uses a 6623-entry dictionary that does contain them - it reads
# both correctly - but it is worse on Latin text (loses footnote superscripts,
# VSLLME-...-CCl4, gamma-nonalactone -> Y-nonalactone).
#
# So the two failure modes are disjoint and the C pass is only trusted where English is
# structurally incapable of being right. A repair is accepted only if the C reading has
# the same alphanumeric skeleton (same digits, same letters, in order) as the A/B
# consensus AND every character it introduces comes from DONOR_CHARS. Anything else
# keeps the A/B reading, so the C pass can never rewrite a word or a number.
#
# The whitelist matters. "Has a character dict_en lacks" is necessary but not
# sufficient: on T04 pass C read the `<` of "<1" as U+039B GREEK CAPITAL LETTER LAMDA
# twice, which would have passed the skeleton test and written Lambda into a
# concentration column. The whitelist is deliberately lowercase Greek, the comparison
# operators and the degree/plusminus/superscript signs - the symbols that actually turn
# up in food-chemistry tables. Greek capitals are excluded: LAMDA/SIGMA are the classic
# misreads of < and >. Extend it with --donor-chars if a paper needs more.
DONOR_CHARS = set("±µμγβαδθ°²³≤≥×÷∞≠≈∓")


def set_donor_chars(spec):
    """--donor-chars: extra characters the symbol-donor pass may introduce."""
    DONOR_CHARS.update(spec)


_DICT_EN = None
_DICT_ERR = []


def dict_en():
    """Character vocabulary of the English recognition model, read from the install."""
    global _DICT_EN
    if _DICT_EN is None:
        path = os.path.join(UMI_DATA, "plugins", "win7_x64_RapidOCR-json",
                            "models", "dict_en.txt")
        try:
            with open(path, encoding="utf-8") as f:
                _DICT_EN = set(f.read().split("\n")) - {""}
        except OSError as e:
            _DICT_ERR.append("%s: %s" % (path, e))
            _DICT_EN = set()
    if _DICT_ERR:
        log("  WARNING symbol repair disabled - dict_en.txt unreadable: %s"
            % _DICT_ERR[0], LOG_DIR + "/s3_grid.log")
    return _DICT_EN


def skeleton(s):
    """Letters and digits only, lowercased - what both models must agree on."""
    return re.sub(r"[^0-9a-z]", "", s.lower())


def repair(ab_text, c_text):
    """
    Adopt the C reading only when it spells something English has no vocabulary for,
    the letters and digits still agree, and every introduced character is whitelisted.
    Returns (text, status).
    """
    if not c_text or ab_text == c_text:
        return ab_text, "same"
    if not dict_en():
        return ab_text, "no_dict"
    introduced = set(c_text) - set(ab_text)
    outside = any(ch not in _DICT_EN for ch in c_text if not ch.isspace())
    if outside and introduced and introduced <= DONOR_CHARS \
            and skeleton(ab_text) == skeleton(c_text):
        return c_text, "repaired_C"
    return ab_text, "kept_AB"


# --------------------------------------------------------------------------- geometry
def to_points(ocr, table):
    """OCR pixel boxes -> PDF points inside the crop rect."""
    x0, y0, x1, y1 = table["crop"]
    s = 72.0 / float(ocr["dpi"])
    out = []
    for b in ocr["boxes"]:
        xs = [p[0] for p in b["box"]]
        ys = [p[1] for p in b["box"]]
        out.append(dict(text=b["text"], score=float(b["score"]),
                        x0=x0 + min(xs) * s, y0=y0 + min(ys) * s,
                        x1=x0 + max(xs) * s, y1=y0 + max(ys) * s))
    out.sort(key=lambda b: (b["y0"], b["x0"]))
    return out


def tag_zones(boxes, table, med_h):
    """caption (above top rule) / header / body / note (below bottom rule)."""
    ty = table["rules"]["top"][0]
    my = table["rules"]["mid"][0]
    by = table["rules"]["bottom"][0]
    for b in boxes:
        cy = (b["y0"] + b["y1"]) / 2.0
        if cy < ty:
            b["zone"] = "caption"
        elif cy < my:
            b["zone"] = "header"
        elif cy < by:
            b["zone"] = "body"
        else:
            b["zone"] = "note"
    return boxes


def rule_like(b, med_h, med_w):
    """Throw away anything that is a table rule mis-read as a character."""
    t = b["text"].strip()
    if not t:
        return True
    if re.fullmatch(r"[-_=~.·—–\s|]+", t) and len(t) >= 2:
        return True
    if b["y1"] - b["y0"] < 0.35 * med_h and (b["x1"] - b["x0"]) > 4 * med_w:
        return True
    return False


def split_runs(items, min_gap):
    """One text line -> runs separated by blank horizontal gaps."""
    items = sorted(items, key=lambda b: b["x0"])
    runs = []
    for b in items:
        if runs and b["x0"] - runs[-1]["x1"] <= min_gap:
            runs[-1]["boxes"].append(b)
            runs[-1]["x1"] = max(runs[-1]["x1"], b["x1"])
            runs[-1]["y0"] = min(runs[-1]["y0"], b["y0"])
            runs[-1]["y1"] = max(runs[-1]["y1"], b["y1"])
        else:
            runs.append(dict(x0=b["x0"], x1=b["x1"], y0=b["y0"], y1=b["y1"], boxes=[b]))
    for r in runs:
        r["boxes"].sort(key=lambda b: b["x0"])
        r["text"] = join_boxes(r["boxes"])
        r["score"] = min(b["score"] for b in r["boxes"])
        r["cy"] = (r["y0"] + r["y1"]) / 2.0
    return runs


def join_boxes(boxes):
    """Join boxes of one cell; superscript footnotes stay attached to their number."""
    out = ""
    prev = None
    for b in boxes:
        t = b["text"].strip()
        if not t:
            continue
        if prev is not None:
            gap = b["x0"] - prev["x1"]
            sup = (b["y1"] - b["y0"]) < 0.75 * (prev["y1"] - prev["y0"])
            if gap > 0.22 * (prev["y1"] - prev["y0"]) and not sup:
                out += " "
            elif gap > 0 and not sup:
                out += " "
        out += t
        prev = b
    return out.strip()


def infer_columns(body_runs_by_row, x_lo, x_hi, min_gap, min_fill, n_rows,
                  max_cover=0.35):
    """
    Column bands = the x ranges that essentially no run reaches.

    Splitting each line into runs first is what makes this work: one unusually long
    cell that spills into its neighbour's column cannot hide that separator, because
    the rows underneath still fill that x range with their own runs.

    A gutter does not have to be blank in EVERY row - group-label rows such as
    "Lactones" and a cell that happens to hold "0.9986 1.8" in one box both bridge
    real gutters. So up to `max_cover` (default 35%) of the rows may cover it. Bands
    filled in almost no row are merged back afterwards - they are over-splitting.
    """
    step = 0.5
    n = max(int((x_hi - x_lo) / step), 1)
    hits = [0] * n
    for row in body_runs_by_row:
        line = bytearray(n)
        for r in row:
            a = max(0, int((r["x0"] - x_lo) / step))
            b = min(n - 1, int((r["x1"] - x_lo) / step))
            for k in range(a, b + 1):
                line[k] = 1
        for k in range(n):
            if line[k]:
                hits[k] += 1
    allowed = int(math.floor(max_cover * max(n_rows, 1)))

    min_blank = int(round(min_gap / step))

    # collect the blank intervals, then take what lies BETWEEN them as the columns.
    # Deriving the bands from the gutter list (rather than interleaving cuts) matters:
    # the blank strip left of the first column and right of the last one is a gutter
    # too, and pairing cuts by index used to shift every band by one.
    gutters = []
    k = 0
    while k < n:
        if hits[k] > allowed:
            k += 1
            continue
        j = k
        while j < n and hits[j] <= allowed:
            j += 1
        if j - k >= min_blank:
            gutters.append((x_lo + k * step, x_lo + j * step))
        k = j

    if not gutters:
        bands = [(x_lo, x_hi)]
    else:
        bands = []
        if gutters[0][0] - x_lo > min_gap:
            bands.append((x_lo, gutters[0][0]))
        for i in range(len(gutters) - 1):
            bands.append((gutters[i][1], gutters[i + 1][0]))
        if x_hi - gutters[-1][1] > min_gap:
            bands.append((gutters[-1][1], x_hi))
    bands = [b for b in bands if b[1] - b[0] > 0.8 * min_gap]

    # fill rate per band, drop bands filled in too few rows, then re-join the gap
    def fill(band):
        c = 0
        for row in body_runs_by_row:
            if any(r["x0"] < band[1] - 0.5 and r["x1"] > band[0] + 0.5 for r in row):
                c += 1
        return c / max(n_rows, 1)

    changed = True
    while changed and len(bands) > 1:
        changed = False
        rates = [fill(b) for b in bands]
        i = next((k for k, v in enumerate(rates) if v < min_fill), None)
        if i is None:
            break
        # merge band i into whichever neighbour leaves the narrower leftover gap
        left_gap = bands[i][0] - bands[i - 1][0] if i > 0 else 1e9
        right_gap = bands[i + 1][1] - bands[i][1] if i + 1 < len(bands) else 1e9
        j = i - 1 if left_gap <= right_gap else i + 1
        lo = min(bands[i][0], bands[j][0])
        hi = max(bands[i][1], bands[j][1])
        bands[min(i, j): max(i, j) + 1] = [(lo, hi)]
        changed = True
    return bands


def line_gaps(lines):
    out = []
    for ln in lines:
        it = sorted(ln, key=lambda z: z["x0"])
        for i in range(1, len(it)):
            g = it[i]["x0"] - it[i - 1]["x1"]
            if g > 0.5:
                out.append(g)
    return out


def lines_of(bs, row_gap, min_gap):
    """Boxes -> text lines (y clustering) -> runs (x gap splitting)."""
    lines = []
    for b in sorted(bs, key=lambda z: (z["y0"] + z["y1"]) / 2.0):
        cy = (b["y0"] + b["y1"]) / 2.0
        if lines and cy - (sum(x[0] for x in lines[-1]) / len(lines[-1])) <= row_gap:
            lines[-1].append((cy, b))
        else:
            lines.append([(cy, b)])
    return [split_runs([b for _cy, b in ln], min_gap) for ln in lines]


def row_cy(row):
    return sum(r["cy"] for r in row) / len(row)


def cell_of(run, bands):
    """Which column band(s) a run covers; >1 means a merged cell."""
    hits = [k for k, (a, b) in enumerate(bands) if run["x0"] < b - 0.5 and run["x1"] > a + 0.5]
    if not hits:
        c = (run["x0"] + run["x1"]) / 2.0
        hits = [min(range(len(bands)), key=lambda k: abs((bands[k][0] + bands[k][1]) / 2 - c))]
    return hits[0], hits[-1]


def assemble(zone_runs_by_row, bands):
    """Runs in rows + column bands -> list of rows of {text, score, span}."""
    grid = []
    for row in zone_runs_by_row:
        cells = [dict(text="", score=None, span=0) for _ in bands]
        for r in row:
            c0, c1 = cell_of(r, bands)
            cells[c0]["text"] = (cells[c0]["text"] + " " + r["text"]).strip() if cells[c0]["text"] else r["text"]
            sc = r["score"]
            cells[c0]["score"] = sc if cells[c0]["score"] is None else min(cells[c0]["score"], sc)
            if c1 > c0:
                cells[c0]["span"] = c1 - c0 + 1
                for k in range(c0 + 1, c1 + 1):
                    cells[k]["span"] = -1          # covered by the merged cell
        grid.append(cells)
    return grid


def grid_rows(grid):
    """Flatten a grid to [[text,...]] skipping covered cells."""
    return [[c["text"] for c in row if c["span"] >= 0] for row in grid]


def zone_text(runs_by_row):
    return [join_boxes([b for r in row for b in r["boxes"]]) for row in runs_by_row]


def build(ocr, table, cfg, cols=None):
    boxes = to_points(ocr, table)
    if not boxes:
        return None
    heights = [b["y1"] - b["y0"] for b in boxes]
    widths = [b["x1"] - b["x0"] for b in boxes]
    med_h = statistics.median(heights)
    med_w = statistics.median(widths)
    boxes = [b for b in boxes if not rule_like(b, med_h, med_w)]
    tag_zones(boxes, table, med_h)
    row_gap = cfg["row_gap"] * med_h

    def zone(z):
        return [b for b in boxes if b["zone"] == z]

    body_lines = lines_of(zone("body"), row_gap, cfg["min_gap"])
    head_lines = lines_of(zone("header"), row_gap, cfg["min_gap"])
    if cols is not None:
        header = assemble(head_lines, cols)
        body = assemble(body_lines, cols)
        return dict(id=table["id"], name=table["name"], page=table["page"],
                    pass_=ocr["pass"], dpi=ocr["dpi"], min_gap=cfg["min_gap"],
                    bands=[[round(a, 2), round(b, 2)] for a, b in cols],
                    cols=[round(a, 2) for a, b in cols], n_col=len(cols),
                    n_head_row=len(header), n_body_row=len(body),
                    caption=zone_text(lines_of(zone("caption"), row_gap, cfg["min_gap"])),
                    note=zone_text(lines_of(zone("note"), row_gap, cfg["min_gap"])),
                    header=header, body=body, med_h=round(med_h, 2))
    min_gap = cfg["min_gap"]
    cols = infer_columns(body_lines, table["box"][0] - 8, table["box"][2] + 8,
                         min_gap, cfg["min_col_fill"], max(len(body_lines), 1),
                         cfg["max_cover"])
    header = assemble(head_lines, cols)
    body = assemble(body_lines, cols)
    return dict(
        id=table["id"], name=table["name"], page=table["page"], pass_=ocr["pass"],
        dpi=ocr["dpi"],
        min_gap=round(min_gap, 2),
        bands=[[round(a, 2), round(b, 2)] for a, b in cols],
        cols=[round(a, 2) for a, b in cols],
        n_col=len(cols),
        n_head_row=len(header), n_body_row=len(body),
        caption=zone_text(lines_of(zone("caption"), row_gap, min_gap)),
        note=zone_text(lines_of(zone("note"), row_gap, min_gap)),
        header=header, body=body,
        med_h=round(med_h, 2),
    )


# --------------------------------------------------------------------------- verify
def flat_cells(g):
    """(section, row, col) -> cell dict.  Column index is the grid position, so cells
    covered by a merged neighbour keep their slot and simply hold no text."""
    out = {}
    for sec, grid in (("head", g["header"]), ("body", g["body"])):
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                out[(sec, r, c)] = cell
    return out


def consensus(ca, cb):
    """Pick the value to write, and say why."""
    ta, tb = ca["text"], cb["text"]
    if ta == tb:
        return ta, "match"
    if norm(ta) == norm(tb):
        return ta, "match_norm"
    sa = ca["score"] if ca["score"] is not None else 0.0
    sb = cb["score"] if cb["score"] is not None else 0.0
    if abs(sa - sb) < 0.02:
        return ta, "conflict_tie"      # equal confidence -> keep pass A, flag for review
    return (ta, "conflict_a") if sa > sb else (tb, "conflict_b")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", type=float, default=0.80)
    ap.add_argument("--min-gap", type=float, default=4.5,
                    help="cell gap in pt: splits a line into cells and marks gutters")
    ap.add_argument("--row-gap", type=float, default=0.55, help="row split = k x median line height")
    ap.add_argument("--min-col-fill", type=float, default=0.30)
    ap.add_argument("--max-cover", type=float, default=0.35,
                    help="share of body rows allowed to bridge a column gutter")
    ap.add_argument("--donor-chars", default="",
                    help="extra characters the symbol-donor pass may introduce "
                         "(added to the built-in whitelist)")
    a = ap.parse_args()
    if a.donor_chars:
        set_donor_chars(a.donor_chars)
    cfg = dict(min_gap=a.min_gap, row_gap=a.row_gap,
               min_col_fill=a.min_col_fill, max_cover=a.max_cover)

    ensure_dirs()
    logfile = os.path.join(LOG_DIR, "s3_grid.log")
    if os.path.exists(logfile):
        os.remove(logfile)
    log("STEP 3 - rebuild grid + verify A/B", logfile)

    db = load_tables()
    summary = []
    for t in db["tables"]:
        name = t["name"]
        pa = os.path.join(OCR_DIR, "%s_A.json" % name)
        pb = os.path.join(OCR_DIR, "%s_B.json" % name)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            log("  %s missing ocr json - skipped" % t["id"], logfile)
            continue
        ga = build(load_json(pa), t, cfg)
        # pass B is first built on its own geometry (structural cross-check), then
        # re-gridded onto pass A's columns so the two extractions are comparable
        gb = build(load_json(pb), t, cfg)
        bands_a = [(b[0], b[1]) for b in ga["bands"]]
        gb_on_a = build(load_json(pb), t, cfg, cols=bands_a)
        # pass C is the symbol donor: only ever consulted for characters dict_en lacks
        pc_path = os.path.join(OCR_DIR, "%s_C.json" % name)
        gc_on_a = build(load_json(pc_path), t, cfg, cols=bands_a) \
            if os.path.exists(pc_path) else None

        ca, cb = flat_cells(ga), flat_cells(gb_on_a)
        cc_all = flat_cells(gc_on_a) if gc_on_a else {}
        keys = sorted(set(ca) | set(cb))
        rows_out, low_out = [], []
        n_conf = n_match = n_only = n_rep = 0
        grid = {"head": [], "body": []}
        for sec in ("head", "body"):
            src = ga["header"] if sec == "head" else ga["body"]
            gsec = []
            for r in range(len(src)):
                grow = []
                for c in range(len(ga["cols"])):
                    k = (sec, r, c)
                    x, y = ca.get(k), cb.get(k)
                    if x is None and y is None:
                        grow.append(dict(text="", score=None, span=0))
                        continue
                    if x is None or y is None:
                        n_only += 1
                        present = y if x is None else x
                        txt, how = present["text"], ("only_b" if x is None else "only_a")
                        sc = present["score"] or 0.0
                        rows_out.append([t["id"], name, t["page"], sec, r + 1, c + 1, how,
                                         x["text"] if x else "", y["text"] if y else "",
                                         round(sc, 4)])
                    else:
                        txt, how = consensus(x, y)
                        sc = min(x["score"] or 0, y["score"] or 0)
                        if how.startswith("conflict"):
                            n_conf += 1
                            rows_out.append([t["id"], name, t["page"], sec, r + 1, c + 1, how,
                                             x["text"], y["text"], round(sc, 4)])
                        else:
                            n_match += 1
                    # symbol repair: adopt pass C only where the English dictionary has
                    # no character to write and the digits/letters still agree
                    ctext = cc_all.get(k, {}).get("text", "")
                    if ctext:
                        new_txt, rep = repair(txt, ctext)
                        if rep == "repaired_C":
                            n_rep += 1
                            rows_out.append([t["id"], name, t["page"], sec, r + 1, c + 1,
                                             "repaired_C", txt, ctext,
                                             round(sc, 4) if sc is not None else ""])
                            txt = new_txt
                    if txt and sc is not None and sc < a.conf:
                        low_out.append([t["id"], name, t["page"], sec, r + 1, c + 1,
                                        txt, round(sc, 4), how])
                    grow.append(dict(text=txt, score=sc,
                                     span=present["span"] if (x is None or y is None)
                                     else x["span"]))
                gsec.append(grow)
            grid[sec] = gsec

        out = dict(id=t["id"], name=name, page=t["page"], long_table=t["long_table"],
                   src_pdf_rect=t["crop"], img_a=t["img_a"], img_b=t["img_b"],
                   caption=ga["caption"], caption_text=" ".join(ga["caption"]).strip(),
                   note=ga["note"], note_text=" ".join(ga["note"]).strip(),
                   cols=ga["cols"], bands=ga["bands"], n_col=ga["n_col"],
                   n_head_row=len(grid["head"]), n_body_row=len(grid["body"]),
                   header=grid["head"], body=grid["body"],
                   pass_b=dict(n_col=gb["n_col"], n_head_row=gb["n_head_row"],
                               n_body_row=gb["n_body_row"]),
                   verify=dict(n_cells=len(keys), n_match=n_match, n_conflict=n_conf,
                               n_one_sided=n_only, n_lowconf=len(low_out),
                               n_repaired=n_rep,
                               agree_pct=round(100.0 * n_match / max(len(keys), 1), 2)))
        save_json(out, os.path.join(GRID_DIR, "%s_grid.json" % name))

        with open(os.path.join(GRID_DIR, "%s_diff.csv" % name), "w", newline="",
                  encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["table_id", "name", "pdf_page", "section", "row", "col",
                        "status", "pass_A_text", "pass_B_text", "min_score"])
            w.writerows(rows_out)
        with open(os.path.join(GRID_DIR, "%s_lowconf.csv" % name), "w", newline="",
                  encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["table_id", "name", "pdf_page", "section", "row", "col",
                        "text", "score", "status"])
            w.writerows(low_out)

        summary.append((t, out, len(rows_out), len(low_out)))
        log("  %s p%02d  cols=%d (B:%d)  head=%d body=%d  match=%d conflict=%d one-sided=%d repaired=%d lowconf=%d  agree=%.1f%%"
            % (t["id"], t["page"], out["n_col"], out["pass_b"]["n_col"], out["n_head_row"],
               out["n_body_row"], n_match, n_conf, n_only, n_rep, len(low_out),
               out["verify"]["agree_pct"]), logfile)

    log("tables rebuilt: %d" % len(summary), logfile)


if __name__ == "__main__":
    main()
