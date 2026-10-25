# -*- coding: utf-8 -*-
"""
50_make_deck.py — 生成《浓香型白酒风味数据库：数据清洗与关系挖掘》汇报 PPT

素材：new/数据清洗与关系挖掘报告.md、new/figures/*.png、new/output/*.csv
输出：new/数据清洗与关系挖掘_汇报.pptx

排版约定：
  * 所有文本框显式关闭自动调整（noAutofit）并开启自动换行，否则 LibreOffice
    会按单行宽度撑开形状，导致文字溢出画面。
  * 正文底线 6.86 in（页脚在 7.04 in），所有内容不得越界。
"""
from __future__ import annotations

import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
OUT = os.path.join(HERE, "数据清洗与关系挖掘_汇报.pptx")

# ---------------------------------------------------------------- design system
FONT = "Microsoft YaHei"
PRIMARY = RGBColor(0x1F, 0x38, 0x64)
ACCENT = RGBColor(0xC0, 0x00, 0x00)
BLUE = RGBColor(0x2E, 0x75, 0xB6)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
GREY = RGBColor(0x59, 0x59, 0x59)
GREY_L = RGBColor(0x8C, 0x8C, 0x8C)
LIGHT = RGBColor(0xEE, 0xF3, 0xFA)
LIGHT2 = RGBColor(0xF5, 0xF7, 0xFA)
CARD_LINE = RGBColor(0xD6, 0xDF, 0xEC)
RED_BG = RGBColor(0xFD, 0xF2, 0xF2)
GREEN_BG = RGBColor(0xEE, 0xF7, 0xEE)
TEXT = RGBColor(0x26, 0x26, 0x26)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SW, SH = 13.333, 7.5
L, R = 0.55, 0.55
CW = SW - L - R                     # 12.233
RIGHT = SW - R                      # 12.783
TOP = 1.42
BOTTOM = 6.86                       # 内容底线

prs = Presentation()
prs.slide_width = Inches(SW)
prs.slide_height = Inches(SH)
BLANK = prs.slide_layouts[6]


# ---------------------------------------------------------------- helpers
def style_run(run, size=16, bold=False, color=TEXT, italic=False, font=FONT):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = font
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", font)


def textbox(slide, left, top, width, height, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE       # 关键：禁止按单行撑开形状
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tb, tf


def para(tf, text, size=16, bold=False, color=TEXT, first=False, sb=0, sa=3,
         align=PP_ALIGN.LEFT, line=1.10):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(sb)
    p.space_after = Pt(sa)
    p.line_spacing = line
    r = p.add_run()
    r.text = text
    style_run(r, size=size, bold=bold, color=color)
    return p


def rich(tf, parts, size=16, first=False, sb=0, sa=3, align=PP_ALIGN.LEFT, line=1.10):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(sb)
    p.space_after = Pt(sa)
    p.line_spacing = line
    for t, b, c in parts:
        r = p.add_run()
        r.text = t
        style_run(r, size=size, bold=b, color=c)
    return p


def rect(slide, left, top, width, height, fill=None, line=None,
         shape=MSO_SHAPE.RECTANGLE, line_w=1.0):
    sh = slide.shapes.add_shape(shape, Inches(left), Inches(top), Inches(width), Inches(height))
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(line_w)
    sh.shadow.inherit = False
    return sh


def panel(slide, left, top, width, height, fill=LIGHT, line=None, pad=0.20,
          title=None, title_color=PRIMARY, title_size=13.5, line_w=1.0):
    """带底色的内容面板，返回内部文本框的 text frame。"""
    rect(slide, left, top, width, height, fill=fill, line=line, line_w=line_w)
    tb, tf = textbox(slide, left + pad, top + 0.13, width - 2 * pad, height - 0.26)
    if title:
        para(tf, title, size=title_size, bold=True, color=title_color, first=True,
             sb=0, sa=6)
    return tf


def bullets(tf, items, size=12, gap=6):
    """items: (head, body) 或 str。head 加粗上色，body 常规。

    只有当第 0 段确实为空时才复用它，否则会把项目符号接到标题后面。
    """
    first = len(tf.paragraphs) == 1 and not tf.paragraphs[0].runs
    for it in items:
        head, body = (None, it) if isinstance(it, str) else it
        parts = []
        if head:
            parts.append(("▍ ", True, BLUE))
            parts.append((head, True, PRIMARY))
            if body:
                parts.append(("　" + body, False, TEXT))
        else:
            parts.append(("• ", False, BLUE))
            parts.append((body, False, TEXT))
        rich(tf, parts, size=size, first=first, sb=0 if first else gap, sa=0)
        first = False


def slide_head(title, kicker=None):
    s = prs.slides.add_slide(BLANK)
    rect(s, L, 0.34, 0.085, 0.60, fill=PRIMARY)
    tb, tf = textbox(s, L + 0.22, 0.30, CW - 0.22, 0.66, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, title, size=24, bold=True, color=PRIMARY, first=True, sa=0)
    if kicker:
        tb2, tf2 = textbox(s, L + 0.22, 0.99, CW - 0.30, 0.30)
        para(tf2, kicker, size=12, color=GREY, first=True, sa=0)
    rect(s, L, 1.30, CW, 0.020, fill=CARD_LINE)
    return s


N = 1        # 封面不编号，正文从 2 开始


def footer(slide, note=""):
    global N
    N += 1
    tb, tf = textbox(slide, L, 6.98, CW - 1.0, 0.28)
    para(tf, note, size=9, color=GREY_L, first=True, sa=0)
    tb2, tf2 = textbox(slide, RIGHT - 0.9, 6.98, 0.9, 0.28)
    para(tf2, str(N), size=10.5, bold=True, color=PRIMARY, first=True, sa=0,
         align=PP_ALIGN.RIGHT)


def add_table(slide, rows, left, top, width, col_w=None,
              header_size=11.5, body_size=10.5, row_h=None):
    nrow, ncol = len(rows), len(rows[0])
    height = sum(row_h) if row_h else 0.34 * nrow
    gf = slide.shapes.add_table(nrow, ncol, Inches(left), Inches(top),
                                Inches(width), Inches(height))
    tbl = gf.table
    if col_w:
        tot = sum(col_w)
        for i, w in enumerate(col_w):
            tbl.columns[i].width = Emu(int(Inches(width) * w / tot))
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(row_h[i] if row_h else 0.34)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = Inches(0.07)
            cell.margin_right = Inches(0.06)
            cell.margin_top = Inches(0.02)
            cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.space_before = Pt(0)
            p.space_after = Pt(0)
            p.line_spacing = 1.0
            r = p.add_run()
            r.text = str(val)
            if i == 0:
                style_run(r, size=header_size, bold=True, color=WHITE)
                cell.fill.solid()
                cell.fill.fore_color.rgb = PRIMARY
            else:
                style_run(r, size=body_size, bold=(j == 0), color=TEXT)
                cell.fill.solid()
                cell.fill.fore_color.rgb = WHITE if i % 2 else LIGHT2
    return tbl


def figure_slide(title, kicker, img, note="", max_h=None, top=None, center=True):
    s = slide_head(title, kicker)
    path = os.path.join(FIG, img)
    with Image.open(path) as im:
        iw, ih = im.size
    t0 = top if top else TOP + 0.06
    avail_h = (max_h if max_h else BOTTOM) - t0
    scale = min(CW / iw, avail_h / ih)
    w, h = iw * scale, ih * scale
    t = t0 + (avail_h - h) / 2 if center else t0
    s.shapes.add_picture(path, Inches(L + (CW - w) / 2), Inches(t),
                         Inches(w), Inches(h))
    footer(s, note)
    return s


# =============================================================== 01 封面
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, SW, 3.05, fill=PRIMARY)
rect(s, 0, 3.05, SW, 0.07, fill=ACCENT)
tb, tf = textbox(s, 1.05, 0.72, SW - 2.1, 1.45)
para(tf, "浓香型白酒风味数据库", size=40, bold=True, color=WHITE, first=True, sa=6)
para(tf, "数据清洗与风味物质关系挖掘", size=25, color=RGBColor(0xBD, 0xD7, 0xEE), sa=0)
tb, tf = textbox(s, 1.05, 2.36, SW - 2.1, 0.45)
para(tf, "基于 data总库.xlsx：33 篇文献 · 63 个化合物 · 156 个数值列",
     size=13, color=RGBColor(0x9D, 0xC3, 0xE6), first=True, sa=0)
