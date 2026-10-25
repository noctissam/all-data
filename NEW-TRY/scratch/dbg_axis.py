# -*- coding: utf-8 -*-
"""Print the per-column data axis the recovery computes, to check it by eye."""
import json
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scratch")
sys.stdout.reconfigure(encoding="utf-8")

import importlib.util                       # noqa: E402
import pymupdf                              # noqa: E402
from recover_headers import group_lines, match_table, pdf_for   # noqa: E402

spec = importlib.util.spec_from_file_location("b", "src/build_rec整理.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)

IDX, TI = int(sys.argv[1]), int(sys.argv[2])
band = json.load(open("out/re整理/band_%02d.json" % IDX, encoding="utf-8"))["tables"][TI]
info = B.classify_columns(band)
targets = [c for c, _ in info["data_cols"]
           if B.sample_label(band, c, 0, info.get("hdr_rows")).startswith("列")]
hdr, body = B.promote_header_rows(band)
print("targets =", targets)
print("body[0] =", json.dumps(body[0], ensure_ascii=False)[:110])
print("body[1] =", json.dumps(body[1], ensure_ascii=False)[:110] if len(body) > 1 else "-")

doc = pymupdf.open(pdf_for(IDX))
pg = doc[(band.get("pages") or [1])[0] - 1]
t = match_table(__import__("extract_band").page_tables(pg), band)
lines = group_lines(pg.get_text("words"))

for c in targets:
    xs = []
    for r in body:
        if c >= len(r):
            continue
        want = str(r[c] or "").strip()
        if not want:
            continue
        head = next((str(x or "").strip() for x in r if str(x or "").strip()), "")
        for y, ws in lines:
            if not any(w[4].strip() == head for w in ws):
                continue
            hit = [(w[0] + w[2]) / 2.0 for w in ws if w[4].strip() == want]
            xs.extend(hit)
            break
    xs.sort()
    print("col%-3d n=%-4d axis=%s" % (c, len(xs),
                                       round(xs[len(xs) // 2], 1) if xs else None))
    print("      first 6 x:", [round(x, 1) for x in xs[:6]])
doc.close()