# -*- coding: utf-8 -*-
"""41个可用化合物 x 113样品: PCA + 聚类热图
输入: 可用化合物原始数据.xlsx / all data (浓度 μg/L)
预处理: 缺失(未检出)=0 -> log10(1+x) -> 按化合物z-score
输出: PCA聚类分析/ 下的图 + PCA_聚类分析结果.xlsx + PCA聚类分析.txt
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm
import seaborn as sns
from sklearn.decomposition import PCA
from scipy.cluster.hierarchy import linkage, dendrogram

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
SRC = BASE + r"\可用化合物原始数据.xlsx"
OUTD = BASE + r"\PCA聚类分析"
os.makedirs(OUTD, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
L = []
def w(*a):
    s = " ".join(str(x) for x in a); L.append(s); print(s)

df = pd.read_excel(SRC, sheet_name="all data")
conc = [c for c in df.columns if c.endswith("(μg/L)")]
def cname(r):
    z = str(r["中文名称"])
    if z in ("nan", "None", ""): z = str(r["Odorants"])
    return z
comp = [cname(r) for _, r in df.iterrows()]
doc = np.array([int(c.split("  ")[0]) for c in conc])
smp = [c.split("  ")[1].replace(" (μg/L)", "") for c in conc]

X = df[conc].apply(pd.to_numeric, errors="coerce")          # 化合物 x 样品
X = X.fillna(0).clip(lower=0)
X.index = comp
ids = [f"D{d}|{i+1:03d}" for i, d in enumerate(doc)]   # 唯一样品ID(文献|序号)
X.columns = ids
# 去掉全零化合物
X = X.loc[(X > 0).sum(axis=1) >= 2]
w("== 数据 ==")
w("化合物 %d 个, 样品 %d 个, 非空浓度 %d / %d (%.1f%%)" % (
    X.shape[0], X.shape[1], int(df[conc].notna().sum().sum()), df[conc].size,
    100 * df[conc].notna().sum().sum() / df[conc].size))

S = X.T                                                    # 样品 x 化合物
logS = np.log10(S + 1)
Z = (logS - logS.mean()) / logS.std(ddof=0).replace(0, np.nan)
Z = Z.fillna(0)

# ---------------- PCA ----------------
p = PCA(n_components=min(10, Z.shape[0], Z.shape[1]), random_state=0)
scores = p.fit_transform(Z.values)
evr = p.explained_variance_ratio_
sdf = pd.DataFrame(scores, index=Z.index,
                   columns=[f"PC{i+1}" for i in range(scores.shape[1])])
sdf.insert(0, "样品", smp)
sdf.insert(0, "文献", [f"D{d}" for d in doc])
ldf = pd.DataFrame(p.components_.T, index=Z.columns,
                   columns=[f"PC{i+1}" for i in range(scores.shape[1])])
ldf.insert(0, "中文名称", Z.columns)

w("")
w("== PCA (log10(1+x) + 按化合物z-score) ==")
w("解释方差: " + ", ".join("PC%d=%.1f%%" % (i + 1, 100 * v) for i, v in enumerate(evr[:6])))
w("PC1+PC2 累计 = %.1f%%" % (100 * evr[:2].sum()))

# 文档配色
docs = sorted(set(doc))
pal = (list(cm.tab20.colors) + list(cm.tab20b.colors) + list(cm.tab20c.colors))
dcolor = {d: pal[i % len(pal)] for i, d in enumerate(docs)}

# 1) 碎石图
fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(range(1, len(evr) + 1), 100 * evr, color="#4C72B0")
ax.plot(range(1, len(evr) + 1), 100 * np.cumsum(evr), "o-", color="#C44E52", ms=4)
ax.set_xlabel("主成分"); ax.set_ylabel("解释方差 (%)"); ax.set_title("PCA 碎石图")
ax2 = ax.twinx(); ax2.set_ylim(0, 105); ax2.set_ylabel("累计 (%)")
for i, v in enumerate(100 * np.cumsum(evr)):
    ax2.annotate("%.0f%%" % v, (i + 1, v), fontsize=7, color="#C44E52")
fig.tight_layout(); fig.savefig(OUTD + r"\1_PCA碎石图.png", dpi=200); plt.close(fig)

# 2) 得分图
fig, ax = plt.subplots(figsize=(11, 8))
for d in docs:
    m = np.array([dd == d for dd in doc])
    ax.scatter(scores[m, 0], scores[m, 1], s=45, color=dcolor[d],
               label=f"D{d}", edgecolor="white", linewidth=0.4)
ax.axhline(0, color="grey", lw=0.6, ls="--"); ax.axvline(0, color="grey", lw=0.6, ls="--")
ax.set_xlabel("PC1 (%.1f%%)" % (100 * evr[0])); ax.set_ylabel("PC2 (%.1f%%)" % (100 * evr[1]))
ax.set_title("PCA 得分图（113个样品，按文献编号着色）")
ax.legend(fontsize=7, ncol=2, loc="best", frameon=False)
fig.tight_layout(); fig.savefig(OUTD + r"\2_PCA得分图.png", dpi=200); plt.close(fig)

# 3) 载荷图(PC1/PC2 各前12, 条形图)
fig, axes = plt.subplots(1, 2, figsize=(13, 6))
for ax, pc in zip(axes, ["PC1", "PC2"]):
    t = ldf.reindex(ldf[pc].abs().sort_values(ascending=False).index)[:12].iloc[::-1]
    colors = ["#C44E52" if v > 0 else "#4C72B0" for v in t[pc]]
    ax.barh([str(x)[:16] for x in t["中文名称"]], t[pc], color=colors)
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_title("%s 载荷前12 (解释方差 %.1f%%)" % (pc, 100 * evr[0] if pc == "PC1" else 100 * evr[1]),
                 fontsize=11)
    ax.set_xlabel("载荷"); ax.tick_params(labelsize=8)
fig.tight_layout(); fig.savefig(OUTD + r"\3_PCA载荷图.png", dpi=200); plt.close(fig)

# ---------------- 聚类热图(自定义布局, 便于阅读) ----------------
from scipy.cluster.hierarchy import leaves_list, fcluster

nz = (X > 0).sum(axis=0)                     # 每样品检出化合物数
cmap_nz = {"≤10": "#d9d9d9", "11-20": "#a6bddb", "21-30": "#3690c0", "31-41": "#034e7b"}

col_link = linkage(Z.values, method="ward", metric="euclidean")       # 样品聚类
row_link = linkage(Z.T.values, method="ward", metric="euclidean")     # 化合物聚类
col_idx = leaves_list(col_link); row_idx = leaves_list(row_link)
col_order = [ids[i] for i in col_idx]
row_order = [Z.columns[i] for i in row_idx]
H = Z.T.values[np.ix_(row_idx, col_idx)]     # 化合物 x 样品(按聚类排序)
nr, nc = H.shape

fig = plt.figure(figsize=(26, 14))
gs = fig.add_gridspec(3, 3, width_ratios=[1.0, 20, 0.02],
                      height_ratios=[0.9, 0.45, 12], wspace=0.004, hspace=0.004)
ax_cd = fig.add_subplot(gs[0, 1])
ax_cb = fig.add_subplot(gs[1, 1])
ax_h = fig.add_subplot(gs[2, 1])
ax_rd = fig.add_subplot(gs[2, 0])

# 列树
dendrogram(col_link, ax=ax_cd, no_labels=True, color_threshold=0,
           above_threshold_color="#777")
ax_cd.set_xlim(0, 10 * nc); ax_cd.axis("off")
# 行树
dendrogram(row_link, orientation="left", ax=ax_rd, no_labels=True, color_threshold=0,
           above_threshold_color="#777")
ax_rd.set_ylim(10 * nr, 0); ax_rd.axis("off")

# 热图(用树状图坐标: 第i行占[10i,10i+10])
im = ax_h.imshow(H, aspect="auto", cmap="RdBu_r", vmin=-2.5, vmax=2.5,
                 interpolation="nearest", extent=(0, 10 * nc, 10 * nr, 0))
ax_h.set_xlim(0, 10 * nc); ax_h.set_ylim(10 * nr, 0)
ax_h.set_yticks([10 * i + 5 for i in range(nr)])
ax_h.set_yticklabels(row_order, fontsize=8)
ax_h.yaxis.tick_right()
ax_h.set_xticks([10 * j + 5 for j in range(nc)])
ax_h.set_xticklabels([c.split("|")[0] for c in col_order], fontsize=6, rotation=90)
ax_h.tick_params(length=0)
ax_h.set_xlabel("样品（113个；列标签=文献编号，上两条分别=文献配色 / 检出化合物数分档）",
                fontsize=10)

# 列注释条(文献色 + 检出数)
ax_cb.set_xlim(0, 10 * nc); ax_cb.set_ylim(0, 2)
for j, c in enumerate(col_order):
    d = int(c.split("|")[0][1:])
    ax_cb.add_patch(plt.Rectangle((10 * j, 1), 10, 1, color=dcolor[d], lw=0))
    n = int(nz[c])
    cat = "≤10" if n <= 10 else "11-20" if n <= 20 else "21-30" if n <= 30 else "31-41"
    ax_cb.add_patch(plt.Rectangle((10 * j, 0), 10, 1, color=cmap_nz[cat], lw=0))
ax_cb.set_xticks([]); ax_cb.set_yticks([])
for sp in ax_cb.spines.values(): sp.set_visible(False)
ax_cb.text(10 * nc + 3, 1.5, "文献", fontsize=8, va="center")
ax_cb.text(10 * nc + 3, 0.5, "检出数", fontsize=8, va="center")
ax_cb.text(-2, 1.5, "列注释", fontsize=8, va="center", ha="right")

# z 色标 + 检出数图例
cax = fig.add_axes([0.030, 0.80, 0.006, 0.10])
cb = fig.colorbar(im, cax=cax); cb.set_label("z-score", fontsize=8, labelpad=2)
cb.ax.tick_params(labelsize=7)
lg = fig.add_axes([0.085, 0.795, 0.10, 0.11]); lg.axis("off")
lg.text(0.0, 0.95, "检出化合物数/样品", fontsize=8)
for i, (k, v) in enumerate(cmap_nz.items()):
    lg.add_patch(plt.Rectangle((0.0, 0.72 - i * 0.2), 0.12, 0.14, color=v))
    lg.text(0.18, 0.79 - i * 0.2, k, fontsize=7, va="center")

fig.suptitle("41个化合物 × 113个样品 层次聚类热图"
             "（log10(1+x) → 按化合物 z-score；ward/euclidean）", fontsize=16, y=0.965)
fig.text(0.99, 0.945, "上条配色与PCA得分图一致(D1–D27)", fontsize=8, ha="right", color="#555")
fig.savefig(OUTD + r"\4_聚类热图.png", dpi=200, bbox_inches="tight")
plt.close(fig)

# ---------------- 补充: 文献均值热图(27文献) ----------------
Zdoc = Z.copy()
Zdoc["_D"] = [f"D{d}" for d in doc]
Dmean = Zdoc.groupby("_D").mean().T                       # 化合物 x 文献
coll = linkage(Dmean.T.values, method="ward", metric="euclidean")
rowl = linkage(Dmean.values, method="ward", metric="euclidean")
ci = leaves_list(coll); ri = leaves_list(rowl)
Hd = Dmean.values[np.ix_(ri, ci)]
fig, ax = plt.subplots(figsize=(11, 12))
im2 = ax.imshow(Hd, aspect="auto", cmap="RdBu_r", vmin=-2, vmax=2)
ax.set_xticks(range(len(ci)))
ax.set_xticklabels([Dmean.columns[i] for i in ci], fontsize=9)
ax.set_yticks(range(len(ri)))
ax.set_yticklabels([Dmean.index[i] for i in ri], fontsize=8)
ax.yaxis.set_ticks_position("left")
ax.tick_params(length=0)
ax.set_title("文献层面均值热图（41化合物 × 27文献，按文献内样品均值）", fontsize=12)
cb2 = fig.colorbar(im2, ax=ax, fraction=0.03, pad=0.02, location="bottom", shrink=0.5)
cb2.set_label("z-score", fontsize=8)
fig.tight_layout(); fig.savefig(OUTD + r"\6_文献均值热图.png", dpi=200); plt.close(fig)

# ---------------- 补充: 相对组成PCA ----------------
rel = S.div(S.sum(axis=1).replace(0, np.nan), axis=0) * 100
rel = rel.fillna(0)
logR = np.log10(rel + 0.01)
Zr = (logR - logR.mean()) / logR.std(ddof=0).replace(0, np.nan)
Zr = Zr.fillna(0)
p2 = PCA(n_components=min(6, Zr.shape[0], Zr.shape[1]), random_state=0)
sc2 = p2.fit_transform(Zr.values)
evr2 = p2.explained_variance_ratio_
fig, ax = plt.subplots(figsize=(11, 8))
for d in docs:
    m = np.array([dd == d for dd in doc])
    ax.scatter(sc2[m, 0], sc2[m, 1], s=45, color=dcolor[d], label=f"D{d}",
               edgecolor="white", linewidth=0.4)
ax.axhline(0, color="grey", lw=0.6, ls="--"); ax.axvline(0, color="grey", lw=0.6, ls="--")
ax.set_xlabel("PC1 (%.1f%%)" % (100 * evr2[0])); ax.set_ylabel("PC2 (%.1f%%)" % (100 * evr2[1]))
ax.set_title("补充: 相对组成 PCA（各样品归一为100%后 log+z）")
ax.legend(fontsize=7, ncol=2, frameon=False)
fig.tight_layout(); fig.savefig(OUTD + r"\5_相对组成PCA得分图.png", dpi=200); plt.close(fig)

# ---------------- 输出xlsx ----------------
pre = pd.DataFrame(Z.values, index=Z.index, columns=Z.columns).T  # 化合物x样品
var = pd.DataFrame({"主成分": [f"PC{i+1}" for i in range(len(evr))],
                    "解释方差%": 100 * evr, "累计%": 100 * np.cumsum(evr)})
with pd.ExcelWriter(OUTD + r"\PCA_聚类分析结果.xlsx", engine="openpyxl") as wri:
    pd.DataFrame([
        ["输入", "可用化合物原始数据.xlsx / all data"],
        ["规模", "%d化合物 x %d样品; 非空浓度%d/%d" % (
            X.shape[0], X.shape[1], int(df[conc].notna().sum().sum()), df[conc].size)],
        ["预处理", "缺失(未检出)记0 -> log10(1+x) -> 按化合物(列)z-score; 全零/单一值化合物剔除"],
        ["PCA", "sklearn PCA, 已标准化数据不重复缩放; 得分=样品, 载荷=化合物"],
        ["聚类", "层次聚类 ward + euclidean, 行=化合物(z-score), 列=样品(z-score)"],
        ["补充PCA", "相对组成: 每样品各化合物占该样品总量%, log10(%+0.01) 后 z-score"],
        ["注意", "各文献浓度量级差异大(部分文献单位×1000换算), PC1 可能主要反映总体浓度水平而非香气组成"],
    ], columns=["项目", "说明"]).to_excel(wri, sheet_name="说明", index=False)
    var.to_excel(wri, sheet_name="PCA方差解释", index=False)
    sdf.to_excel(wri, sheet_name="PCA得分", index=False)
    ldf.sort_values("PC1", ascending=False).to_excel(wri, sheet_name="PCA载荷", index=False)
    pre.to_excel(wri, sheet_name="预处理矩阵(log10_z)")
    pd.DataFrame({"聚类顺序": range(1, len(col_order) + 1), "样品ID": col_order,
                  "文献": [c.split("|")[0] for c in col_order],
                  "样品": [smp[ids.index(c)] for c in col_order],
                  "检出化合物数": [int(nz[c]) for c in col_order]}
                 ).to_excel(wri, sheet_name="样品聚类顺序", index=False)
    pd.DataFrame({"聚类顺序": range(1, len(row_order) + 1), "化合物": row_order}
                 ).to_excel(wri, sheet_name="化合物聚类顺序", index=False)
    pd.DataFrame({"样品ID": ids,
                  "文献": [f"D{d}" for d in doc],
                  "样品": smp,
                  "PC1": sc2[:, 0], "PC2": sc2[:, 1],
                  "PC1%": 100 * evr2[0], "PC2%": 100 * evr2[1]}
                 ).to_excel(wri, sheet_name="相对组成PCA得分", index=False)

# ---------------- 文字结论 ----------------
w("")
w("== 载荷 TOP8 (PC1) ==")
for _, r in ldf.reindex(ldf["PC1"].abs().sort_values(ascending=False).index)[:8].iterrows():
    w("  %-16s PC1=%+.3f  PC2=%+.3f" % (str(r["中文名称"])[:16], r["PC1"], r["PC2"]))
w("")
w("== 载荷 TOP8 (PC2) ==")
for _, r in ldf.reindex(ldf["PC2"].abs().sort_values(ascending=False).index)[:8].iterrows():
    w("  %-16s PC1=%+.3f  PC2=%+.3f" % (str(r["中文名称"])[:16], r["PC1"], r["PC2"]))
w("")
w("== 相对组成PCA ==")
w("PC1=%.1f%% PC2=%.1f%% (累计%.1f%%)" % (100 * evr2[0], 100 * evr2[1],
                                          100 * (evr2[0] + evr2[1])))
w("")
w("== 样品聚类: 各文献在主簇中的分布 ==")
# 两簇划分(col dendrogram 最高层)
cl = fcluster(col_link, 2, criterion="maxclust")
dist = pd.crosstab(pd.Series([f"D{d}" for d in doc], name="文献"), pd.Series(cl, name="簇"))
w(dist.to_string())
with open(OUTD + r"\PCA聚类分析.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
w("")
w("DONE -> " + OUTD)