tb, tf = textbox(s, 1.05, 3.72, SW - 2.1, 1.5)
para(tf, "汇报人：夏童", size=19, bold=True, color=PRIMARY, first=True, sa=10)
para(tf, "导师：徐岩　教授　　指导小组：马玥　助理研究员", size=14, color=GREY, sa=0)
tb, tf = textbox(s, 1.05, 5.60, SW - 2.1, 1.1)
rich(tf, [("课题方向：", True, PRIMARY),
          ("使用机器学习对浓香型白酒的勾兑进行自动化升级", False, TEXT)],
     size=14, first=True, sa=6)
rich(tf, [("本次汇报：", True, PRIMARY),
          ("风味数据库的数据清洗、阈值与 OAV 补全、风味物质关系挖掘", False, TEXT)],
     size=14, sa=0)

# =============================================================== 02 目录
s = slide_head("汇报提纲")
items = [
    ("01", "数据库现状", "两部 Excel 的关系、主库结构与 33 篇文献覆盖"),
    ("02", "数据清洗", "三类系统性损坏的定位与修复、单位统一、阈值与 OAV 补全"),
    ("03", "质量判定", "156 个数值列哪些可用、哪些需要回原文核对"),
    ("04", "关系挖掘", "相关矩阵、变量组聚类、样品 PCA/DBSCAN、共现网络、贡献权重表"),
    ("05", "结论与计划", "数据库核心缺口与下一步工作"),
]
y = TOP + 0.10
for num, t, d in items:
    rect(s, L, y, 0.70, 0.70, fill=PRIMARY)
    tb, tf = textbox(s, L, y, 0.70, 0.70, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, num, size=17, bold=True, color=WHITE, first=True, sa=0, align=PP_ALIGN.CENTER)
    tb, tf = textbox(s, L + 0.93, y + 0.02, CW - 1.0, 0.68)
    para(tf, t, size=17, bold=True, color=PRIMARY, first=True, sa=2)
    para(tf, d, size=12, color=GREY, sa=0)
    y += 0.90
tf = panel(s, L, y + 0.06, CW, 0.56, fill=LIGHT, title=None)
rich(tf, [("全部分析结果均可在 ", False, TEXT), ("new/", True, ACCENT),
          (" 目录复现：脚本 4 个、图表 13 张、结果表 38 个、汇总 Excel 32 个工作表。"
           "源文件保持只读未改动。", False, TEXT)],
     size=11.5, first=True, sa=0)
footer(s)

# =============================================================== 03 数据库现状
s = slide_head("一、数据库现状：两部 Excel 的关系", "同一课题目录下存在两个数据文件，二者并不同步")
rows = [
    ["", "data总库.xlsx（本次清洗对象）", "data.xlsx（姊妹库）"],
    ["工作表数", "13 个（all data + 12 个文献表 + 1 个空表）", "35 个（all data + 34 个文献表）"],
    ["all data 规模", "63 行 × 163 列", "95 行 × 52 列"],
    ["数值列内容", "以浓度为主，数值已提取为纯数字", "浓度与 OAV 混排，保留 “±SD” 文本"],
    ["CAS 列", "33 行损坏（被删除所有 0）", "完整、可用"],
    ["本次用途", "清洗主体", "交叉校验与数值修复的参照"],
]
add_table(s, rows, L, TOP, CW, col_w=[1.5, 4.6, 4.0], row_h=[0.36] * 6)
tf = panel(s, L, 3.72, CW, 1.66, fill=RED_BG, line=ACCENT, title="⚠　三点必须注意的差异",
           title_color=ACCENT, pad=0.22)
para(tf, "① 两库 all data 的列布局不一致：主库文献 4/6/7/9 组放的是浓度，姊妹库同一位置放的是 OAV"
         " → 合并时必须按列名而非按位置对齐。", size=11.5, sa=5)
para(tf, "② 主库只保留了 12 个文献工作表，姊妹库有 34 个 → 主库不是姊妹库的超集，二者信息互补。",
     size=11.5, sa=5)
para(tf, "③ 主库的 Threshold 与 Concentration（μg/L）两列在源文件中完全为空 → 课题技术路线的第一步即断链。",
     size=11.5, sa=0)
tf = panel(s, L, 5.52, CW, 1.18, fill=LIGHT, line=BLUE, title="本次处理的策略", pad=0.22)
rich(tf, [("以 ", False, TEXT), ("data总库.xlsx", True, PRIMARY),
          (" 为清洗主体，把 ", False, TEXT), ("data.xlsx", True, PRIMARY),
          (" 仅作为校验与修复的参照；两个源文件全程只读打开，未做任何修改。", False, TEXT)],
     size=11.5, first=False, sa=0)
footer(s)

# =============================================================== 04 主库结构
s = slide_head("主库结构：63 个化合物 × 156 个数值列", "all data = 7 列元数据 + 156 列文献样品数据")
tf = panel(s, L, TOP, 4.30, 5.30, fill=LIGHT2, line=CARD_LINE,
           title="7 列元数据", pad=0.22)
for c, hot in [("Order ID", 0), ("CAS", 0), ("Odorants（英文名）", 0), ("中文名称", 0),
               ("SMILES（分子结构）", 0), ("Threshold", 1), ("Concentration（μg/L）", 1)]:
    para(tf, "· " + c + ("　← 整列全空" if hot else ""), size=12,
         color=ACCENT if hot else TEXT, sa=4)
