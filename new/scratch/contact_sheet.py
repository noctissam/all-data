# -*- coding: utf-8 -*-
"""Tile rendered slides into contact sheets for fast visual QA.
usage: python contact_sheet.py <preview-dir> <out-dir>"""
import os
import sys
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "preview-v2")
DST = os.path.join(HERE, sys.argv[2] if len(sys.argv) > 2 else "contact2")
os.makedirs(DST, exist_ok=True)

pages = sorted(f for f in os.listdir(SRC) if f.startswith("page-") and f.endswith(".png"))
COLS, PAD, LABEL = 2, 12, 26

for i in range(0, len(pages), 4):
    chunk = pages[i:i + 4]
    ims = [Image.open(os.path.join(SRC, p)).convert("RGB") for p in chunk]
    w, h = ims[0].size
    rows = (len(ims) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * w + (COLS + 1) * PAD,
                              rows * (h + LABEL) + (rows + 1) * PAD), (235, 238, 242))
    d = ImageDraw.Draw(sheet)
    for k, im in enumerate(ims):
        r, c = divmod(k, COLS)
        x = PAD + c * (w + PAD)
        y = PAD + r * (h + LABEL + PAD)
        sheet.paste(im, (x, y + LABEL))
        idx = int(chunk[k].split("-")[1].split(".")[0])
        d.rectangle([x, y, x + w, y + LABEL], fill=(40, 60, 100))
        d.text((x + 8, y + 6), f"slide {idx}", fill=(255, 255, 255))
    sheet.save(os.path.join(DST, f"sheet-{i // 4 + 1}.png"))
    print("sheet", i // 4 + 1, chunk)
