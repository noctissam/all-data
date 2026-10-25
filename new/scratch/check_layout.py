# -*- coding: utf-8 -*-
"""
check_layout.py — 版面自检（不依赖渲染器）

对每一页：
  1. 形状安全区检查：任何形状越出 [0.35, SW-0.35] x [0.25, SH-0.35] 即报警。
  2. 文本溢出估算：按字符宽度模型估算换行行数 -> 所需高度，与文本框高度比较。
  3. 表格估算：按列宽与单元格文本估算每行所需高度，与设定行高比较。
输出：屏幕报告 + new/output/layout_check.json
"""
from __future__ import annotations

import json
import math
import os
import sys

from pptx import Presentation
from pptx.util import Emu, Pt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DECK = os.path.join(HERE, "数据清洗与关系挖掘_汇报.pptx")
OUT = os.path.join(HERE, "output", "layout_check.json")

SW, SH = 13.333, 7.5
SAFE_L, SAFE_R = 0.35, SW - 0.35
SAFE_T, SAFE_B = 0.22, SH - 0.22


def em_width(ch: str) -> float:
    """Rough advance width in em units."""
    o = ord(ch)
    if o < 0x2E80:                       # ASCII / Latin / punctuation
        if ch in "　":
            return 1.0
        if ch in " .,:;'|!i l":
            return 0.32
        if ch in "fjrt()[]-":
            return 0.38
        if ch.isupper():
            return 0.68
        return 0.56
    if 0x2E80 <= o <= 0x9FFF:            # CJK
        return 1.0
    if 0xFF01 <= o <= 0xFF60:            # fullwidth forms
        return 1.0
    if 0x2000 <= o <= 0x206F:            # general punctuation (dashes etc.)
        return 1.0
    if 0x2070 <= o <= 0x209F or 0x1D43 <= o <= 0x1DBF:   # super/subscript
        return 0.5
    return 0.6


def text_width_pt(text: str, size_pt: float) -> float:
    return sum(em_width(c) for c in text) * size_pt


def para_metrics(p, default_size=18.0):
    size = default_size
    text = ""
    for r in p.runs:
        if r.font.size is not None:
            size = max(size if text else 0, r.font.size.pt)
        text += r.text
    if not text:
        return 0.0, 0.0, 0.0
    size = default_size
    for r in p.runs:
        if r.font.size is not None:
            size = r.font.size.pt
            break
    ls = p.line_spacing if isinstance(p.line_spacing, float) else 1.0
    sb = p.space_before.pt if p.space_before is not None else 0.0
    sa = p.space_after.pt if p.space_after is not None else 0.0
    return text_width_pt(text, size), size * 1.2 * ls, sb + sa


def frame_needed_height(tf, box_width_in: float):
    """Estimate the height (inches) a text frame needs once wrapped."""
    avail_pt = box_width_in * 72.0
    total = 0.0
    for p in tf.paragraphs:
        w, lh, sp = para_metrics(p)
        if w == 0:
            total += sp
            continue
        nlines = max(1, math.ceil(w / max(avail_pt, 1.0)))
        total += nlines * lh + sp
    return total / 72.0


def inch(v):
    return Emu(v).inches


