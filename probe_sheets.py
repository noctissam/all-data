# -*- coding: utf-8 -*-
"""probe_sheets: data总库分表名全列表 + D12对应分表结构 -> probe_sheets.txt"""
import re
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

xl = pd.ExcelFile(BASE + r"\data总库.xlsx")
w("== 全部分表名 ==")
for s in xl.sheet_names:
    w("  %r" % s)

# 找D12/D24/D11分表
pats = {"D12":"GC", "D24":"洋河", "D11":"四川", "D3":"Decoding"}
for k, p in pats.items():
    hits=[s for s in xl.sheet_names if p in s]
    w("")
    w("== %s 命中: %s ==" % (k, hits))
    for s in hits:
        sh=pd.read_excel(BASE + r"\data总库.xlsx", sheet_name=s)
        sh.columns=[str(c).strip() for c in sh.columns]
        w("  [%s] 列: %s" % (s, list(sh.columns)))
        nc=[c for c in sh.columns if re.search(r"compound|化合物|odorant",c,re.I)]
        if nc:
            m=sh[sh[nc[0]].astype(str).str.contains("exanoate|己酸乙酯|cetate|乙酸乙酯",na=False,regex=True)]
            for _,r in m.head(6).iterrows():
                w("    %s -> %s" % (r[nc[0]], {c:r[c] for c in sh.columns if c!=nc[0] and pd.notna(r[c])}))

with open(BASE + r"\probe_sheets.txt","w",encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE")
