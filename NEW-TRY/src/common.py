# -*- coding: utf-8 -*-
"""
NEW-TRY shared helpers.

Pipeline overview (three-line table "三线表" extraction):
    s1_detect_tables.py   PDF -> locate three-line tables -> render 2 copies of each table image
    s2_umi_ocr.py         run Umi-OCR twice per table image (pass A = main, pass B = verification)
    s3_verify_grid.py     rebuild grid from OCR boxes, diff pass A vs pass B cell by cell
    s4_to_excel.py        write plain grid tables + verification sheets to one xlsx workbook

All console output is ASCII-only on purpose: the Windows console code page here is
cp936 and non-ASCII prints get mangled.  Detailed logs go to log files as UTF-8.
"""

import json
import os
import sys

# --------------------------------------------------------------------------- paths
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# NEWTRY_OUT lets a batch run give each paper its own output tree. The five steps all
# import their paths from here, so redirecting this one variable is enough to keep
# paper N's tables.json / images / grid from being overwritten by paper N+1 - no
# per-script changes and no risk of one paper's crops being read as another's.
OUT = os.environ.get("NEWTRY_OUT") or os.path.join(ROOT, "out")
OUT = os.path.abspath(OUT)

IMG_DIR = os.path.join(OUT, "img")            # table crops, *_A.png / *_B.png
PREVIEW_DIR = os.path.join(OUT, "page_preview")  # full pages with candidate boxes drawn
OCR_DIR = os.path.join(OUT, "ocr")            # raw Umi-OCR json, one per image
GRID_DIR = os.path.join(OUT, "grid")          # reconstructed grid json + cell diff csv
LOG_DIR = os.path.join(OUT, "log")
TABLES_JSON = os.path.join(OUT, "tables.json")

UMI_EXE = r"C:\UMI-OCR\Umi-OCR_Rapid_v2.1.3\Umi-OCR.exe"
UMI_DATA = r"C:\UMI-OCR\Umi-OCR_Rapid_v2.1.3\UmiOCR-data"
UMI_API_PORT = 1224

# --------------------------------------------------------------------------- tuning
# Detection thresholds (PDF points, 1 pt = 1/72 inch).  Tuned for A4 Elsevier-style
# two-column-free article PDFs; widen min_rule_w for narrow tables, raise long_h_pt
# to be stricter about what counts as a "long" table.
CFG = dict(
    min_rule_w=60.0,      # a rule must be at least this wide (pt)
    max_rule_h=4.0,       # ...and this thin, otherwise it is a graphic, not a rule
    flat_tol=0.8,         # endpoints y difference tolerated for a stroked line
    rule_dy_tol=1.2,      # rules within this y distance merge into one
    rule_ox=0.50,         # x overlap ratio needed to merge two rules
    min_x_overlap=0.60,   # top/bottom rules must share this much x range
    min_table_h=18.0,     # ignore degenerate triples
    max_table_h=760.0,    # taller than a page -> not a single table
    max_mid_frac=0.45,    # header rule must sit in the top 45% of the table
    pad_x=5.0,            # crop padding around the rules (pt)
    pad_top=5.0,
    pad_bot=6.0,
    long_h_pt=150.0,      # height (pt) above which a table is flagged "long"
    long_rows=8,          # ...or this many text rows
    # tabularity gate - what separates a real table from a decorative rule block
    min_body_rows=3,      # data rows between header rule and bottom rule
    min_med_runs=3.0,     # median number of horizontally separated runs per data row
    min_frac_3plus=0.35,  # share of data rows having >= 3 separated runs
    dpi_main=300,         # pass A render resolution
    dpi_check=400,        # pass B render resolution (same content, different raster)
)

DIRS = [OUT, IMG_DIR, PREVIEW_DIR, OCR_DIR, GRID_DIR, LOG_DIR]


def ensure_dirs():
    for d in DIRS:
        os.makedirs(d, exist_ok=True)


def log(msg, logfile=None):
    """ASCII console print + optional UTF-8 log file."""
    safe = str(msg).encode("ascii", "replace").decode("ascii")
    print(safe)
    sys.stdout.flush()
    if logfile:
        os.makedirs(os.path.dirname(logfile), exist_ok=True)
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")


def load_tables():
    if not os.path.exists(TABLES_JSON):
        raise SystemExit("tables.json missing - run s1_detect_tables.py first")
    with open(TABLES_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tid(index):
    return "T%02d" % index
