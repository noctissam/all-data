# -*- coding: utf-8 -*-
"""PCA结果解读: 各文献PC均值、PC1与总量相关性、文献层面聚类分组"""
import numpy as np, pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
base = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
f = base + r"\PCA聚类分析\PCA_聚类分析结果.xlsx"
sc = pd.read_excel(f, sheet_name="PCA得分")
raw = pd.read_excel(base + r"\可用化合物原始数据.xlsx", sheet_name="all data")
conc = [c for c in raw.columns if c.endswith("(μg/L)")]
X = raw[conc].apply(pd.to_numeric, errors="coerce").fillna(0)
tot = X.sum(axis=0)

g = sc.groupby("文献")[["PC1", "PC2"]].mean().round(2)
g["样品数"] = sc.groupby("文献").size()
g["中位总浓度μg/L"] = [float(np.median(tot.iloc[[i for i, c in enumerate(conc)
                     if c.split("  ")[0] == d[1:]]])) for d in g.index]
g = g.sort_values("PC1")
print("== 各文献 PC 均值 (按PC1升序) ==")
print(g.to_string())
from scipy.stats import pearsonr
r, p = pearsonr(sc["PC1"], np.log10(tot.values + 1))
print()
print("PC1 ~ log10(总浓度) 相关: r = %.3f, p = %.2e" % (r, p))
# 文献层面聚类(k=3)
D = sc.groupby("文献")[["PC1", "PC2", "PC3"]].mean()
Z = (D - D.mean()) / D.std(ddof=0)
cl = fcluster(linkage(Z.values, "ward"), 3, criterion="maxclust")
print()
print("== 文献层面聚类 k=3 ==")
for k in sorted(set(cl)):
    print("  簇%d: %s" % (k, ", ".join(D.index[cl == k])))