para(tf, "156 列数值列的组织方式", size=13.5, bold=True, color=PRIMARY, sb=12, sa=6)
para(tf, "只有每组首列带文献编号与单位，后续列是“裸样品名”（GRD-JC、SC2、NX4…）——"
         "必须做表头前向填充，才能还原 156 列的语义（已实现）。",
     size=11.5, color=GREY, sa=0)
txt_l = ["1　基础酒 vs GJ-1573", "2　Y1/Y3/Y5/Y8/Y11 陈酿序列", "3　LZLJ-M7 / LZLJ-T7",
         "4　LS / FS 液液萃取", "5　脉冲电场 PEF（S1–F3）", "6　JH / SC 产区样品",
         "7　CB / FB / SB", "9　分级基酒 B1–B5", "10　风味重组样品 1–8",
         "11　优级/一级/二级/丢糟", "12　高粱营养品质", "13　四川不同产区",
         "14　GC×GC-MS 含量 A/B/C", "15　全二维 GC-TOFMS", "16　5 种品牌浓香型",
         "17　北派年份标记物"]
txt_r = ["18　不同贮存年份 X0–X8", "19　浓香型 LZ", "20　三种香型 NX",
         "21　浓香型等级评判", "22　乙醇代谢 SC1–SC3", "23　2 / 3 / 5 年陈",
         "24　典型 5 产区 JNC/WLY", "25　山东沂蒙老区", "26　一级好酒–三级酒",
         "27　GC-QTOF MS NX1–NX10", "28　酱香型 vs 浓香型", "29　两种原粮 G1/G2",
         "30　洋河绵柔型白酒", "31　天之蓝 vs 二锅头", "32　基酒味觉特征分组",
         "33　宜宾产区 S-Y*/S-L*"]
tb, tf = textbox(s, 5.05, TOP - 0.02, 3.75, 0.32)
para(tf, "156 列归纳为 33 个研究主题", size=13, bold=True, color=PRIMARY, first=True, sa=0)
for x, lst in ((5.05, txt_l), (9.03, txt_r)):
    tb, tf = textbox(s, x, TOP + 0.36, 3.75, 4.95)
    for k, t in enumerate(lst):
        para(tf, t, size=10, color=TEXT, first=(k == 0), sa=4.5)
footer(s, "文献 24 / 25 / 30 / 32 的样品名直接对应产区与品牌，是课题要求的“产区/品牌”标注素材")

