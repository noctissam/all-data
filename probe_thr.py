# -*- coding: utf-8 -*-
"""探查 阈值.xlsx 结构(所有sheet + '周'sheet详情) -> probe_thr.txt"""
import pandas as pd
BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26.10\英文"
P = BASE + r"\阈值.xlsx"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

xl = pd.ExcelFile(P)
w("sheets: %s" % xl.sheet_names)
for s in xl.sheet_names:
    sh = pd.read_excel(P, sheet_name=s, header=None)
    w("")
    w("== %s 形状=%s ==" % (s, sh.shape))
    w(sh.head(8).to_string())

# 详情: 第二个sheet '周'
name = xl.sheet_names[1] if len(xl.sheet_names) > 1 else None
if name:
    sh = pd.read_excel(P, sheet_name=name)
    w("")
    w("== '周' 列名: %s ==" % list(sh.columns))
    w("行数=%d" % len(sh))
    w(sh.head(30).to_string())
    w("...")
    w(sh.tail(10).to_string())

with open(r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月\probe_thr.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE")
