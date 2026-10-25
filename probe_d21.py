# -*- coding: utf-8 -*-
"""probe_d21: D21清洗数据的类型/样品分布 -> probe_d21.txt"""
import pandas as pd
BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
src = pd.read_excel(BASE + r"\清洗后数据.xlsx", sheet_name="清洗后数据")
D21 = "浓香型白酒基酒挥发性成分分析及等级识别研究"
g = src[src["文献名"] == D21]
L = []
L.append("总行数: %d" % len(g))
L.append("类型: %s" % g["数据类型"].value_counts().to_dict())
L.append("样品分布: %s" % g["样品"].astype(str).value_counts().to_dict())
oav = g[g["数据类型"] == "OAV"]
L.append("OAV行数: %d" % len(oav))
if len(oav):
    L.append("OAV样品: %s" % oav["样品"].astype(str).value_counts().to_dict())
    L.append(oav.head(15)[["化合物","样品","数值"]].to_string())
with open(BASE + r"\probe_d21.txt","w",encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE")
