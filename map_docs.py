# -*- coding: utf-8 -*-
"""建立 文献映射 + 单位定标参照
1) 解析 data总库 'all data' 表头 -> 文献编号 -> [(样品,单位)]
2) 解析 data总库 每个分表 -> 表名/表头/单位/化合物数
3) 清洗后数据 -> 每篇文献的(清洗后样品, 原始样品线索)
"""
import re
import pandas as pd
import openpyxl

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
REF = BASE + r"\data总库.xlsx"
SRC = BASE + r"\清洗后数据.xlsx"
OUT = BASE + r"\map_docs.txt"

def clean_sample(s):
    # 复用与 build_db 相同的清洗逻辑(精简版, 用于比对)
    if s is None:
        return None
    t = str(s).strip()
    if t == "" or t.lower() == "nan":
        return None
    junk = re.compile(
        r"^(nan|nd|n\.d\.?|—|--|－|/|-|<1|>100|>10|>1)$"
        r"|^[\d\.\s±<>±]+$"
        r"|浓度|含量|量比|平均|序号|No\.?|Category|ion|p值|SD|OAV值?|配度|加标|添加|重复性|稳定性"
        r"|\(I%\)|乙醛脱氢酶"
        r"|^esters?$|^alcohols?$|^acids?$|^aldehydes?$|^ketones?$|^phenols?$|^others?$|^totals?$"
        r"|^酯类$|^醇类$|^酸类$|^醛类$|^酮类$|^酚类$|^其他$|^总计$"
        r"|mg\s*/?\s*l|μg\s*/?\s*l|g\s*/?\s*l|mg·l|μg·l|g·l|mg/L|μg/L|g/L",
        re.IGNORECASE)
    if junk.search(t):
        return None
    t2 = re.sub(r"(?<=[A-Z0-9])[a-z]{1,2}$", "", t).strip()
    if t2 == "" or re.fullmatch(r"[\d\.]+", t2):
        return None
    return t2

with open(OUT, "w", encoding="utf-8") as f:
    # ---------- 1) data总库 'all data' 表头 ----------
    f.write("="*90 + "\n### data总库 'all data' 表头解析 -> 文献组 ###\n")
    hdr = pd.read_excel(REF, sheet_name="all data", nrows=0).columns.tolist()
    # 跳过前6个信息列
    info_cols = 6
    groups = {}   # doc_no -> [(colname, sample, unit)]
    cur = None
    for c in hdr[info_cols:]:
        c = str(c)
        m = re.match(r"^\s*(\d+)\s+(.*)$", c)
        if m:
            cur = int(m.group(1))
            rest = m.group(2)
        else:
            rest = c
        # 从 rest 提取单位
        um = re.search(r"\((μg/L|mg/L|g/L|μg/l|mg/l|g/l|mg·L⁻¹|g/L)\)\s*$|(\bmg/L\b|μg/L|g/L)\s*$|(mg/L|μg/L|g/L)", rest)
        unit = ""
        if um:
            unit = next(g for g in um.groups() if g)
            rest2 = re.sub(r"[\(（]\s*(?:μg/L|mg/L|g/L|μg/l|mg/l|g/l)\s*[\)）]", "", rest).strip()
            rest2 = re.sub(r"\s*(?:μg/L|mg/L|g/L)\s*$", "", rest2).strip()
        else:
            rest2 = rest.strip()
        if cur is None:
            continue
        groups.setdefault(cur, []).append((c, rest2, unit))
    for dn in sorted(groups):
        samples = [s for (_, s, _) in groups[dn]]
        units = set(u for (_, _, u) in groups[dn] if u)
        f.write(f"\n  文献{dn}: 样品={samples}  单位线索={sorted(units)}\n")

    # ---------- 2) data总库 分表 ----------
    f.write("\n" + "="*90 + "\n### data总库 分表结构 ###\n")
    wb = openpyxl.load_workbook(REF, read_only=True, data_only=True)
    for ws in wb.worksheets:
        if ws.title == "all data":
            continue
        f.write(f"\n--- {ws.title!r} (rows={ws.max_row}, cols={ws.max_column}) ---\n")
        rows = list(ws.iter_rows(min_row=1, max_row=2, values_only=True))
        for i, r in enumerate(rows, 1):
            cells = [str(x)[:28] if x is not None else "" for x in r]
            f.write(f"   R{i}: {cells}\n")
    wb.close()

    # ---------- 3) 清洗后数据 每篇文献样品 ----------
    f.write("\n" + "="*90 + "\n### 清洗后数据 每篇文献 -> (原始样品, 清洗后样品) ###\n")
    df = pd.read_excel(SRC, sheet_name="清洗后数据")
    for i, (lit, g) in enumerate(df.groupby("文献名", sort=False), 1):
        raw = g["样品"].astype(str).unique().tolist()
        cleaned = []
        for s in raw:
            cs = clean_sample(s)
            if cs and cs not in cleaned:
                cleaned.append(cs)
        f.write(f"\n  [{i}] {lit}\n")
        f.write(f"      清洗后样品({len(cleaned)}): {cleaned}\n")

print("DONE -> map_docs.txt")
