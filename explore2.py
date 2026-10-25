# -*- coding: utf-8 -*-
"""针对性探查:数值可解析性、每个文献的样品、化合物中英分布"""
import pandas as pd
import re

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
df = pd.read_excel(BASE + r"\清洗后数据.xlsx", sheet_name="清洗后数据")
OUT = BASE + r"\explore2.txt"

def is_num(x):
    if pd.isna(x):
        return False
    s = str(x).strip().replace(",", "")
    return bool(re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s))

with open(OUT, "w", encoding="utf-8") as f:
    # 1. 数值可解析性
    f.write("### 数值 可解析为纯数字占比 ###\n")
    ok = df["数值"].apply(is_num)
    f.write(f"  可解析: {ok.sum()} / {len(df)}  ({ok.mean()*100:.1f}%)\n")
    f.write(f"  不可解析示例(前40个 unique):\n")
    bad = df.loc[~ok, "数值"].astype(str).unique()[:40]
    for b in bad:
        f.write(f"    {b!r}\n")
    f.write("\n")

    # 2. CAS 可用性
    f.write("### CAS号 缺失/可用 ###\n")
    f.write(f"  非空: {df['CAS号'].notna().sum()} / {len(df)}\n")
    f.write(f"  unique非空: {df['CAS号'].dropna().nunique()}\n")
    f.write(f"  CAS缺失时的化合物名示例(前30):\n")
    for n in df.loc[df["CAS号"].isna(), "化合物"].astype(str).unique()[:30]:
        f.write(f"    {n}\n")
    f.write("\n")

    # 3. 化合物名 语言分布
    f.write("### 化合物名 语言分布 ###\n")
    def lang(s):
        s = str(s)
        if re.search(r"[一-鿿]", s):
            return "含中文"
        return "纯英文/数字"
    f.write(str(df["化合物"].apply(lang).value_counts()) + "\n")
    f.write("  纯英文名示例(前20):\n")
    eng = df.loc[~df["化合物"].astype(str).str.contains(r"[一-鿿]"), "化合物"].unique()[:20]
    for n in eng:
        f.write(f"    {n}\n")
    f.write("\n")

    # 4. 每个文献的样品清单
    f.write("### 每个文献 -> 样品清单(去掉明显垃圾前) ###\n")
    for lit, g in df.groupby("文献名", sort=False):
        samples = g["样品"].astype(str).unique().tolist()
        f.write(f"\n  【{lit}】 样品数={len(samples)}\n")
        f.write(f"    {samples}\n")

print("DONE -> explore2.txt")
