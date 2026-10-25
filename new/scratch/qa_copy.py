# -*- coding: utf-8 -*-
"""
qa_copy.py — 生成用于「完整版面目视检查」的副本。

渲染器把每一页按固定 1.25 倍绘制，因此原稿只能看到左上角 80%。
本脚本把所有几何尺寸与字号都乘以 0.8，渲染时被那 1.25 倍还原，
于是预览图能覆盖整页，且文字与文本框的相对比例与原稿完全一致。

只写入 new/scratch/qa/，不影响交付文件。
"""
from __future__ import annotations

import os
import shutil

from pptx import Presentation
from pptx.util import Emu, Inches, Pt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "数据清洗与关系挖掘_汇报.pptx")
DST_DIR = os.path.join(HERE, "scratch", "qa")
DST = os.path.join(DST_DIR, "qa_deck.pptx")
K = 0.8

os.makedirs(DST_DIR, exist_ok=True)
shutil.copy(SRC, DST)

prs = Presentation(DST)


def sc(v):
    return None if v is None else Emu(int(v * K))


def scale_fonts(tf):
    for p in tf.paragraphs:
        if p.space_before is not None:
            p.space_before = Pt(p.space_before.pt * K)
        if p.space_after is not None:
            p.space_after = Pt(p.space_after.pt * K)
        for r in p.runs:
            if r.font.size is not None:
                r.font.size = Pt(r.font.size.pt * K)


for slide in prs.slides:
    for sh in slide.shapes:
        if sh.left is not None:
            sh.left, sh.top = sc(sh.left), sc(sh.top)
            sh.width, sh.height = sc(sh.width), sc(sh.height)
        if sh.has_text_frame:
            tf = sh.text_frame
            for attr in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
                v = getattr(tf, attr)
                if v is not None:
                    setattr(tf, attr, Emu(int(v * K)))
            scale_fonts(tf)
        if sh.has_table:
            tbl = sh.table
            for col in tbl.columns:
                col.width = Emu(int(col.width * K))
            for row in tbl.rows:
                row.height = Emu(int(row.height * K))
            for row in tbl.rows:
                for cell in row.cells:
                    for attr in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
                        v = getattr(cell, attr)
                        if v is not None:
                            setattr(cell, attr, Emu(int(v * K)))
                    scale_fonts(cell.text_frame)

prs.save(DST)
print("saved", DST)
