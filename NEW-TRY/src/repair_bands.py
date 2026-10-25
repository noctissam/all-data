# -*- coding: utf-8 -*-
"""
Repair band tables whose rows were never split into columns.

The failure
-----------
One OCR box occasionally spans several printed columns, so a whole row collapses into a
single cell: "甲酸乙酯 127.47 129.13 258.12" instead of four cells. Everything
downstream then believes the compound is called "甲酸乙酯 127.47 129.13 258.12" and
reports the quantitative columns as empty. The numbers are not lost, they are just filed
under the wrong heading.

Most of these are two-panel tables - the paper prints 类别|值|值|值|值 twice side by side -
and it is the right panel that gets swallowed by the left panel's name cell.

What this does
---------------
Per table, a declared target column count plus a declared layout, so the split is decided
by the table and not by guessing from the cell. Anything that does not fit the declared
shape is left exactly as it was and reported, because a wrong split is worse than a
visible merge: the repair has to be checkable.

Verification is arithmetic where the table allows it. 表3-4 准确度实验 prints its own
recovery rate, and for every row (加标 - 本底) / 添加 reproduces it to the printed
percent, which is an independent confirmation that 本底 / 添加 / 加标 were separated
correctly and not, say, shifted one column.

Full-width digits are normalised to ASCII while parsing. "211．77 ～722．07" does not
sort or average as text; keeping the glyphs and losing the number helps nobody.

Run:
    python src/repair_bands.py --dry-run
    python src/repair_bands.py
"""

import argparse
import json
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))

# ---------------------------------------------------------------- parsing helpers

CJK = r"\u4e00-\u9fff"

# A number as the OCR writes it: ASCII, or full-width, with l/I/1 and 0/O confusions.
# The OCR confuses 1 with l/I/| and 0 with O, and it does so inside row numbers
# ("l8" for 18, "2l" for 21). A digit class alone would reject every one of those and the
# serial would stay glued to the name it belongs to, which is the bug being fixed here.
NUM_CORE = r"[0-9lI|０-９](?:[0-9lI|０-９]*[0-9lI|０-９])?(?:[.．,，][0-9lI|０-９]+)?"
NUM_SRC = NUM_CORE
NUM_RE = re.compile(r"^%s$" % NUM_CORE)
FULLWIDTH = str.maketrans("０１２３４５６７８９．，－～（）", "0123456789.,-~()")

# "211．77 ～722．07" / "1 124．35" - a printed range is one value, not two.
RANGE_RE = re.compile(
    r"^(?P<a>%s)\s*[～~]\s*(?P<b>%s)$" % (NUM_SRC, NUM_SRC))

# One OCR box spanning several printed columns: some text then two or more numbers.
MERGED = re.compile(r"^(?P<head>.*\S)\s+%s\s+%s(?P<rest>.*)$" % (NUM_SRC, NUM_SRC))


def norm(s):
    """Full-width punctuation and digits to ASCII. Leaves CJK alone."""
    return (s or "").translate(FULLWIDTH)


def is_num(tok):
    return bool(NUM_RE.match(norm(tok).strip()))