# =============================================================== 05 清洗成果总览
s = slide_head("二、数据清洗：成果总览", "针对三类系统性损坏，加上单位与阈值的补全")
cards = [
    ("100%", "CAS 号通过校验位", "63 行中 33 行损坏，全部修复", GREEN),
    ("156", "个数值列全部标定单位", "含 13 列单位纠错", BLUE),
    ("100", "个数值单元被精确还原", "「删除 0」指纹比对还原", ACCENT),
    ("×1000", "修正一处单位错误", "文献 2、6 组单位标错", ACCENT),
    ("306", "个阈值单元被抽取", "→ 55 个化合物获得阈值", BLUE),
    ("4 426", "个单元算出 OAV", "40 个化合物中位 OAV > 1", GREEN),
]
cw_, ch_ = (CW - 0.36) / 3, 1.58
for i, (big, t, d, col) in enumerate(cards):
    cx = L + (i % 3) * (cw_ + 0.18)
    cy = TOP + (i // 3) * (ch_ + 0.20)
    rect(s, cx, cy, cw_, ch_, fill=LIGHT2, line=CARD_LINE)
    rect(s, cx, cy, 0.075, ch_, fill=col)
    tb, tf = textbox(s, cx + 0.26, cy + 0.15, cw_ - 0.46, ch_ - 0.30)
    para(tf, big, size=26, bold=True, color=col, first=True, sa=1)
    para(tf, t, size=12.5, bold=True, color=PRIMARY, sa=3)
    para(tf, d, size=10.5, color=GREY, sa=0)
tf = panel(s, L, 5.22, CW, 1.50, fill=LIGHT, line=BLUE,
           title="为什么必须清洗：不清洗会直接让后续建模失真", pad=0.22)
para(tf, "· CAS 错误 → 化合物无法与风味阈值库、结构库关联，OAV 无法计算。", size=11.5, sa=4)
para(tf, "· 数值丢位（738,302 被存成 738,32）→ 相关系数、PCA、聚类、OAV 排序同时失真。", size=11.5, sa=4)
para(tf, "· 单位差 1000 倍 → “保留 OAV > 1”的变量筛选完全失效。", size=11.5, sa=0)
footer(s)

# =============================================================== 06 CAS
s = slide_head("清洗发现 ①　CAS 号被「删除数字中的所有 0」破坏",
               "63 行中 33 行损坏 —— 这是数据集最严重的系统性问题")
rows = [
    ["损坏模式", "源文件实例　→　修复结果"],
    ["中间的 0 被删", "18-64-5 → 108-64-5　·　15-54-4 → 105-54-4　·　16–32–1 → 106-32-1"],
    ["末尾的 0 被删", "123-66- → 123-66-0　·　513-86- → 513-86-0　·　11-43- → 110-43-0"],
    ["多个 0 被删", "11-38-3 → 110-38-3　·　98-- → 98-00-0　·　51-52- → 501-52-0"],
    ["被 Excel 当成日期", "3658-08-08 00:00:00 → 3658-80-8　·　216/3/9 → 106-30-9　·　216/7/7 → 106-70-7"],
    ["进位被抹掉", "221-28-5 → 2021-28-5　·　79-9-4 → 79-09-4　·　59-86-3 → 590-86-3"],
    ["破折号混用（en dash）", "16–32–1 → 106-32-1　·　25415–67–2 → 25415-67-2"],
]
add_table(s, rows, L, TOP, CW, col_w=[2.6, 9.6], row_h=[0.36] + [0.40] * 6)
tb, tf = textbox(s, L, 4.42, CW, 2.2)
para(tf, "三级修复策略", size=14, bold=True, color=PRIMARY, first=True, sa=7)
para(tf, "① 规范化连接符：en dash / em dash / 空格 → 半角连字符。", size=12, sa=5)
para(tf, "② 以 SMILES 作为分子身份键连接姊妹库 data.xlsx —— 33 行全部命中。", size=12, sa=5)
para(tf, "③ 兜底：以 CAS 校验位为约束，在任意位置重新插入 0 搜索合法 CAS（本数据集未用到，逻辑已保留）。",
     size=12, sa=8)
rich(tf, [("结果：", True, GREEN), ("63 / 63 行 CAS 全部通过校验位验证。", True, GREEN),
          ("　建议同时保留一份原始 CSV 作为对照。", False, GREY)], size=12, sa=0)
footer(s)

# =============================================================== 07 数值修复
s = slide_head("清洗发现 ②　同一机制也污染了浓度数值",
               "用「删除 0」留下的精确指纹，从姊妹库还原了 100 个数值单元")
tf = panel(s, L, TOP, CW, 1.20, fill=RED_BG, line=ACCENT,
           title="判据：把数字中所有「0」去掉后，两者的残留完全相同 → 即判定为丢位损坏，且正确值唯一",
           title_color=ACCENT, pad=0.22)
rich(tf, [("主库：", True, PRIMARY), ("738,32", True, ACCENT),
          ("　→ 去零残留 ", False, GREY), ("「73832」", False, GREY),
          ("　　　姊妹库：", True, PRIMARY), ("738,302", True, GREEN),
          ("　→ 去零残留 ", False, GREY), ("「73832」", False, GREY),
          ("　　✓ 命中", True, GREEN)], size=12.5, sa=0)
rows = [
    ["化合物", "列（文献/样品）", "主库（损坏）", "还原后"],
    ["己酸乙酯", "3　LZLJ-T7", "738,32 ± 3649", "738,302 ± 3649"],
    ["己酸乙酯", "5　S1 (mg/L)", "126.133", "1206.133"],
    ["丁酸乙酯", "5　S3 (mg/L)", "15.311", "105.311"],
    ["丁酸乙酯", "10　1mg/L", "94 ± 14.6", "940 ± 14.6"],
    ["异戊酸乙酯", "5　S2 (F3) (mg/L)", "4.37", "4.307"],
]
add_table(s, rows, L, 2.80, CW, col_w=[1.7, 2.7, 3.0, 3.0], row_h=[0.34] + [0.34] * 5)
tf = panel(s, L, 4.94, CW, 1.82, fill=LIGHT, line=BLUE, pad=0.22,
           title="这是本次清洗中价值最高的单项修复")
para(tf, "若不清洗，相关系数、PCA、聚类与 OAV 排序都会同时失真 —— 而且这类错误很隐蔽："
         "数字看起来完全正常，只是少了一位。", size=11.5, sa=6)
rich(tf, [("完整 100 条修复记录见 ", False, TEXT), ("output/issues_log.csv", True, PRIMARY),
          (" 中的 value_repair 条目，每条都保留了损坏原值与还原值，可逐条回溯。", False, TEXT)],
     size=11.5, sa=0)
footer(s)

# =============================================================== 08 单位错误
s = slide_head("清洗发现 ③　一处 ×1000 的单位错误",
               "文献 2、6 组把 mg/L 标成了 μg/L —— 由两条独立证据确认")
tf = panel(s, L, TOP, CW, 1.16, fill=LIGHT2, line=CARD_LINE,
           title="证据一：与姊妹库的表头不一致", pad=0.22)
rich(tf, [("主库表头：", True, TEXT), ("Y1（μg/L）", False, ACCENT),
          ("　　　姊妹库表头：", True, TEXT), ("2  Y1 μg/ml", False, GREEN)], size=12, sa=4)
rich(tf, [("μg/mL ≡ mg/L，两者相差 ", False, TEXT), ("1000 倍", True, ACCENT),
          (" —— 单位在从姊妹库复制到主库时被改写。", False, TEXT)], size=12, sa=0)
tf = panel(s, L, 2.72, CW, 1.62, fill=LIGHT2, line=CARD_LINE,
           title="证据二：OAV 恒等式反证（文献 6 组，己酸乙酯）", pad=0.22)
rich(tf, [("主库 ", False, TEXT), ("6 JH1", True, PRIMARY), (" 值为 ", False, TEXT),
          ("2 491.482", True, ACCENT), ("，若按 mg/L 计：", False, TEXT)], size=12, sa=5)
rich(tf, [("2 491.482 mg/L ÷ 55.3 μg/L = ", False, TEXT), ("45 054", True, ACCENT)], size=12, sa=5)
rich(tf, [("姊妹库同一位置 ", False, TEXT), ("6 JH1 OAV = 45 299.64", True, GREEN),
          ("　→　吻合（差 0.5%）", True, GREEN)], size=12, sa=0)
tf = panel(s, L, 4.48, CW, 2.24, fill=GREEN_BG, line=GREEN,
           title="处理结果", title_color=GREEN, pad=0.22)
para(tf, "· 已把文献 2、6 两组共 13 列的单位修正为 mg/L。", size=11.5, sa=5)
para(tf, "· 在 column_registry.csv 中标记为 corrected_declared，并保留修正前的原值"
         "（unit_pre_correction 列）以便追溯。", size=11.5, sa=5)
para(tf, "· 修正后这 13 列全部通过「己酸乙酯尺度校验」。", size=11.5, sa=5)
para(tf, "· 单位统一后，5 018 个数值单元全部换算为 μg/L，可直接进入建模。", size=11.5, sa=0)
footer(s)

# =============================================================== 09 阈值与 OAV
s = slide_head("阈值补全与 OAV 计算",
               "主库 Threshold 列全空 → 从 12 个文献工作表抽取阈值并建立多来源共识")
rows = [
    ["步骤", "数量", "说明"],
    ["抽到的阈值单元", "306", "来自 12 个文献工作表的阈值列（含主库丢掉的“原始/标准顺序/OAV”并列块）"],
    ["命中主库化合物", "175", "未命中的 131 个单元对应主库尚未整合的化合物（见第五部分）"],
    ["建立阈值的化合物", "55", "多来源取中位数，同时保留 min / max 供敏感性分析"],
    ["可计算 OAV 的单元", "4 426", "其中 3 304 个来自通过单位校验的列，用于 OAV 汇总"],
    ["中位 OAV > 1 的化合物", "40", "课题方案要求保留 OAV > 1 的化合物作为建模变量"],
    ["关键化合物（覆盖 ≥20 列）", "20", "满足课题“20 个关键化合物”的规模要求"],
]
add_table(s, rows, L, TOP, CW, col_w=[2.6, 1.1, 8.5], row_h=[0.36] + [0.38] * 6)
tf = panel(s, L, 4.44, CW, 2.28, fill=LIGHT, line=BLUE, pad=0.22,
           title="补齐后，课题技术路线的第一步「阈值 → OAV → 保留 OAV>1」已经打通")
rich(tf, [("己酸乙酯", True, ACCENT),
          ("是唯一的“双高”物质：中位 OAV ≈ 2.3×10⁴，且在 ", False, TEXT),
          ("109 / 109", True, PRIMARY),
          (" 个可用列中全部被报道 —— 与它作为浓香型白酒骨架与标志物的共识一致。", False, TEXT)],
     size=12, sa=7)
rich(tf, [("反例：", True, PRIMARY),
          ("乙酸乙酯浓度最高（10⁵–10⁶ μg/L 量级），但阈值高达 32 600 μg/L，中位 OAV 仅 ", False, TEXT),
          ("15.6", True, ACCENT),
          (" —— 这正是必须用 OAV 而不是浓度来筛选变量的原因。", False, TEXT)], size=12, sa=0)
footer(s, "阈值来源与分布：output/thresholds_raw.csv、output/thresholds_consensus.csv")

# =============================================================== 10 质量判定
s = slide_head("三、质量判定：156 个数值列哪些可用",
               "以己酸乙酯为尺度标尺（浓香型白酒定义性组分，文献值 0.5–4 g/L）")
tf = panel(s, L, TOP, 5.90, 1.30, fill=GREEN_BG, line=GREEN,
           title="109 列（70%）通过校验", title_color=GREEN, pad=0.22)
para(tf, "标记 usable_absolute = True，可用于绝对浓度与 OAV 分析，也用于本报告的 PCA、"
         "DBSCAN 与权重表。", size=11.5, sa=0)
tf = panel(s, L + 6.10, TOP, CW - 6.10, 1.30, fill=RED_BG, line=ACCENT,
           title="41 列（26%）尺度异常，已隔离", title_color=ACCENT, pad=0.22)
para(tf, "仅参与秩相关等无量纲分析；未自动改写数值，附推断单位供回原文核对。",
     size=11.5, sa=0)
tb, tf = textbox(s, L, 2.86, CW, 0.32)
para(tf, "待核对单位清单（按文献分组）", size=13.5, bold=True, color=PRIMARY, first=True, sa=0)
rows = [
    ["文献", "列数", "己酸乙酯换算值 (μg/L)", "推断"],
    ["10　风味重组样品", "7", "192 – 1 157", "重组模型酒、非真实酒样，低值属正常"],
    ["24　典型 5 产区", "5", "883 – 1 591", "疑似应为 mg/L（×1000）"],
    ["25　沂蒙老区成品酒 / 新老原酒", "8", "182 – 3 152", "疑似应为 mg/L（×1000）"],
    ["13　四川不同产区", "4", "1.76×10⁸（176 g/L）", "声明 g/L 过大，疑似应为 mg/100mL"],
    ["32　基酒味觉特征分组", "5", "9.7×10¹⁰", "声明 g/L 严重过大，单位待定"],
    ["22/28/31/12/17/11/23/33", "各 1–3", "69 – 7 889", "单列异常，需回原文核对"],
]
add_table(s, rows, L, 3.24, CW, col_w=[3.3, 0.9, 2.5, 5.5], row_h=[0.32] + [0.36] * 6)
footer(s, "交叉验证：DBSCAN 判出的离群样品与上述单位异常列，独立地指向同一批数据 —— 两个判据互相印证")

# =============================================================== 11 路线对应
s = slide_head("四、关系挖掘：与课题技术路线的对应", "已完成的路段　vs　补齐感官 Y 之后才能执行的路段")
steps = [("阈值", "306 单元", True), ("OAV", "4 426 单元", True),
         ("层次聚类 + DBSCAN", "变量组 + 样本簇", True),
         ("风味贡献权重表", "已产出基线", True),
         ("PLSR / VIP", "需感官 Y", False), ("符号回归 F(X)=Y", "需感官 Y", False)]
bw, bh = (CW - 2 * 0.34) / 3, 1.02
for i, (t, d, done) in enumerate(steps):
    bx = L + (i % 3) * (bw + 0.34)
    by = TOP + 0.02 + (i // 3) * (bh + 0.24)
    col = GREEN if done else RGBColor(0xBF, 0xBF, 0xBF)
    rect(s, bx, by, bw, bh, fill=GREEN_BG if done else LIGHT2, line=col, line_w=1.25)
    tb, tf = textbox(s, bx + 0.16, by + 0.13, bw - 0.32, bh - 0.26)
    para(tf, t, size=13, bold=True, color=PRIMARY if done else GREY, first=True, sa=3)
    rich(tf, [(d + "　", False, GREY), ("✓ 已完成" if done else "✗ 待补 Y", True, col)],
         size=10.5, sa=0)
tf = panel(s, L, 3.90, CW, 1.06, fill=RED_BG, line=ACCENT, pad=0.22,
           title="关键限制", title_color=ACCENT)
rich(tf, [("数据库里只有 X（化合物浓度），没有任何 Y（感官强度）—— Threshold 列为空、没有 "
           "QDA / RATA 评分、没有描述符强度矩阵。因此 PLSR/VIP 与符号回归目前无法真正执行。",
           False, TEXT)], size=12, sa=0)
tb, tf = textbox(s, L, 5.08, CW, 1.70)
para(tf, "本次关系挖掘已完成的内容", size=13.5, bold=True, color=PRIMARY, first=True, sa=7)
bullets(tf, [
    ("相关矩阵", "62×62 全库 + 20×20 关键化合物（含 P 值与 FDR 校正）"),
    ("变量级层次聚类", "在 62 个化合物上聚类，得到 5 个变量组"),
    ("样品空间", "PCA（前两主成分 56.9%）+ DBSCAN（7 簇 + 28 个离群）"),
    ("共现网络", "文献内相关 + 跨文献一致性检验 → 34 条稳健边"),
    ("风味贡献权重表", "相对 OAV 法，已产出可用的基线与对照"),
], size=11.5, gap=4)
footer(s)

# =============================================================== 12 相关矩阵图
s = slide_head("20 × 20 关键香气化合物相关矩阵",
               "课题「备选方案」：20×20 热图 + 显著性检验（Spearman R，* P<0.05）")
_path = os.path.join(FIG, "fig02_corr20_significance.png")
with Image.open(_path) as _im:
    _iw, _ih = _im.size
_avail_h = BOTTOM - (TOP + 0.06)
_scale = min(7.30 / _iw, _avail_h / _ih)
_w, _h = _iw * _scale, _ih * _scale
s.shapes.add_picture(_path, Inches(L), Inches(TOP + 0.06 + (_avail_h - _h) / 2),
                     Inches(_w), Inches(_h))
tf = panel(s, 7.95, TOP + 0.06, RIGHT - 7.95, _avail_h, fill=LIGHT2, line=CARD_LINE,
           pad=0.22, title="关键化合物怎么选出来的")
para(tf, "中位 OAV > 1 且被 ≥20 个可用列报道，按中位 OAV 降序取前 20 个：", size=11.5, sa=6)
for _l in ["· 己酸乙酯（覆盖 109/109 列）", "· 1-辛烯-3-醇、1-丙醇、二甲基三硫醚",
           "· 丁酸乙酯、戊酸乙酯、辛酸乙酯、异戊酸乙酯", "· 丁酸、戊酸、己醛、乙醛、1-丁醇"]:
    para(tf, _l, size=11.5, color=TEXT, sa=4)
para(tf, "统计口径", size=13, bold=True, color=PRIMARY, sb=10, sa=6)
para(tf, "62 个化合物共 1 693 个可检配对，P<0.05 者 1 183 对，经 Benjamini–Hochberg "
         "FDR 5% 校正后仍有 1 123 对存活。", size=11.5, sa=6)
para(tf, "热图为下三角：红 = 正相关（协同积累），蓝 = 负相关（此消彼长）；"
         "星号越多的格子显著性越高。", size=11.5, sa=6)
rich(tf, [("酯类之间、酸与酯之间形成明显的深红块", True, ACCENT),
          ("，是本次最直观的关系信号。", False, TEXT)], size=11.5, sa=0)
footer(s, "完整矩阵见 output/corr_key20_R.csv 与 corr_key20_P.csv")

# =============================================================== 13 相关解读
s = slide_head("相关矩阵读图要点", "酯类同源同向；酸类是酯的前体；痕量高活性物质独立")
bullets(tf := textbox(s, L, TOP, CW, 3.30)[1], [
    ("酯类之间形成强正相关团",
     "己酸乙酯—丁酸乙酯 R=0.85***、丁酸乙酯—异丁酸乙酯 R=0.80***、"
     "戊酸乙酯—2-甲基丁酸乙酯 R=0.80*** —— 乙酯类同源同向生成，"
     "与「己酸菌–酵母酯化体系共同产生」的机理一致。"),
    ("酸类与酯类同向（前体–产物关系）",
     "丁酸—异丁酸乙酯 R=0.82***、戊酸—丁酸乙酯 R=0.77***、乙酸乙酯—丁酸 R=0.83***"
     " —— 可直接作为勾兑调控的「联动变量对」。"),
    ("1-辛烯-3-醇与多个酯类负相关",
     "与戊酸乙酯 R=−0.50**、与 1-丁醇 R=−0.43* —— 呈现此消彼长，"
     "提示发酵条件或陈酿在两个方向上互相排斥。"),
    ("二甲基三硫醚相对独立",
     "与多数酯类 R≈0.1–0.4，符合其「极低阈值、独立于酯类代谢」的化学行为。"),
], size=13, gap=12)
tf = panel(s, L, 4.90, CW, 1.90, fill=LIGHT, line=BLUE, pad=0.22,
           title="统计口径与必要提醒")
rich(tf, [("62 个化合物共 1 693 个可检配对，P<0.05 者 1 183 对，经 Benjamini–Hochberg FDR 5% "
           "校正后仍有 ", False, TEXT), ("1 123 对", True, PRIMARY), ("存活。", False, TEXT)],
     size=11.5, sa=7)
rich(tf, [("但样品来自不同文献，跨文献相关会混入「文献间偏移」（不同实验室、稀释倍数、检测方法）。"
           "因此下一步改用 ", False, TEXT), ("文献内相关 + 跨文献一致性检验", True, ACCENT),
          (" 来给出更稳健的结论（见共现网络一页）。", False, TEXT)], size=11.5, sa=0)
footer(s)

# =============================================================== 14 聚类图
figure_slide("变量级层次聚类：5 个变量组",
             "课题「1.1 变量级层次聚类」—— 对 1−|Spearman R| 做 Ward 连接聚类",
             "fig04_dendrogram_compounds.png",
             "颜色 = 化学类别；红色虚线为 5 类切分位置，线下即为「变量组」", max_h=5.5)

# =============================================================== 15 变量组解读
s = slide_head("5 个变量组的化学解读与建模意义", "课题计划「锁定树状图底部紧密聚类的几个化合物」已完成")
rows = [
    ["变量组", "数", "代表成员", "化学解读"],
    ["组 1　短链乙酯 / 乙酸酯族", "10", "戊酸乙酯、辛酸乙酯、异丁酸乙酯、2-甲基丁酸乙酯、乙酸异戊酯",
     "发酵早期生成、香气强度高"],
    ["组 2　主体骨架", "35", "己酸乙酯、乙酸乙酯、丁酸乙酯、乳酸乙酯、己酸、丁酸、1-丁醇、己醛",
     "浓香型核心风味集合"],
    ["组 3　陈香 / 芳香族 / 酚醛", "10", "苯乙醛、乙酸苯乙酯、3-苯基丙酸乙酯、4-乙基愈创木酚、三甲基吡嗪",
     "糟香 / 窖香 / 烘焙香载体"],
    ["组 4　痕量高活性", "5", "二甲基三硫醚、1-辛烯-3-醇、2-庚酮、乳酸乙酯、γ-壬内酯",
     "极低阈值、极高 OAV"],
    ["组 5　醛 / 酸小众", "2", "(E)-2-辛烯醛、3-苯基丙酸", "样本量少，独立成组"],
]
add_table(s, rows, L, TOP, CW, col_w=[2.5, 0.6, 6.3, 2.8], row_h=[0.34] + [0.48] * 5)
tf = panel(s, L, 4.52, CW, 2.20, fill=LIGHT, line=BLUE, pad=0.22,
           title="对建模的三点直接意义")
bullets(tf, [
    ("组 4 是符号回归的最佳起点：", "与主体酯类弱相关但 OAV 极高，独立信息量最大，"
     "最可能提供非线性交互项。"),
    ("组 1、组 2 内部共线性严重：", "多条 R>0.8，做 PLSR/VIP 时会被互相稀释，建议先按组降维再建模。"),
    ("组 3 跨越酯–酸–醇类别：", "是「香气描述符 ↔ 化合物」映射的关键候选，与计划中的"
     "焦香↔吡嗪、糟香↔4-乙基愈创木酚体系直接对应。"),
], size=11.5, gap=5)
footer(s)

# =============================================================== 16 PCA 图
figure_slide("样品空间：PCA", "89 个样品 × 20 关键化合物（log₁₀ 后 z-score）：PC1 = 48.1%，PC2 = 8.9%，合计 56.9%",
             "fig05_pca_samples.png",
             "左：碎石图　中：得分图（按文献编号着色）　右：载荷图；PC1 区分酯类骨架丰度层级，PC2 区分芳香族/酚类方向",
             max_h=5.3)

# =============================================================== 17 DBSCAN 解读
s = slide_head("DBSCAN：有效样本簇与离群样本", "课题「1.2 用 DBSCAN 检查样本是否服从模式」")
tf = panel(s, L, TOP, CW, 1.06, fill=LIGHT2, line=CARD_LINE, pad=0.22)
rich(tf, [("参数：", True, PRIMARY),
          ("eps = 2.28（5-近邻 k-距离拐点）、min_samples = 4　→　", False, TEXT),
          ("7 个簇 + 28 个离群样本（31.5%）", True, ACCENT)], size=13, first=True, sa=5)
para(tf, "最大簇含 25 个样品，其余簇 4–11 个 —— 可直接作为后续符号回归的「有效样本簇」。",
     size=11.5, sa=0)
tf = panel(s, L, 2.66, CW, 2.02, fill=GREEN_BG, line=GREEN, pad=0.22,
           title="一个重要的交叉验证", title_color=GREEN)
para(tf, "离群样本主要来自两类来源：", size=12, sa=5)
para(tf, "① 单位异常的文献组（24 / 25 / 32 / 33）；", size=12, sa=4)
para(tf, "② 「重组模型酒」（文献 10）—— 非真实酒样，成分比例被人为设定。", size=12, sa=7)
rich(tf, [("也就是说，", False, TEXT),
          ("DBSCAN 的离群判据与单位合理性判据互相独立地指向了同一批样品", True, GREEN),
          (" —— 两个完全不同的角度交叉验证了数据质量问题，也为「哪些样品不应进入建模」"
           "提供了客观依据。", False, TEXT)], size=12, sa=0)
tf = panel(s, L, 4.86, CW, 1.90, fill=LIGHT, line=BLUE, pad=0.22,
           title="检测方法差异的提示")
para(tf, "化合物 × 文献景观图显示各文献的类别构成差异很大（有的酯类占比 >80%，有的酸类占比显著）"
         "—— 这既反映真实样品差异，也反映不同文献的检测与定量策略差异"
         "（HS-SPME / LLE / GC×GC 对极性物质回收率不同）。", size=11.5, sa=6)
para(tf, "结论：把「检测方法」作为协变量正式标注进数据库是必要的（课题方案已要求），"
         "否则模型会学到方法偏差而非酒体差异。", size=11.5, bold=True, color=ACCENT, sa=0)
footer(s)

# =============================================================== 18 网络图
figure_slide("化合物共现网络：文献内相关 + 跨文献一致性检验",
             "1 219 个化合物对在 ≥2 篇文献中被报道；≥3 篇同向、符号一致率 ≥99%、|平均 R| ≥ 0.6 → 34 条稳健边",
             "fig11_correlation_network.png",
             "红边 = 正相关（协同积累），蓝边 = 负相关（此消彼长）；左图位置由 MDS 按相关距离排布",
             max_h=5.4)

# =============================================================== 19 网络结论
s = slide_head("共现网络给出的稳健关系", "这些结论在多篇独立文献中同向出现，而非单一数据集的偶然相关")
rows = [
    ["化合物 A", "化合物 B", "文献数", "平均 R"],
    ["3-甲基丁基己酸酯", "己酸丁酯", "4", "+0.98"],
    ["己酸丁酯", "己酸己酯", "3", "+0.97"],
    ["3-甲基丁基己酸酯", "壬酸乙酯", "4", "+0.96"],
    ["3-甲基丁基己酸酯", "乙酸异戊酯", "3", "+0.95"],
    ["己酸丁酯", "丁酸异戊酯", "3", "+0.94"],
    ["壬酸乙酯", "庚酸", "3", "−0.77"],
    ["棕榈酸乙酯", "辛酸", "5", "+0.74"],
]
add_table(s, rows, L, TOP, CW, col_w=[3.6, 3.2, 1.3, 1.5], row_h=[0.34] + [0.36] * 7)
tf = panel(s, L, 4.62, CW, 2.14, fill=LIGHT, line=BLUE, pad=0.22,
           title="三条可直接用于建模与生产的结论")
bullets(tf, [
    ("勾兑联动单元：", "正相关对（如己酸丁酯—己酸己酯）在调酒时会同步变化，"
     "可作为同一个调控单元处理，减少待优化变量数。"),
    ("反向约束：", "负相关对（壬酸乙酯—庚酸）可作为配方寻优的约束条件。"),
    ("符号回归的初始变量组：", "优先在正相关团内部寻找比值关系，"
     "对应课题提出的「存在比例关系的化合物集合」。"),
], size=11.5, gap=5)
footer(s)

# =============================================================== 20 权重表图
figure_slide("风味贡献权重表（相对 OAV 法）", "课题最终交付物《风味贡献权重表》的基线版本",
             "fig09_flavor_weights.png",
             "wᵢ = OAVᵢ / ΣOAV（每个样品内部归一化到 100%），再对所有含该化合物的样品取平均")

# =============================================================== 21 权重解读
s = slide_head("权重表解读与方法学边界", "这既是成果，也是后续符号回归应当去检验的假设")
bullets(textbox(s, L, TOP, CW, 3.20)[1], [
    ("己酸乙酯是第一贡献者", "在 109 个样品上平均占 47.4%，且是数据库中唯一全覆盖的化合物。"),
    ("1-辛烯-3-醇「少而强」", "只在 32 个样品中被检出，却达到 45.7% 的平均权重 —— "
     "说明在它被检出的那些样品里几乎与己酸乙酯平分香气活性，建议在感官实验中单独关注。"),
    ("其余物质构成长尾", "均在 1–11% 量级；二甲基三硫醚（阈值仅 0.38 μg/L）占 3.5%，"
     "属典型痕量高活性物质，与变量组 4 对应。"),
], size=13, gap=12)
tf = panel(s, L, 3.86, CW, 2.10, fill=RED_BG, line=ACCENT, pad=0.22,
           title="方法学限制（必须说明）", title_color=ACCENT)
para(tf, "本权重采用相对 OAV 法，隐含假设「各化合物香气强度可线性可加」，"
         "并未考虑协同 / 拮抗 / 掩蔽效应。", size=11.5, sa=6)
rich(tf, [("课题计划的 ", False, TEXT), ("符号回归正是用来检验这一假设的工具", True, PRIMARY),
          ("。因此本表应作为符号回归与泰勒展开的", False, TEXT), ("基线与对照", True, PRIMARY),
          ("，而非最终结论。", False, TEXT)], size=11.5, sa=6)
para(tf, "表内各项分别在不同样品子集上求平均，合计 >100%；需要严格归一化的单样品权重向量，"
         "请使用逐样品占比矩阵 oav_share_matrix.csv。", size=11.5, sa=0)
footer(s)

# =============================================================== 22 陈酿 VIP
figure_slide("陈酿轴：趋势与 PLSR-VIP 方法演示",
             "数据库中唯一存在的连续 Y —— 陈酿年份（n = 10，来自 2 篇文献）",
             "fig12_aging_vip.png",
             "VIP>1：乙酸异戊酯 2.48、1-丙醇 1.49、乙醛 1.45、戊酸 1.43、己醛 1.01、乙偶姻 1.00（R²Y = 0.62）",
             max_h=5.3)

# =============================================================== 23 结论
s = slide_head("五、结论：两个必须优先解决的核心问题",
               "清洗与分析已经完成，但数据库本身还有两个结构性缺口")
tf = panel(s, L, TOP, CW, 2.10, fill=RED_BG, line=ACCENT, line_w=1.4, pad=0.24,
           title="问题一　数据库整合率只有 18%", title_color=ACCENT, title_size=15)
rich(tf, [("主库 all data 已整合化合物 ", False, TEXT), ("62", True, ACCENT),
          ("　|　12 个文献工作表里出现过的不同化合物名 ", False, TEXT), ("341", True, ACCENT),
          ("　|　能匹配上主库的 ", False, TEXT), ("60（18%）", True, ACCENT),
          ("　|　尚未整合 ", False, TEXT), ("281", True, ACCENT)], size=12, sa=7)
para(tf, "例如文献 5 有 119 个、文献 5(PEF) 有 91 个化合物，而主库总共只有 62 行。"
         "且工作表内化合物名存在系统性字符损坏：1-Brussol / 2-Brussol（应为 1-/2-Butanol）、"
         "1,2-benzachol、2-Peramolium、Pantrol 等，疑似一次全局替换或 OCR 错误 —— 需先修名才能整合。",
     size=11.5, sa=0)
tf = panel(s, L, 3.62, CW, 1.62, fill=RED_BG, line=ACCENT, line_w=1.4, pad=0.24,
           title="问题二　数据库只有 X，没有 Y", title_color=ACCENT, title_size=15)
para(tf, "Threshold 列为空、没有 QDA / RATA 评分、没有描述符强度矩阵 → "
         "PLSR/VIP、符号回归、泰勒展开这三个核心环节目前都无法真正执行。"
         "本次已把 X 侧（浓度、阈值、OAV、变量组、样本簇）全部准备好，"
         "并给出相对 OAV 权重表作为基线。", size=11.5, sa=0)
tf = panel(s, L, 5.44, CW, 1.32, fill=GREEN_BG, line=GREEN, pad=0.22)
rich(tf, [("好消息：", True, GREEN),
          ("清洗后的 109 列 × 62 化合物矩阵、55 个化合物阈值、40 个 OAV>1 化合物、"
           "5 个变量组、有效样本簇与稳健相关边均已就绪 —— 感官 Y 一旦补齐，"
           "建模链路可以立即跑通。", False, TEXT)], size=12, first=True, sa=0)
footer(s)

# =============================================================== 24 下一步
s = slide_head("下一步工作计划", "按优先级排序")
rows = [
    ["优先级", "任务", "依据 / 交付"],
    ["P0", "补齐感官 Y 矩阵（QDA / RATA 描述符强度）", "没有 Y，PLSR/VIP、符号回归、泰勒展开无法执行"],
    ["P0", "修复文献工作表中损坏的化合物名，并把 281 个未整合化合物并入主矩阵",
     "直接决定能否达到「150 条样本 × 20 化合物」的目标"],
    ["P1", "核对 41 个尺度异常列的单位，核对后可用列从 109 扩到约 130 列",
     "重点：文献 24/25 疑似应为 mg/L；文献 13/32 的 g/L 标注有误"],
    ["P1", "把产区 / 品牌 / 工艺 / 检测方法四个标签正式建成列",
     "课题方案明确要求；文献 24/25/30/32 已有对应样品名"],
    ["P2", "统一 OAV≈1 附近化合物的阈值，并做阈值敏感性分析",
     "对应学期计划第 1 项；阈值共识表已给出多来源 min / max"],
    ["P2", "用变量组 + 稳健相关对作为符号回归的初始变量组", "优先在组 4（痕量高活性）内部寻找非线性交互"],
    ["P3", "把权重表作为「权重法配比」，与「OAV 法配比」对比", "对应课题第 3 个拟解决问题"],
]
add_table(s, rows, L, TOP, CW, col_w=[0.85, 5.0, 5.5], row_h=[0.34] + [0.50] * 7)
tf = panel(s, L, 5.72, CW, 1.04, fill=LIGHT, line=BLUE, pad=0.22)
rich(tf, [("需要老师指导的问题：", True, PRIMARY),
          ("感官实验的描述符体系与强度标度，如何与数据库中的化合物一一对应？"
           "（这决定了 Y 矩阵的列定义）", False, TEXT)], size=12, first=True, sa=0)
footer(s)

# =============================================================== 25 产出与复现
s = slide_head("附：本次产出与复现方式", "全部位于 new/ 目录，两个源文件保持只读未改动")
tf = panel(s, L, TOP, CW, 1.30, fill=LIGHT2, line=CARD_LINE, pad=0.22, title="交付物")
rich(tf, [("报告　", True, BLUE), ("数据清洗与关系挖掘报告.md", False, TEXT),
          ("　　图表　", True, BLUE), ("figures/ 13 张", False, TEXT),
          ("　　结果表　", True, BLUE), ("output/ 38 个 CSV", False, TEXT)], size=11.5, sa=5)
rich(tf, [("汇总表　", True, BLUE), ("白酒风味数据库_清洗版.xlsx（32 个工作表）", False, TEXT),
          ("　　清洗日志　", True, BLUE), ("issues_log.csv（195 条）", False, TEXT)],
     size=11.5, sa=0)
tb, tf = textbox(s, L, 2.92, CW, 0.30)
para(tf, "复现命令（环境：C:\\anaconda\\python.exe）", size=13, bold=True, color=PRIMARY,
     first=True, sa=0)
rect(s, L, 3.28, CW, 1.28, fill=RGBColor(0x1F, 0x24, 0x2B))
tb, tf = textbox(s, L + 0.22, 3.46, CW - 0.44, 0.98)
for k, line in enumerate([
        '$py = "C:\\anaconda\\python.exe"',
        "& $py new\\10_extract_sources.py    # 12 个文献工作表 → 整洁长表",
        "& $py new\\20_clean_master.py       # 主库清洗：CAS / 名称 / 单位 / 数值 / 阈值 / OAV",
        "& $py new\\30_analyze.py            # 关系挖掘 + 全部绘图",
        "& $py new\\40_export_excel.py       # 汇总导出 Excel"]):
    para(tf, line, size=10, color=RGBColor(0xD4, 0xD4, 0xD4), first=(k == 0), sa=1)
rows = [
    ["关键结果文件", "内容"],
    ["column_registry.csv", "156 列登记表：文献 / 样品 / 单位 / 可信度 / 是否可用"],
    ["master_wide_ugL.csv", "统一为 μg/L 的宽表（可直接进入建模）"],
    ["corr_key20_R.csv / _P.csv", "20×20 相关矩阵与 P 值（课题备选方案的直接产出）"],
    ["consensus_correlations.csv", "文献内相关 + 跨文献一致性检验结果"],
    ["oav_weights.csv", "风味贡献权重表"],
]
add_table(s, rows, L, 4.72, CW, col_w=[3.6, 7.6], row_h=[0.32] + [0.32] * 5)
footer(s)

# =============================================================== 26 结束
s = prs.slides.add_slide(BLANK)
rect(s, 0, 2.35, SW, 0.06, fill=ACCENT)
tb, tf = textbox(s, 1.0, 2.72, SW - 2.0, 1.4)
para(tf, "请老师批评指正", size=38, bold=True, color=PRIMARY, first=True, sa=16,
     align=PP_ALIGN.CENTER)
para(tf, "汇报人：夏童　|　导师：徐岩　教授　|　指导小组：马玥　助理研究员",
     size=14, color=GREY, sa=0, align=PP_ALIGN.CENTER)

prs.save(OUT)

# python-pptx keeps the default template's type="screen4x3" hint even after the
# slide size is changed, which makes some renderers scale/crop the page. Fix it.
import zipfile, shutil, re  # noqa: E402
tmp = OUT + ".tmp"
with zipfile.ZipFile(OUT) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == "ppt/presentation.xml":
            data = re.sub(rb'<p:sldSz([^>]*?)type="screen4x3"',
                          rb'<p:sldSz\1type="screen16x9"', data)
        zout.writestr(item, data)
shutil.move(tmp, OUT)

print("saved:", OUT)
print("slides:", len(prs.slides._sldIdLst))
