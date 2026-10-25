# -*- coding: utf-8 -*-
"""统计 浓香型数据库.xlsx 中非0化合物数据 -> stats_nonzero.txt"""
import math
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
OUT = BASE + r"\浓香型数据库.xlsx"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

df = pd.read_excel(OUT, sheet_name="all data")
idx = pd.read_excel(OUT, sheet_name="文献索引与单位")
base_cols = ["Order ID","CAS","Odorants","中文名称","SMILES","Threshold（μg/L）"]
data_cols = [c for c in df.columns if c not in base_cols]
conc_cols = [c for c in data_cols if c.endswith("(μg/L)")]
oav_cols  = [c for c in data_cols if c.endswith("OAV")]

def nz(col):
    """非空且数值!=0 的个数"""
    s = pd.to_numeric(df[col], errors="coerce")
    return int(((s.notna()) & (s != 0)).sum())

w("== 总览 ==")
w("化合物行数: %d" % len(df))
w("数据列: %d (浓度列=%d, OAV列=%d)" % (len(data_cols), len(conc_cols), len(oav_cols)))

has_conc = df[conc_cols].apply(pd.to_numeric, errors="coerce").fillna(0).ne(0).any(axis=1)
has_oav  = df[oav_cols].apply(pd.to_numeric, errors="coerce").fillna(0).ne(0).any(axis=1)
has_any  = has_conc | has_oav
w("至少有1个非0浓度值的化合物: %d (%.1f%%)" % (has_conc.sum(), 100*has_conc.mean()))
w("至少有1个非0 OAV值的化合物: %d (%.1f%%)" % (has_oav.sum(), 100*has_oav.mean()))
w("任一非0数据的化合物: %d (%.1f%%)" % (has_any.sum(), 100*has_any.mean()))
w("全0/全空化合物: %d" % (~has_any).sum())
thr = pd.to_numeric(df["Threshold（μg/L）"], errors="coerce")
w("有阈值的化合物: %d" % int(thr.notna().sum()))
w("有SMILES的化合物: %d" % int(df["SMILES"].astype(str).str.strip().ne("").sum() - int(df["SMILES"].isna().sum())))

w("")
w("== 按文献(浓度列非0化合物数 / OAV列) ==")
grp = {}
for c in data_cols:
    dno = c.split(" ")[0]
    g = grp.setdefault(dno, {"conc": [], "oav": []})
    if c.endswith("OAV"): g["oav"].append((c, nz(c)))
    else: g["conc"].append((c, nz(c)))
for dno in sorted(grp, key=lambda x: int(x)):
    g = grp[dno]
    cs = sum(v for _, v in g["conc"]); os_ = sum(v for _, v in g["oav"])
    cmax = max((v for _, v in g["conc"]), default=0)
    w("  #%-2s 浓度列=%2d列 非0计数合计=%5d 单列最大=%4d | OAV列=%2d列 合计=%4d"
      % (dno, len(g["conc"]), cs, cmax, len(g["oav"]), os_))

w("")
w("== 各列非0计数明细 (浓度列) ==")
rows = []
for c in conc_cols:
    rows.append((c, nz(c)))
rows.sort(key=lambda x: -x[1])
for c, n in rows:
    w("  %-40s %d" % (c, n))

w("")
w("== 各列非0计数明细 (OAV列) ==")
rows = [(c, nz(c)) for c in oav_cols]
rows.sort(key=lambda x: -x[1])
for c, n in rows:
    w("  %-40s %d" % (c, n))

w("")
w("== 热门非0化合物 TOP25 (非0列数) ==")
cnt = df[data_cols].apply(pd.to_numeric, errors="coerce").fillna(0).ne(0).sum(axis=1)
top = df.assign(_c=cnt).sort_values("_c", ascending=False).head(25)
for _, r in top.iterrows():
    w("  %-40s 中文=%-16s 非0列数=%d/%d" % (
        str(r["Odorants"])[:40], str(r["中文名称"])[:16], int(r["_c"]), len(data_cols)))

w("")
w("== 每个化合物的非0列数分布 ==")
dist = cnt.value_counts().sort_index()
for k, v in dist.items():
    w("  %3d列有值: %d个化合物" % (k, v))

with open(BASE + r"\stats_nonzero.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE -> stats_nonzero.txt")
