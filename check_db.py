# -*- coding: utf-8 -*-
"""抽查 浓香型数据库.xlsx (修正版:用CAS精确抽查)"""
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
OUT = BASE + r"\浓香型数据库.xlsx"
CHK = BASE + r"\check_db.txt"

df = pd.read_excel(OUT, sheet_name="all data")
docs = pd.read_excel(OUT, sheet_name="文献索引")
units = pd.read_excel(OUT, sheet_name="单位待确认")
qual = pd.read_excel(OUT, sheet_name="数据质量")

data_cols = [c for c in df.columns if c not in
             ["Order ID","CAS","Odorants","中文名称","SMILES","Threshold（μg/L）"]]

with open(CHK, "w", encoding="utf-8") as f:
    f.write(f"all data 形状: {df.shape}\n")
    f.write(f"列名(前14): {list(df.columns[:14])}\n\n")

    f.write("### 填充率 ###\n")
    fill = df.notna().sum(); total = len(df)
    for c in ["CAS","Odorants","中文名称","SMILES","Threshold（μg/L）"]:
        f.write(f"  {c}: {fill.get(c,0)}/{total}\n")
    f.write("\n")

    f.write("### 数据质量(按文献) ###\n")
    f.write(qual.to_string(index=False) + "\n\n")

    # 精确抽查 ethyl hexanoate CAS 123-66-0
    f.write("### 抽查 ethyl hexanoate (CAS 123-66-0) ###\n")
    rr = df[df["CAS"].astype(str) == "123-66-0"]
    if len(rr):
        rr = rr.iloc[0]
        f.write(f"  Odorants={rr['Odorants']} | 中文={rr['中文名称']} | SMILES={rr['SMILES']} | Thr={rr['Threshold（μg/L）']}\n")
        nz = {c: rr[c] for c in data_cols if pd.notna(rr[c]) and rr[c] != ""}
        f.write(f"  非空数据列数: {len(nz)}\n")
        for c, v in list(nz.items())[:30]:
            f.write(f"     {c} = {v}\n")
    else:
        f.write("  未找到 CAS=123-66-0\n")
    f.write("\n")

    # 抽查 3年陈 / 5年陈 是否找回来
    f.write("### 抽查 '3 年陈' / '5 年陈' 列是否存在及有数据 ###\n")
    for c in data_cols:
        if "年陈" in c:
            f.write(f"  列 {c}: 非空 {df[c].notna().sum()}\n")
    f.write("\n")

    # 列出所有含中文物种名的样品列(品牌/酒样)
    f.write("### 含中文的样品列(品牌/酒样)示例 ###\n")
    zh_cols = [c for c in data_cols if any('\u4e00'<=ch<='\u9fff' for ch in c)]
    for c in zh_cols[:40]:
        f.write(f"  [{df[c].notna().sum():3d}] {c}\n")
    f.write(f"  ... 共 {len(zh_cols)} 个中文样品列\n")

print("DONE -> check_db.txt")
