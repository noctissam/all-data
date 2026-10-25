# -*- coding: utf-8 -*-
"""侦察: data总库分表清单 / PDF库 / D23、D25原始样品名 / SMILES阈值覆盖"""
import importlib, sys
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"

print("== 1) data总库 sheet清单 ==")
x = pd.ExcelFile(BASE + r"\data总库.xlsx")
for s in x.sheet_names:
    print("  ", repr(s))

print("== 2) PDF文本库 ==")
for m in ["pypdf", "fitz", "pdfplumber", "PyPDF2"]:
    try:
        importlib.import_module(m); print("   OK", m)
    except Exception:
        print("   NO", m)

src = pd.read_excel(BASE + r"\清洗后数据.xlsx", sheet_name="清洗后数据")
D23 = "酱香型和浓香型白酒中香气物质及其差异研究"
D25 = "浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究"

print("== 3) D23 原始样品名(计数) ==")
s23 = src[src["文献名"] == D23]["样品"].astype(str).value_counts()
for k, v in s23.items():
    print("   %-30s %d" % (k, v))

print("== 4) D25 原始样品名(计数) ==")
s25 = src[src["文献名"] == D25]["样品"].astype(str).value_counts()
for k, v in s25.items():
    print("   %-40s %d" % (k, v))

print("== 5) D25 数据类型分布 ==")
print(src[src["文献名"] == D25]["数据类型"].value_counts().to_dict())

print("== 6) D25 化合物行数(去重) ==")
d25 = src[src["文献名"] == D25]
print("   rows=", len(d25), " uniq compounds=", d25["化合物"].nunique())
