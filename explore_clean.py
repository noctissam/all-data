# -*- coding: utf-8 -*-
"""探索 清洗后数据.xlsx 的取值分布"""
import pandas as pd
from collections import Counter

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
df = pd.read_excel(BASE + r"\清洗后数据.xlsx", sheet_name="清洗后数据")

OUT = BASE + r"\explore_clean.txt"
with open(OUT, "w", encoding="utf-8") as f:
    f.write(f"形状: {df.shape}\n")
    f.write(f"列名: {list(df.columns)}\n\n")

    f.write("### 数据类型 分布 ###\n")
    f.write(str(df["数据类型"].value_counts(dropna=False)) + "\n\n")

    f.write("### 文献名 分布 (unique=%d) ###\n" % df["文献名"].nunique())
    for k, v in df["文献名"].value_counts(dropna=False).items():
        f.write(f"  [{v:6d}] {k}\n")
    f.write("\n")

    f.write("### 样品 分布 (unique=%d) ###\n" % df["样品"].nunique())
    for k, v in df["样品"].value_counts(dropna=False).items():
        f.write(f"  [{v:6d}] {k}\n")
    f.write("\n")

    f.write("### 化合物 unique count: %d ###\n" % df["化合物"].nunique())
    f.write("### CAS号 unique count: %d ###\n\n" % df["CAS号"].nunique())

    f.write("### 前30个化合物 ###\n")
    for k, v in df["化合物"].value_counts().head(30).items():
        f.write(f"  [{v:6d}] {k}\n")
    f.write("\n")

    f.write("### 数值 列类型样本(前30) ###\n")
    for v in df["数值"].head(30).tolist():
        f.write(f"  {v!r}\n")
    f.write("\n")

    # 每个 数据类型 × 样品 的交叉表
    f.write("### 数据类型 × 样品 交叉 (前若干) ###\n")
    ct = pd.crosstab(df["数据类型"], df["样品"])
    f.write(str(ct) + "\n\n")

    f.write("### 每个文献的 数据类型 汇总 ###\n")
    for lit, g in df.groupby("文献名"):
        dts = g["数据类型"].value_counts().to_dict()
        f.write(f"  {lit}: {dts}\n")

print("DONE -> explore_clean.txt")
