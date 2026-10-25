# -*- coding: utf-8 -*-
"""Crop a named body row out of a table image so it can be eyeballed against the source."""
import json
import os
import re
import statistics
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "..\\src")
from PIL import Image

from common import IMG_DIR, OCR_DIR, load_json, load_tables
import s3_verify_grid as S

name = sys.argv[1]
needle = sys.argv[2].lower()
pad_up = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0
scale = int(sys.argv[4]) if len(sys.argv) > 4 else 3

db = load_tables()
t = [x for x in db["tables"] if x["name"] == name][0]
ocr = load_json(os.path.join(OCR_DIR, name + "_A.json"))

boxes = S.to_points(ocr, t)
med = statistics.median([b["y1"] - b["y0"] for b in boxes])
boxes = [b for b in boxes if not S.rule_like(b, med, med)]
S.tag_zones(boxes, t, med)
lines = S.lines_of([b for b in boxes if b["zone"] == "body"], 0.55 * med, 4.5)

crop = t["crop"]
dpi = db["meta"]["dpi_main"]
sc = dpi / 72.0
img = Image.open(os.path.join(IMG_DIR, os.path.basename(t["img_a"])))

hit = None
for ln in lines:
    txt = " ".join(r["text"] for r in ln).lower()
    if needle in txt:
        hit = ln
        break
if not hit:
    print("row not found:", needle)
    raise SystemExit(1)

y0 = min(r["y0"] for r in hit) - pad_up
y1 = max(r["y1"] for r in hit) + pad_up
px0 = int((crop[0] - crop[0]) * sc)
px1 = int((crop[2] - crop[0]) * sc)
py0 = max(0, int((y0 - crop[1]) * sc))
py1 = min(img.height, int((y1 - crop[1]) * sc))

out = img.crop((px0, py0, px1, py1))
out = out.resize((out.width * scale, out.height * scale), Image.LANCZOS)
name_out = os.path.join("..", "out", "rowcheck_%s_%s.png" % (name, re.sub(r"\W+", "_", needle)[:18]))
out.save(name_out)
print("saved:", os.path.abspath(name_out))
print("text:", [r["text"] for r in hit])