def to_num(tok):
    """'l8' -> 8.0, '51.0l' -> 51.0, '211．77' -> 211.77.

    Only the OCR-confusable glyphs are touched: l/I/| -> 1, O -> 0. A genuine letter in a
    compound name never reaches here, because the name is taken as the leading text run
    before any numeric parsing starts.
    """
    s = norm(tok).strip().replace(" ", "")
    s = re.sub(r"[lI|]", "1", s)
    s = s.replace("O", "0").replace("o", "0")
    s = re.sub(r"[ ,]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def serial(tok):
    """An OCR'd row number: '14', 'l3', '2l', 'l8'. Returns int or None."""
    v = to_num(tok)
    if v is None or abs(v - round(v)) > 1e-9:
        return None
    return int(round(v))


def classify_interleaved(cell, n_left=4):
    """
    Split a two-panel row: 名称A a1..a4 名称B b1..b4 -> (A, B, a[], b[]).

    classify() cannot be used here because it collapses the whole row into one text run
    ("酯类 1.00 ... 呋喃类（×10-2） 0.72") and loses the fact that a SECOND name sits in the
    middle. So the tokens are walked in order and the panel boundary is found from the
    count: the first name is everything before the first number, the second name is the
    run of text tokens that starts after the n_left numbers.
    """
    toks = norm(str(cell or "")).strip().split()
    if not toks:
        return "", "", [], []

    def is_txt(t):
        return not is_num(t) and not RANGE_RE.match(t)

    # first name: leading text tokens
    i = 0
    left_name = []
    while i < len(toks) and is_txt(toks[i]):
        left_name.append(toks[i])
        i += 1
    left_vals = []
    while i < len(toks) and len(left_vals) < n_left and (is_num(toks[i]) or RANGE_RE.match(toks[i])):
        left_vals.append(toks[i])
        i += 1

    # second name: the next run of text tokens
    right_name = []
    while i < len(toks) and is_txt(toks[i]):
        # a scale factor belongs to the name, not to a number
        right_name.append(toks[i])
        i += 1
    right_vals = []
    while i < len(toks) and (is_num(toks[i]) or RANGE_RE.match(toks[i])):
        right_vals.append(toks[i])
        i += 1

    a = " ".join(left_name)
    b = " ".join(right_name)
    # re-attach a trailing scale factor that classify-style tokenising split off
    if left_vals and re.search(r"[×x]\s*10", left_vals[-1], re.I):
        a = (a + left_vals[-1]).strip()
        left_vals = left_vals[:-1]
    return a, b, left_vals, right_vals


def classify(cell):
    """
    Split one merged cell into (leading text, [value tokens]).

    value tokens are returned as display strings, already normalised. A range stays a
    single token so a min-max pair is not mistaken for two measurements.
    """
    s = norm(str(cell or "")).strip()
    if not s:
        return "", []
    toks = s.split()
    text_parts, vals = [], []
    for t in toks:
        if is_num(t):
            vals.append(norm(t).strip())
        elif RANGE_RE.match(t):
            vals.append(t)
        else:
            # a name chunk may carry its own trailing scale factor, e.g. 芳香族（×10-2）
            if vals and re.search(r"[×x]\s*10", t, re.I):
                vals[-1] = vals[-1] + t
            else:
                text_parts.append(t)
    return " ".join(text_parts), vals


# ---------------------------------------------------------------- table handlers
#
# Each handler: (table, ctx) -> dict(rows=..., header=..., note=...)
# `ctx` collects warnings for rows that could not be repaired.


def _pad(rows, n):
    return [list(r) + [""] * (n - len(r)) for r in rows]


def r21_t9(t, ctx):
    """表3-4 准确度实验: 风味物质 | 本底 | 添加 | 加标测定 | 回收率.

    Every row is checked against its own printed recovery rate, so a mis-split cannot
    survive here.
    """
    out, n = [], 5
    hdr = ["风味物质", "本底浓度（mg/L）", "添加浓度（mg/L）",
           "加标测定（mg/L）", "回收率"]
    ok = bad = 0
    for i, r in enumerate(t["rows"]):
        name, vals = classify(r[0] if r else "")
        rec = str(r[1]).strip() if len(r) > 1 else ""
        if name and len(vals) == 3:
            base, spike, found = (to_num(v) for v in vals)
            m = re.match(r"^([\d.]+)\s*%", rec)
            if None not in (base, spike, found, m) and spike:
                calc = (found - base) / spike * 100.0
                if abs(calc - float(m.group(1))) < 0.05:
                    ok += 1
                else:
                    bad += 1
                    ctx.warn(t, i, "回收率对不上: 算得 %.2f%% 印刷 %s" % (calc, rec))
            out.append([name, vals[0], vals[1], vals[2], rec])
        else:
            ctx.warn(t, i, "形状不符(名称=%r 数值%d个)，原样保留" % (name, len(vals)))
            out.append(list(r))
    ctx.note("回收率算术自检: %d 行吻合, %d 行不符" % (ok, bad))
    return {"rows": _pad(out, n), "header": hdr, "ncol": n}


def r21_t2(t, ctx):
    """表2-2 微波消解程序: two stacked sub-tables sharing one OCR grid."""
    out, n = [], 4
    for i, r in enumerate(t["rows"]):
        c0 = str(r[0]).strip() if r else ""
        name, vals = classify(c0)
        rest = [str(x).strip() for x in r[1:]]
        if name == "" and len(vals) >= 3 and not any(rest):
            out.append(vals[:4])                       # 功率 升温 温度 保持
        elif name and vals and "=" in name:             # 元素 + 线性方程
            out.append([name, "", "", to_num(vals[0]) if is_num(vals[0]) else vals[0]])
        elif name and len(vals) >= 2:                   # 元素 + 方程(R2 在另一列)
            out.append([name, " ".join(vals), "", to_num(rest[0]) if rest else ""])
        else:
            out.append(list(r))
    return {"rows": _pad(out, n), "header": ["列1", "列2", "列3", "列4"], "ncol": n}


def r25_t1(t, ctx):
    """表2 不同品牌酒样中风味物质含量.

    This table's eight columns are already correct in the band file, so the only thing to
    repair is the handful of rows where the OCR glued the retention index onto the front
    of the compound name ("389 己酸己酯"). An earlier version of this handler rebuilt the
    whole row from tokens, which on an already-split table shifted every value one column
    left - the RI column received the first measurement, WLY received the second, and the
    concentrations ended up under the wrong brands. Nothing is rebuilt here: only the name
    cell is touched, and only when it actually carries a leading index.
    """
    n = t.get("n_col") or 8
    out, fixed, joined = [], 0, 0
    ri_lead = re.compile(r"^(?P<ri>[＜<]\s*\d+|\d{2,4})\s+(?P<nm>\S.*)$")
    for i, r in enumerate(t["rows"]):
        row = [str(x).strip() for x in r] + [""] * (n - len(r))
        first = row[0]
        if first and i > 0:
            m = ri_lead.match(first)
            if m:
                row[0] = m.group("nm").strip()
                ri = m.group("ri").strip()
                # The index belongs in the RI column. On rows where the OCR split it
                # across two cells it reads "1" in the RI column and "389" glued to the
                # name, which is one number, 1389 - retention indices here run 700-1400, so
                # neither half is a plausible index on its own. Rejoin them when the split
                # is obvious rather than storing "1" as the answer.
                if n > 1:
                    cur = row[1]
                    if re.fullmatch(r"\d{1,2}", cur) and re.fullmatch(r"\d{3,}", ri):
                        row[1] = cur + ri
                        joined += 1
                    elif not cur:
                        row[1] = ri
                fixed += 1
        out.append(row)
    ctx.note("RI 从名称中拆出 %d 行（其中 %d 行把被拆成两格的保留指数接回），其余列原样保留" % (fixed, joined))
    return {"rows": _pad(out, n), "header": HEADERS[("25", "品牌")], "ncol": n}


def r28_t0(t, ctx):
    """表2 精密度/重复性/稳定性: 化合物 | 精密度(含量,RI) | 稳定性(含量,RI) | 重复性(含量,RI)."""
    out, n = [], 7
    hdr = ["风味物质", "精密度 含量", "精密度 相对保留时间", "稳定性 含量",
           "稳定性 相对保留时间", "重复性 含量", "重复性 相对保留时间"]
    for i, r in enumerate(t["rows"]):
        name = str(r[0]).strip() if r else ""
        _, a = classify(r[1] if len(r) > 1 else "")
        _, b = classify(r[2] if len(r) > 2 else "")
        vals = a + b
        if name and len(vals) == 6:
            out.append([name] + vals)
        elif name and not vals:
            out.append([name] + [""] * 6)
        else:
            if name and vals:
                ctx.warn(t, i, "数值 %d 个(应为6)，原样保留: %r" % (len(vals), name[:30]))
            out.append(list(r))
    ctx.note("6 个 RSD 子列按 精密度/稳定性/重复性 × 含量/相对保留时间 归位")
    return {"rows": _pad(out, n), "header": hdr, "ncol": n}


def _two_panel(name_a, name_b, t, ctx, idx_range=None):
    """
    Split 名称A a1 a2 a3 a4 名称B b1 b2 b3 b4 into ten columns.

    The serial number of the right panel is whatever trails the left panel's values; in
    every table here it is the next row number, and it is read back as a serial rather
    than as a concentration.
    """
    rows = t["rows"][idx_range] if idx_range else t["rows"]
    out, n = [], 10
    left_names, right_names = [], []
    for i, r in enumerate(rows):
        raw = str(r[0]).strip() if r else ""
        name, vals = classify(raw)
        # a right-panel name may be glued after the left values
        if len(vals) > 4:
            head, tail = vals[:4], vals[4:]
            rname, rvals = "", tail
            if len(tail) >= 5:
                rname = " ".join(tail[:-4])
                rvals = tail[-4:]
            elif len(tail) == 4 and name:
                rname, rvals = "", tail
            out.append([name] + head + [rname] + rvals)
            left_names.append(name)
            right_names.append(rname)
            continue
        if len(vals) == 4:
            out.append([name] + vals + [""] * 5)
        elif not name and len(vals) == 6:
            ctx.warn(t, i, "两栏名称都缺失，只剩6个数值: %r" % (" ".join(vals)[:40],))
            out.append([""] + vals[:4] + [""] + vals[4:])
        elif name and not vals:
            ctx.warn(t, i, "只有名称无数值(换行错位): %r" % name[:30])
            out.append([name] + [""] * 9)
        else:
            ctx.warn(t, i, "形状不符(%d个数值)，原样保留: %r" % (len(vals), raw[:40]))
            out.append(list(r) + [""] * (n - len(r)))
    return out, n


def r29_t0(t, ctx):
    """表1-2 酱香习酒·窖藏1988 和茅台酒: 序号|组分名|习酒|茅台 打印两遍, 共8列."""
    out, n = [], 8
    hdr = ["序号", "组分名", "习酒·窖藏1988", "茅台酒",
           "序号", "组分名", "习酒·窖藏1988", "茅台酒"]
    for i, r in enumerate(t["rows"]):
        s1 = str(r[0]).strip() if r else ""
        # n_left=2: 序号|组分名|习酒|茅台 printed twice, so two values sit on the left
        name, _, vals, extra = classify_interleaved(r[1] if len(r) > 1 else "", 2)
        nm2 = str(r[2]).strip() if len(r) > 2 else ""
        v2 = [str(x).strip() for x in (r[3:5] if len(r) > 4 else [])]
        # the right panel's serial is whatever trails the left panel's two values
        s2 = ""
        if extra:
            cand = serial(extra[0])
            # only accept it as a serial if it continues the left panel's numbering
            if cand is not None and serial(s1) is not None and cand > serial(s1):
                # keep the printed glyphs: 'l8' is what the page says as read, and
                # silently turning it into 18 would make the sheet disagree with the
                # image on a row nobody flagged
                s2 = extra[0]
        if name and len(vals) == 2:
            out.append([s1, name, vals[0], vals[1], s2, nm2, v2[0] if v2 else "",
                        v2[1] if len(v2) > 1 else ""])
        elif name and not vals:
            # A name with no numbers of its own. Two reasons: the printed cell wrapped
            # across lines, or this row carries only the right-hand panel's name. Both are
            # kept verbatim rather than guessed at - the text survives, and the reattach
            # pass below recovers the numbers when the pairing is unambiguous.
            out.append([s1, name, "", "", s2, nm2, v2[0] if v2 else "",
                        v2[1] if len(v2) > 1 else ""])
        elif not name and len(vals) == 2:
            # values-only row: the name wrapped onto the row above
            out.append([s1, "", vals[0], vals[1], s2, nm2,
                        v2[0] if v2 else "", v2[1] if len(v2) > 1 else ""])
        else:
            ctx.warn(t, i, "形状不符(名称=%r 数值%d个)，原样保留"
                     % (name[:20], len(vals)))
            out.append(list(r) + [""] * (n - len(r)))
    ctx.note("右栏序号从左栏数值尾部取出(仅当它接着左栏编号递增)")

    # A name that wrapped across printed lines leaves a name-only row immediately above a
    # values-only row. Once split, the pair is obvious: the name row has no values and the
    # next row has no name. Reattach, so 1,1-二乙氧基异 / 23.27 19.48 / 戊烷 becomes one
    # compound with its two numbers instead of three fragments.
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        name_only = (a[1] and not a[2] and not a[3] and not a[5] and not a[6] and not a[7])
        vals_only = (not b[1] and b[2] and b[3] and not b[5] and b[6] and b[7])
        if name_only and vals_only:
            a[2], a[3] = b[2], b[3]
            b[1], b[2], b[3] = "", "", ""
            ctx.note("行%d/%d 合并：折行名称与其数值归回同一化合物" % (i, i + 1))
    return {"rows": _pad(out, n), "header": hdr, "ncol": n}


def r29_t6(t, ctx):
    """表3-3 与表3-4 挤在同一张 OCR 网格里: 拆成两张表, 各自两栏."""
    rows = t["rows"]
    # the printed 表3-4 caption is the split point
    cut = next((i for i, r in enumerate(rows)
                if "表 3-4" in str(r[2] if len(r) > 2 else "")), None)
    a_rows = rows[:cut] if cut else rows
    b_rows = rows[cut:] if cut else []
    hdr = ["类别", "酒", "香", "甜", "窖底", "类别", "酒", "香", "甜", "窖底"]

    def do(sub, tag):
        out = []
        for i, r in enumerate(sub):
            ra, _, va, _ = classify_interleaved(r[0] if r else "", 4)
            rb, vb = classify(r[5] if len(r) > 5 else "")
            vals_b = vb or [str(x).strip() for x in (r[6:8] if len(r) > 7 else [])]
            if ra and len(va) == 4:
                out.append([ra] + va + [rb] + (vals_b + [""] * 4)[:4])
            elif not ra and len(va) == 4:
                out.append([""] + va + [rb] + (vals_b + [""] * 4)[:4])
            elif ra and not va:
                out.append([ra] + [""] * 4 + [rb] + (vals_b + [""] * 4)[:4])
            elif ra:
                ctx.warn(t, i, tag + " 左栏数值 %d 个(应为4)，原样保留" % len(va))
                out.append(list(r) + [""] * (10 - len(r)))
            else:
                out.append([""] * 10)
        return out

    a = do(a_rows, "表3-3")
    b = do(b_rows, "表3-4")
    ctx.note("在印刷的 表3-4 标题处断开，拆成 2 张表 (表3-3 %d行 / 表3-4 %d行)" % (len(a), len(b)))
    return {"split": [("表3-3 酱香型习酒中各类香气化合物与酯类的量比关系", a, hdr),
                      ("表3-4 酱香型习酒中重要香气化合物与己酸乙酯的量比关系", b, hdr)]}


def _pdf_for(idx):
    """The source PDF path for a sheet index, from the sheet map."""
    mp = os.path.join(REOUT, "sheet_map.json")
    for e in json.load(open(mp, encoding="utf-8")):
        if e.get("idx") == idx and e.get("path") and os.path.exists(e["path"]):
            return e["path"]
    return None


def r29_t8_textlayer(t, ctx):
    """
    表3-6 / 表3-7 on page 41 of 王晓欣: read from the text layer and split in two.

    The band grid produced one table holding both printed tables, and lost the 芳香族 row
    entirely. Both are read back here from the text layer, which has the complete content,
    and split at the printed caption between them.
    """
    pdf = _pdf_for(29)
    if not pdf:
        ctx.warn(t, 0, "找不到 PDF，保留原样")
        return {"rows": [list(r) for r in t["rows"]], "header": HEADERS[("29", "表3-6")],
                "ncol": t.get("n_col", 10)}
    hdr = HEADERS[("29", "表3-6")]
    a = two_panel_from_textlayer(pdf, 41, 330, 450)     # 表3-6
    b = two_panel_from_textlayer(pdf, 41, 545, 740)     # 表3-7
    ctx.note("从文字层重建：表3-6 %d 行 / 表3-7 %d 行（网格原本丢了 芳香族 并把两表合并）"
             % (len(a), len(b)))
    return {"split": [("表3-6 浓香型习酒中各类香气化合物与酯类的量比关系", a, hdr),
                      ("表3-7 浓香型习酒中重要香气化合物与己酸乙酯的量比关系", b, hdr)]}


def two_panel_from_textlayer(pdf_path, page_no, y0, y1):
    """
    Rebuild a two-panel table straight from the PDF's text layer.

    Used where the band grid is known to be lossy and the text layer is not. On page 41 of
    王晓欣 the grid dropped a whole row (芳香族, which the paper prints at y=437 with four
    values) and ran 表3-7 straight on under 表3-6 without a boundary, because the two tables
    are stacked on one page with only a caption between them. Both problems are visible in
    the text layer and invisible afterwards, so the table is read from there instead.

    Column bands come from where the words actually sit, not from a guess: the name column
    is the leftmost, four values follow, then the right panel's name and its four values.

    The printed scale factor （×10-2） sits on the line BELOW the name it qualifies, so it is
    folded back onto the name above it - otherwise the name reads "3-甲基丁酸乙酯" and a
    stray "（×10-2）" becomes a row of its own.
    """
    import pymupdf
    doc = pymupdf.open(pdf_path)
    pg = doc[page_no - 1]
    words = [w for w in pg.get_text("words") if y0 <= w[1] <= y1]
    doc.close()

    lines = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        if lines and w[1] - lines[-1][0] <= 4.0:
            lines[-1][1].append(w)
        else:
            lines.append((w[1], [w]))

    rows = []
    for _y, ws in lines:
        row = ["", "", "", "", "", "", "", "", "", ""]
        for w in ws:
            x, txt = w[0], w[4]
            if x < 140:
                row[0] = txt
            elif x < 290:
                row[1 + min(3, int((x - 140) / 40))] = txt
            elif x < 380:
                row[5] = txt
            else:
                row[6 + min(3, int((x - 380) / 40))] = txt
        if any(c.strip() for c in row):
            rows.append(row)

    # The scale factor （×10-2） is printed on the line BELOW the row it qualifies, and for
    # the lower rows of 表3-7 the measurements are printed on that same lower line. So this
    # is not only a label to fold up - the whole row has to move up with it, or the
    # compound keeps an empty set of values and a stray "（×10-2）" becomes its own row.
    SCALE_ONLY = re.compile(r"^[（(]?\s*×\s*10[^)）]*[)）]?$")
    out = []
    for r in rows:
        lsc = bool(SCALE_ONLY.match((r[0] or "").strip()))
        rsc = bool(SCALE_ONLY.match((r[5] or "").strip()))
        if out and (lsc or rsc):
            prev = out[-1]
            if lsc:
                prev[0] = (prev[0] + r[0]).strip()
            if rsc:
                prev[5] = (prev[5] + r[5]).strip()
            for i in list(range(1, 5)) + list(range(6, 10)):
                if not prev[i] and r[i]:
                    prev[i] = r[i]
            continue
        out.append(r)

    # The lower rows of 表3-7 print the names on one baseline and the measurements on the
    # NEXT one, with the scale factor below those. So after the fold above, what is left is
    # a name-only row followed by a values-only row that starts with the scale. Pull the
    # values up; otherwise the compound keeps an empty set of measurements and a bare
    # "（×10-2）" row sits under it.
    merged = []
    for r in out:
        if merged:
            prev = merged[-1]
            # a scale factor is not a name: without this the row "（×10-2） 0.14 ..." reads
            # as carrying a name and the row above it never receives its own measurements
            def _nm(row):
                for i in (0, 5):
                    v = (row[i] or "").strip()
                    if v and not SCALE_ONLY.match(v):
                        return v
                return ""
            p_name = _nm(prev)
            p_vals = any((prev[i] or "").strip() for i in list(range(1, 5)) + list(range(6, 10)))
            r_name = _nm(r)
            r_vals = [i for i in list(range(1, 5)) + list(range(6, 10)) if (r[i] or "").strip()]
            if p_name and not p_vals and not r_name and r_vals:
                scale = (r[0] or "").strip() or (r[5] or "").strip()
                if scale:
                    if (prev[0] or "").strip():
                        prev[0] = (prev[0] + scale).strip()
                    else:
                        prev[5] = (prev[5] + scale).strip()
                for i in r_vals:
                    prev[i] = r[i]
                continue
        merged.append(r)
    return [r for r in merged if any(c.strip() for c in r)]


def r29_t8(t, ctx):
    """表3-6 浓香型习酒量比关系: 两栏, 右栏名称被并进左栏名称格."""
    out, n = [], 10
    hdr = ["类别", "原酒", "习酒", "酱香", "醇甜", "类别", "原酒", "习酒", "酱香", "醇甜"]
    for i, r in enumerate(t["rows"]):
        raw = str(r[0]).strip() if r else ""
        tail_r = [str(x).strip() for x in (r[1:3] if len(r) > 2 else [])]
        ln, rn, lv, rv = classify_interleaved(raw, 4)
        # the right panel's last two values often land in their own cells
        if len(rv) < 4 and tail_r:
            rv = rv + [v for v in tail_r if v][:4 - len(rv)]
        if ln and len(lv) == 4 and not rn and len(rv) >= 2:
            out.append([ln] + lv + [""] * 5)                 # right panel absent
        elif ln and len(lv) == 4 and rn and len(rv) >= 2:
            out.append([ln] + lv + [rn] + (rv + [""] * 4)[:4])
        elif not ln and not rn and len(lv) + len(rv) >= 6:
            ctx.warn(t, i, "两栏名称都缺失，只剩数值，未拆分")
            out.append([""] * 10)
        elif ln and not lv and not rn:
            ctx.warn(t, i, "只有名称无数值(跨行折行): %r" % ln[:30])
            out.append([ln] + [""] * 9)
        else:
            ctx.warn(t, i, "形状不符(左%s个/右%s个数值)，原样保留: %r"
                     % (len(lv), len(rv), raw[:40]))
            out.append(list(r) + [""] * (n - len(r)))
    ctx.note("右栏(第6-10列)从左栏名称格中拆出")
    return {"rows": _pad(out, n), "header": hdr, "ncol": n}


def r31_t0(t, ctx):
    """洋河绵柔型: 化合物中文名与英文名被粘在一起, 并吞掉前两个样品列."""
    out, n = [], 7
    hdr = ["化合物", "Compound", "41.6% HZL", "41% TZL", "46% TZL",
           "52% TZL", "42.6% MZL"]
    # The cell is 中文名 + 英文名 + 两个样品值, all glued. Work on the raw token list:
    # leading CJK is the Chinese name, the next Latin run is the English name, and every
    # numeric token after it is a sample value. classify() is deliberately not used here -
    # it merges the Latin run into the text run and the two names stop being separable.
    for i, r in enumerate(t["rows"]):
        raw = norm(str(r[2]).strip()) if len(r) > 2 else ""
        rest = [str(x).strip() for x in (r[3:6] if len(r) > 5 else [])]
        # The OCR prints the two names with no space at all ("乙酸乙酯ethyl acetate*"),
        # so whitespace cannot be the boundary. The first Latin letter is.
        m = re.match(r"^(?P<cn>[^A-Za-z]*?)(?P<en>[A-Za-z].*)$", raw)
        cn, tail = (m.group("cn").strip(), m.group("en")) if m else ("", raw)
        en_parts, vals = [], []
        for tk in tail.split():
            if is_num(tk) or RANGE_RE.match(tk):
                vals.append(tk)
            elif vals:
                vals[-1] += tk              # trailing prose: keep with the value
            else:
                en_parts.append(tk)
        en = " ".join(en_parts).strip()
        # a summary row (酯类总含量) has no English name and is not a compound
        if cn and en and len(vals) == 2 and len(rest) == 3:
            out.append([cn, en] + vals + rest)
        elif not raw:
            out.append(list(r) + [""] * (n - len(r)))
        else:
            ctx.warn(t, i, "形状不符(中文=%r 英文=%r 数值%d个)，原样保留"
                     % (cn[:12], en[:20], len(vals)))
            out.append(list(r) + [""] * (n - len(r)))
    ctx.note("中文名/英文名分开, 前两个样品列归位")
    return {"rows": _pad(out, n), "header": hdr, "ncol": n}


# Which table to repair, keyed by a substring of its CAPTION - not by its index in the
# list.
#
# Indexes are not stable across runs: r29_t6 replaces one table with two, which shifts
# every later index by one, so a plan keyed on 29 -> 8 silently moved from 表3-6 onto
# 表3-5 and wrote 表3-6's class-ratio header across a table of OAV values. The rows still
# looked plausible, the repair reported success, and nothing failed loudly. A caption is
# printed on the page and does not move.
PLAN = {
    21: [("表3-4 准确度实验", r21_t9, ("21", "表3-4")),
         ("微波消解程序", r21_t2, ("21", "微波消解"))],
    25: [("不同品牌酒样中风味物质含量", r25_t1, ("25", "品牌"))],
    28: [("", r28_t0, ("28", "表2"))],          # caption empty; falls back to index 0
    29: [("表1-2", r29_t0, ("29", "表1-2")),
         ("表3-6", r29_t8_textlayer, ("29", "表3-6"))],
    31: [("", r31_t0, ("31", "表1"))],
}


def _capnorm(s):
    """Caption compare with whitespace removed: the paper prints '表 3-6' but the table
    list sometimes carries '表3-6', and a mismatch here used to skip the entry silently."""
    return re.sub(r"\s+", "", str(s or ""))


def resolve_plan(idx, d):
    """
    Pair each PLAN entry with the table it names, and refuse to guess.

    Returns [(caption_match, index_or_None, handler, header_key)]. A caption that matches
    more than one table, or none at all, is reported and skipped: acting on the wrong table
    is worse than leaving it alone, and the report says which entry was meant.
    """
    found = []
    for cap_sub, fn, hkey in PLAN.get(idx, []):
        if not cap_sub:
            found.append(("", 0, fn, hkey))       # uncaptioned table: index 0
            continue
        want = _capnorm(cap_sub)
        hits = [i for i, t in enumerate(d["tables"])
                if want and want in _capnorm(t.get("caption"))]
        if len(hits) == 1:
            found.append((cap_sub, hits[0], fn, hkey))
        else:
            # None: the entry named a table that is not there. Reported, never guessed.
            found.append((cap_sub, None, fn, hkey))
    return found

# Grand-total and summary rows. Not compounds, so a run of numbers inside one cell is
# what the paper prints; they are excluded from the "still merged?" test.
SUMMARY_CELLS = {
    31: ("酯类总含量", "总含量", "合计", "总计", "总量"),
}

# The canonical repaired header per table, applied on every run including the
# "already repaired" path. Kept out of the handlers so a header can be corrected after the
# rows have been split, without the idempotence guard refusing to touch it.
#
# "保留指数" rather than the printed full-width "ＲＩ": build_rec整理.py's RI_RE matches
# 数[ＲR][ＩI] but not a bare ＲＩ on its own, so a full-width RI label falls through to the
# data columns and the workbook grows a 浓度 column reading "<700".
HEADERS = {
    ("21", "表3-4"): ["风味物质", "本底浓度（mg/L）", "添加浓度（mg/L）",
                      "加标测定（mg/L）", "回收率"],
    ("21", "微波消解"): ["最大功率/W", "升温时间/min", "温度/℃", "保持时间/min"],
    ("25", "品牌"): ["风味物质", "保留指数", "WLY", "YH", "JSY", "YJGJ", "SXTB", "LZLG"],
    ("28", "表2"): ["风味物质", "精密度 含量", "精密度 相对保留时间", "稳定性 含量",
                   "稳定性 相对保留时间", "重复性 含量", "重复性 相对保留时间"],
    ("29", "表1-2"): ["序号", "组分名", "习酒·窖藏1988", "茅台酒",
                      "序号", "组分名", "习酒·窖藏1988", "茅台酒"],
    ("29", "表3-6"): ["类别", "原酒", "习酒", "酱香", "醇甜",
                      "类别", "原酒", "习酒", "酱香", "醇甜"],
    ("31", "表1"): ["化合物", "Compound", "41.6% HZL", "41% TZL", "46% TZL",
                    "52% TZL", "42.6% MZL"],
}

# tables that stay merged on purpose, with the reason
SKIP = {
    (22, 2): "感官品评/PCA 得分表，非化合物表；合并格是若干个样本分数，分列无定义",
    (22, 3): "同上（综合指标值矩阵）",
}


RI_LEAD = re.compile(r"^(?P<ri>[＜<]\s*\d+|\d{2,4})\s+(?P<nm>\S.*)$")


def _ri_glued(t):
    """band_25 only: a retention index still sitting on the front of the name.

    This is a different defect from the merged 名称+数值+数值 rows - one number, not two -
    so the generic MERGED test does not see it, and without its own test the idempotence
    guard would declare the table finished and never run the fix.
    """
    for row in t.get("rows") or []:
        first = str(row[0]).strip() if row else ""
        if first and RI_LEAD.match(norm(first)):
            return True
    return False


# Tables that need work for a reason MERGED cannot see.
EXTRA_NEEDS = {(25, 1): _ri_glued}

# Tables whose CONTENT is rebuilt from the PDF text layer rather than repaired from the grid.
# They are re-done on every run, because the idempotence test cannot see what is wrong with
# them: they are not merged, they are incomplete.
FORCE_REBUILD = {("29", "表3-6")}


def _already_split(t, skip_names=()):
    """
    True when no cell in this table still holds the merged 名称+数值+数值 shape.

    skip_names lists cells that are summary rows rather than data rows ("酯类总含量",
    the grand total at the foot of a table). Those legitimately keep a run of numbers in
    one cell - they are a total, not a compound row - so they must not keep the table
    looking unrepaired.
    """
    for row in t.get("rows") or []:
        for cell in row:
            s = str(cell or "").strip()
            if not s:
                continue
            if any(k in s for k in skip_names):
                continue
            if MERGED.match(norm(s)):
                return False
    return True


def _reset_header(t, hdr, keep_caption_rows=True):
    """
    Replace header_rows with the repaired one-row header, at the new width.

    This is not cosmetic. build_rec整理.py reads header_rows - not `header` - to label the
    columns of the 基础数据 block, so leaving the old rows in place keeps them in charge:

      - the stale rows are still the OLD width, so every column past the new layout's
        start is read at the wrong offset;
      - worse, for band_29 表1-2 the stale header held 序号 in column 0 and nothing in
        column 4, so the right panel's serial numbers were classified as concentration and
        the workbook grew a 浓度 column reading "l8", "19", "20";
      - the OCR had also swept a dozen lines of body prose ("的香气成分进行定性研究...")
        into header_rows, which is why those columns were titled from fragments of a
        sentence.

    Every displaced row is kept verbatim under caption_rows so nothing the extractor read
    is thrown away by this pass.
    """
    old = list(t.get("header_rows") or [])
    t["header"] = list(hdr)
    t["header_rows"] = [list(hdr)]
    if keep_caption_rows and old:
        t["caption_rows"] = old
    return len(old)


class Ctx:

    def __init__(self):
        self.warnings = []
        self.notes = []

    def warn(self, t, i, msg):
        self.warnings.append((i, msg))

    def note(self, msg):
        self.notes.append(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    report = []
    changed = 0

    for idx in sorted(PLAN):
        path = os.path.join(REOUT, "band_%02d.json" % idx)
        orig = os.path.join(REOUT, "band_%02d.orig.json" % idx)
        d = json.load(open(path, encoding="utf-8"))
        backup = os.path.exists(orig)
        if not backup and not a.dry_run:
            shutil.copy2(path, orig)

        report.append("=" * 74)
        report.append("band_%02d.json   %s" % (idx, d.get("sheet", "")))
        # Tables are located by caption, never by index. See PLAN.
        targets = resolve_plan(idx, d)
        for cap_sub, ti, fn, hkey in targets:
            if ti is None:
                report.append("  !! 标题 %r 在 band_%02d 里匹配到 %d 张表，跳过（不猜）"
                              % (cap_sub, idx,
                                 sum(1 for t in d["tables"]
                                     if _capnorm(cap_sub) in _capnorm(t.get("caption")))))
                continue
            t = d["tables"][ti]
            ctx = Ctx()
            report.append("  t%-3d  %s" % (ti, cap_sub or "(无标题,按索引0)"))
            before = t.get("n_col")

            # Idempotence. Re-running on an already-repaired table must not re-split it:
            # the rows no longer hold "名称 数值 数值", so the handlers would take the
            # "形状不符" path and blank the values out. A table counts as repaired when its
            # rows are already at the target width and no cell still has the merged
            # shape, so only the header fix is applied.
            extra = EXTRA_NEEDS.get((idx, ti))
            done = _already_split(t, skip_names=SUMMARY_CELLS.get(idx, ()))
            if extra is not None:
                done = done and not extra(t)
            if hkey in FORCE_REBUILD:
                # These are rebuilt from the text layer rather than repaired from the grid,
                # so "the rows are no longer merged" says nothing about whether they are
                # RIGHT. 表3-6 passes the idempotence test while still missing a row and
                # holding two printed tables in one.
                done = False
            if done:
                hdr = HEADERS.get(hkey) or t.get("header")
                if hdr:
                    _reset_header(t, hdr)
                report.append("        已修复过(%d 列)，仅重写表头" % (t["n_col"],))
                continue

            res = fn(t, ctx)
            if "split" in res:
                new_tables = []
                for cap, rows, hdr in res["split"]:
                    nt = dict(t)
                    nt["caption"] = cap
                    nt["rows"] = _pad(rows, 10)
                    nt["header"] = hdr
                    nt["n_col"] = 10
                    nt["roles"] = ["name_cn"] + [None] * 9
                    nt["units"] = [""] * 10
                    _reset_header(nt, hdr, keep_caption_rows=True)
                    new_tables.append(nt)
                d["tables"][ti:ti + 1] = new_tables
                # A rebuild runs on every pass, so the tables it emitted last time are
                # still in the list. Without this they are stacked again: 表3-6, 表3-7,
                # 表3-7, ... one duplicate per run.
                wanted = [_capnorm(c) for c, _r, _h in res["split"]]
                new_end = ti + len(new_tables)          # the block just inserted
                d["tables"] = [t2 for j, t2 in enumerate(d["tables"])
                               if j < new_end
                               or _capnorm(t2.get("caption")) not in wanted]
                t["n_col"] = 10
                report.append("        %d 列 -> 拆成 2 张表，各 10 列" % before)
            else:
                t["rows"] = res["rows"]
                t["n_col"] = res["ncol"]
                if res.get("header"):
                    t["header"] = res["header"]
                t["roles"] = None
                t["units"] = [""] * res["ncol"]
                if res.get("header"):
                    _reset_header(t, res["header"])
                report.append("        %s 列 -> %s 列" % (before, res["ncol"]))
            changed += 1
            if ctx.notes:
                for nt in ctx.notes:
                    report.append("        %s" % nt)
            for i, msg in ctx.warnings:
                report.append("        行%-4d 未拆分：%s" % (i, msg))
            if not ctx.warnings:
                report.append("        全部行形状符合，无残留")

        if not a.dry_run:
            json.dump(d, open(path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            report.append("  -> %s%s" % (os.path.basename(path),
                                        "" if backup else "   (原文件已备份为 .orig.json)"))

    report.insert(0, "band 拆列修复报告%s\n修复表数: %d%s"
                  % ("  [DRY RUN 未写入]" if a.dry_run else "", changed,
                     "" if a.dry_run else ""))
    txt = "\n".join(report)
    print(txt)
    outp = os.path.join(REOUT, "repair_report.txt")
    if not a.dry_run:
        open(outp, "w", encoding="utf-8").write(txt)
        print("\n-> %s" % outp)


if __name__ == "__main__":
    main()