def check(prs):
    problems = []
    for si, slide in enumerate(prs.slides, start=1):
        for sh in slide.shapes:
            l, t = inch(sh.left), inch(sh.top)
            w, h = inch(sh.width), inch(sh.height)
            r, b = l + w, t + h
            label = (sh.text_frame.text.replace("\n", " / ")[:46]
                     if sh.has_text_frame and sh.text_frame.text.strip()
                     else f"<{sh.shape_type}>")
            # 1. safe area (full-bleed banners are intentional)
            full_bleed = w >= SW - 0.02 and l <= 0.02
            if not full_bleed and (l < SAFE_L - 1e-6 or t < SAFE_T - 1e-6
                                   or r > SAFE_R + 1e-6 or b > SAFE_B + 1e-6):
                problems.append(dict(slide=si, kind="out_of_safe_area", shape=label,
                                     detail=f"L={l:.2f} T={t:.2f} R={r:.2f} B={b:.2f} "
                                            f"(safe {SAFE_L}–{SAFE_R:.2f} / {SAFE_T}–{SAFE_B:.2f})"))
            if not sh.has_text_frame or not sh.text_frame.text.strip():
                continue
            tf = sh.text_frame
            ml = inch(tf.margin_left) if tf.margin_left is not None else 0.1
            mr = inch(tf.margin_right) if tf.margin_right is not None else 0.1
            mt = inch(tf.margin_top) if tf.margin_top is not None else 0.05
            mb = inch(tf.margin_bottom) if tf.margin_bottom is not None else 0.05
            inner_w = w - ml - mr
            inner_h = h - mt - mb
            need = frame_needed_height(tf, inner_w)
            # 2. text overflow (with 6% tolerance for CJK/Latin kerning)
            if need > inner_h * 1.06 + 0.02:
                problems.append(dict(slide=si, kind="text_overflow", shape=label,
                                     detail=f"needs {need:.2f}in, box {inner_h:.2f}in "
                                            f"(+{need - inner_h:.2f})"))
            # 3. horizontal: CJK breaks between characters, so only a Latin/CJK-free
            #    run wider than the box is a genuine problem
            import re as _re
            avail_pt = inner_w * 72.0
            for p in tf.paragraphs:
                txt = "".join(r.text for r in p.runs)
                if not txt:
                    continue
                sz = 18.0
                for rr in p.runs:
                    if rr.font.size is not None:
                        sz = rr.font.size.pt
                        break
                for tok in _re.findall(r"[0-9A-Za-z\u00C0-\u024F%.,+\-–—/=×><°μ]+", txt):
                    tw = text_width_pt(tok, sz)
                    if tw > avail_pt * 1.02:
                        problems.append(dict(slide=si, kind="h_overflow", shape=tok[:40],
                                             detail=f"token {tw / 72:.2f}in > box {inner_w:.2f}in"))
        # tables
        for sh in slide.shapes:
            if not sh.has_table:
                continue
            tbl = sh.table
            colw = [inch(c.width) for c in tbl.columns]
            for ri, row in enumerate(tbl.rows):
                rh = inch(row.height)
                need = 0.0
                for ci, cell in enumerate(row.cells):
                    txt = cell.text
                    sz = 11.0
                    for p in cell.text_frame.paragraphs:
                        for rr in p.runs:
                            if rr.font.size is not None:
                                sz = rr.font.size.pt
                                break
                        break
                    ml = inch(cell.margin_left) if cell.margin_left is not None else 0.1
                    mr = inch(cell.margin_right) if cell.margin_right is not None else 0.1
                    aw = max((colw[ci] - ml - mr) * 72.0, 1.0)
                    nl = max(1, math.ceil(text_width_pt(txt, sz) / aw))
                    need = max(need, nl * sz * 1.25 / 72.0 + 0.05)
                if need > rh * 1.10 + 0.02:
                    problems.append(dict(
                        slide=si, kind="table_row_short",
                        shape=f"{sh.name} r{ri}: " + " | ".join(c.text[:14] for c in row.cells)[:60],
                        detail=f"needs {need:.2f}in vs row {rh:.2f}in"))
    return problems


def main():
    prs = Presentation(DECK)
    problems = check(prs)
    by = {}
    for p in problems:
        by.setdefault(p["slide"], []).append(p)
    print(f"slides: {len(prs.slides._sldIdLst)}   problems: {len(problems)}")
    for si in sorted(by):
        print(f"\n--- slide {si} ({len(by[si])}) ---")
        for p in by[si]:
            print(f"  [{p['kind']:<18}] {p['shape'][:44]:<46} {p['detail']}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(problems, fh, ensure_ascii=False, indent=1)
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
