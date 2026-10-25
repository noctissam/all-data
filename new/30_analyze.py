# -*- coding: utf-8 -*-
"""
30_analyze.py
=============
Step 3: relationship mining on the cleaned master library, with figures.

Outputs (new/output/*.csv, new/figures/*.png)
--------------------------------------------
  key_compounds.csv        the 20 "OAV>1" key aroma compounds used for modelling
  corr_spearman.csv        62x62 Spearman R
  corr_pvalues.csv         62x62 p-values
  corr_key20_R.csv         the 20x20 matrix (+ P) requested by the proposal
  compound_clusters.csv    variable-level hierarchical clusters
  sample_scores.csv        PCA scores / loadings for the sample space
  dbscan_labels.csv        DBSCAN sample clusters
  vip.csv                  PLSR VIP (aging proxy)
  oav_weights.csv          relative-OAV contribution weights (风味贡献权重表)
  network_edges.csv        significant compound-compound edges
  fig01..fig13             figures

The analysis deliberately mixes
  * scale-free statistics (Spearman, percentile ranks) — valid for every column, and
  * unit-dependent statistics (OAV, absolute concentrations) — restricted to the
    columns that passed the 己酸乙酯 plausibility check.
"""
from __future__ import annotations

import io
import os
import sys
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import seaborn as sns
from scipy import stats
from scipy.cluster import hierarchy as hc
from scipy.spatial.distance import squareform
from sklearn.decomposition import PCA
from sklearn.cluster import DBSCAN
from sklearn.cross_decomposition import PLSRegression
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors
import networkx as nx

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cleanlib as cl  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)

# ---------------------------------------------------------------------------
# house style (CJK-capable)
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.dpi": 130,
    "savefig.dpi": 130,
    "savefig.bbox": "tight",
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "font.size": 9.5,
    "axes.grid": True,
    "grid.alpha": 0.25,
})
sns.set_palette("deep")
CLS_COLOR = {
    "酯类 Ester": "#4C72B0", "酸类 Acid": "#DD8452", "醇类 Alcohol": "#55A868",
    "醛类 Aldehyde": "#C44E52", "酮类 Ketone": "#8172B3", "酚类 Phenol": "#937860",
    "硫化物 Sulfur": "#DA8BC3", "呋喃 Furan": "#8C8C8C", "内酯 Lactone": "#CCB974",
    "吡嗪 Pyrazine": "#64B5CD", "其他 Other": "#BBBBBB",
}
BIO = {"酯类 Ester": "酯类", "酸类 Acid": "酸类", "醇类 Alcohol": "醇类",
       "醛类 Aldehyde": "醛类", "酮类 Ketone": "酮类", "酚类 Phenol": "酚类",
       "硫化物 Sulfur": "硫化物", "呋喃 Furan": "呋喃类", "内酯 Lactone": "内酯",
       "吡嗪 Pyrazine": "吡嗪", "其他 Other": "其他"}


def short(name: str) -> str:
    """Compact label: English name, keep it readable on axes."""
    return (name.replace("Ethyl ", "Et-").replace("Methyl ", "Me-")
                .replace("Isoamyl ", "iAm-").replace("Isobutyl ", "iBu-")
                .replace("isoamyl ", "iAm-"))


# ---------------------------------------------------------------------------
# load cleaned artefacts
# ---------------------------------------------------------------------------
long = pd.read_csv(os.path.join(OUT, "master_long.csv"))
cols = pd.read_csv(os.path.join(OUT, "column_registry.csv"))
oav_sum = pd.read_csv(os.path.join(OUT, "oav_summary.csv"))
cm = pd.read_csv(os.path.join(OUT, "compound_master.csv"))
issues = pd.read_csv(os.path.join(OUT, "issues_log.csv"))
sheets = pd.read_csv(os.path.join(OUT, "sheets_long.csv"))

long["name_short"] = long["name_en"].map(short)
cols["col_label"] = cols["sample_label"].where(
    cols["sample_label"].astype(str).str.len() > 0, cols["header_raw"])
cols["col_label"] = [f"{int(s) if s == s else '?'}-{l}" for s, l in
                     zip(cols["study_no"], cols["col_label"])]
cols["full_label"] = [f"{sh}\n[{lab}]" for sh, lab in zip(cols["sample_label"], cols["col_label"])]

usable_ids = set(cols.loc[cols["usable_absolute"], "col_index"])
print(f"usable columns: {len(usable_ids)} / {len(cols)}")

# compound x column matrices
wide_raw = long.pivot_table(index="name_short", columns="col_index",
                            values="value_mean", aggfunc="first")
wide_ugl = long.pivot_table(index="name_short", columns="col_index",
                            values="value_ugL", aggfunc="first")
wide_use = wide_raw[[c for c in wide_raw.columns if c in usable_ids]]
present = wide_use.notna().sum(axis=1)

# ===========================================================================
# 1. key-compound selection (the "OAV>1" set the proposal asks for)
# ===========================================================================
sel = oav_sum.copy()
sel["n_meas"] = sel["n_measurements"]
key = (sel[(sel["oav_median"] > 1) & (sel["n_meas"] >= 20)]
       .sort_values("oav_median", ascending=False)
       .head(20)
       .reset_index(drop=True))
key["rank"] = key.index + 1
key_short = [short(n) for n in key["name_en"]]
key.to_csv(os.path.join(OUT, "key_compounds.csv"), index=False, encoding="utf-8-sig")
print(f"key compounds selected: {len(key)}  "
      f"(median OAV>1 and reported by >=20 usable columns)")
print("  " + ", ".join(key_short))

# ===========================================================================
# 2. Spearman correlation across the whole library (scale-free)
# ===========================================================================
names = list(wide_use.index)
M = wide_use.to_numpy(dtype=float)
N = len(names)
R = np.full((N, N), np.nan)
P = np.full((N, N), np.nan)
NOBS = np.zeros((N, N), dtype=int)
MIN_OBS = 5
for i in range(N):
    R[i, i], P[i, i], NOBS[i, i] = 1.0, 0.0, int(np.isfinite(M[i]).sum())
    for j in range(i + 1, N):
        a, b = M[i], M[j]
        m = np.isfinite(a) & np.isfinite(b)
        NOBS[i, j] = NOBS[j, i] = int(m.sum())
        if m.sum() >= MIN_OBS and np.std(a[m]) > 0 and np.std(b[m]) > 0:
            r, p = stats.spearmanr(a[m], b[m])
            R[i, j] = R[j, i] = r
            P[i, j] = P[j, i] = p
corr_R = pd.DataFrame(R, index=names, columns=names)
corr_P = pd.DataFrame(P, index=names, columns=names)
corr_R.to_csv(os.path.join(OUT, "corr_spearman.csv"), encoding="utf-8-sig")
corr_P.to_csv(os.path.join(OUT, "corr_pvalues.csv"), encoding="utf-8-sig")
pd.DataFrame(NOBS, index=names, columns=names).to_csv(
    os.path.join(OUT, "corr_n_obs.csv"), encoding="utf-8-sig")
n_sig = int(np.nansum((P < 0.05) & np.triu(np.ones_like(P), 1).astype(bool)))
print(f"correlation: {N}x{N} pairs, {n_sig} significant at P<0.05")

# ---- fig: the 20x20 heat map with significance (proposal's alternative plan)
sub_idx = [n for n in key_short if n in corr_R.index]
R20 = corr_R.loc[sub_idx, sub_idx]
P20 = corr_P.loc[sub_idx, sub_idx]
R20.to_csv(os.path.join(OUT, "corr_key20_R.csv"), encoding="utf-8-sig")
P20.to_csv(os.path.join(OUT, "corr_key20_P.csv"), encoding="utf-8-sig")

fig, ax = plt.subplots(figsize=(11.2, 9.4))
mask = np.triu(np.ones_like(R20, dtype=bool), k=1)
sns.heatmap(R20, mask=mask, cmap="RdBu_r", center=0, vmin=-1, vmax=1,
            square=True, linewidths=.4, linecolor="white",
            cbar_kws={"label": "Spearman R", "shrink": .72}, ax=ax)
for i in range(len(sub_idx)):
    for j in range(len(sub_idx)):
        if j >= i:
            continue
        v, p = R20.iloc[i, j], P20.iloc[i, j]
        if not np.isfinite(v):
            continue
        star = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        ax.text(j + .5, i + .5, f"{v:.2f}{star}", ha="center", va="center",
                fontsize=6.1, color="white" if abs(v) > .55 else "#222")
ax.set_title("关键香气化合物相关矩阵（20×20，Spearman R）\n"
             "* P<0.05   ** P<0.01   *** P<0.001   （下三角；上三角留白）", pad=14)
ax.set_xticklabels(sub_idx, rotation=60, ha="right", fontsize=8.5)
ax.set_yticklabels(sub_idx, rotation=0, fontsize=8.5)
fig.savefig(os.path.join(FIG, "fig02_corr20_significance.png"))
plt.close(fig)

# ---- fig: full clustered correlation heat map
fig, ax = plt.subplots(figsize=(12.6, 11.4))
D = 1 - corr_R.fillna(0).to_numpy()
np.fill_diagonal(D, 0)
Zc = hc.linkage(squareform(D, checks=False), method="average")
order = hc.leaves_list(Zc)
Rn = corr_R.iloc[order, order]
sns.heatmap(Rn, cmap="RdBu_r", center=0, vmin=-1, vmax=1, square=True,
            xticklabels=True, yticklabels=True, linewidths=0,
            cbar_kws={"label": "Spearman R", "shrink": .6}, ax=ax)
ax.set_xticklabels(ax.get_xticklabels(), rotation=90, fontsize=5.4)
ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=5.4)
ax.set_title(f"全库化合物相关矩阵（{N}×{N}，Spearman，按平均连接聚类排序）\n"
             f"仅保留 ≥{MIN_OBS} 对观测的组合", pad=12)
fig.savefig(os.path.join(FIG, "fig03_corr_full_clustered.png"))
plt.close(fig)

# ===========================================================================
# 3. variable-level hierarchical clustering (proposal step 1.1)
# ===========================================================================
Zp = hc.linkage(squareform(D, checks=False), method="ward")
for k in (4, 5, 6):
    lab = hc.fcluster(Zp, k, criterion="maxclust")
    if k == 5:
        cluster5 = lab
clusters = pd.DataFrame({"name_short": names, "cluster": cluster5})
clusters = clusters.merge(
    cm.assign(name_short=cm["name_en"].map(short))[["name_short", "name_en", "name_zh", "chem_class"]],
    on="name_short", how="left")
clusters = clusters.sort_values(["cluster", "name_en"])
clusters.to_csv(os.path.join(OUT, "compound_clusters.csv"), index=False, encoding="utf-8-sig")

fig = plt.figure(figsize=(13.5, 6.6))
ax = fig.add_subplot(1, 1, 1)
dn = hc.dendrogram(Zp, labels=names, leaf_rotation=90, leaf_font_size=6.4,
                  color_threshold=Zp[-4, 2], ax=ax)
ax.set_ylabel("Ward 距离（基于 1 − Spearman |R|）")
ax.set_title("化合物层面层次聚类（变量级）——虚线下切分即“变量组”", pad=12)
ax.axhline(Zp[-4, 2], ls="--", c="crimson", lw=1.4)
ax.grid(False)
# annotate cluster membership on the x tick labels
for t in ax.get_xticklabels():
    t.set_color(CLS_COLOR.get(
        clusters.loc[clusters["name_short"] == t.get_text(), "chem_class"].iloc[0]
        if (clusters["name_short"] == t.get_text()).any() else "其他 Other", "#333"))
fig.savefig(os.path.join(FIG, "fig04_dendrogram_compounds.png"))
plt.close(fig)

# ===========================================================================
# 4. sample space: PCA, DBSCAN, sample dendrogram
# ===========================================================================
X_names = [n for n in key_short if n in wide_use.index]
X = wide_use.loc[X_names].T.copy()                  # samples x compounds
meta = cols.set_index("col_index").loc[X.index]
keep = X.notna().sum(axis=1) >= 12
Xk, metak = X[keep], meta[keep]
Xk = Xk.fillna(Xk.median())
Xlog = np.log10(np.clip(Xk.to_numpy(dtype=float), 1e-2, None))
Xs = StandardScaler().fit_transform(Xlog)
print(f"sample space: {Xs.shape[0]} samples x {Xs.shape[1]} compounds "
      f"(median-imputed, log10 then z-score)")

pca = PCA(n_components=min(6, Xs.shape[0], Xs.shape[1]))
S = pca.fit_transform(Xs)
evr = pca.explained_variance_ratio_
scores = pd.DataFrame(S[:, :3], index=Xk.index, columns=["PC1", "PC2", "PC3"])
scores = scores.join(metak[["study_no", "study_label", "sample_label", "full_label"]])
loadings = pd.DataFrame(pca.components_[:3].T, index=X_names, columns=["PC1", "PC2", "PC3"])
scores.to_csv(os.path.join(OUT, "sample_scores.csv"), encoding="utf-8-sig")
loadings.to_csv(os.path.join(OUT, "pca_loadings.csv"), encoding="utf-8-sig")

fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.0),
                         gridspec_kw={"width_ratios": [1, 2.1, 1.5]})
axes[0].bar(range(1, len(evr) + 1), evr * 100, color="#4C72B0")
axes[0].plot(range(1, len(evr) + 1), np.cumsum(evr) * 100, "o-", c="crimson", ms=4)
axes[0].set_xlabel("主成分"), axes[0].set_ylabel("解释方差 (%)")
axes[0].set_title(f"碎石图\nPC1+PC2 = {(evr[0] + evr[1]) * 100:.1f}%")
ax = axes[1]
studies = sorted(scores["study_no"].dropna().unique())
cmap = plt.get_cmap("tab20")
for k, s in enumerate(studies):
    m = scores["study_no"] == s
    ax.scatter(scores.loc[m, "PC1"], scores.loc[m, "PC2"], s=42,
               color=cmap(k % 20), label=f"{int(s)}", edgecolor="k", linewidth=.3)
ax.set_xlabel(f"PC1 ({evr[0] * 100:.1f}%)"), ax.set_ylabel(f"PC2 ({evr[1] * 100:.1f}%)")
ax.set_title("样品主成分得分图（按文献编号着色）")
ax.legend(title="文献", ncol=2, fontsize=6.5, title_fontsize=7, loc="best")
ax.axhline(0, c="grey", lw=.6), ax.axvline(0, c="grey", lw=.6)
ax = axes[2]
ld = loadings[["PC1", "PC2"]].copy()
ax.scatter(ld["PC1"], ld["PC2"], s=26, c="#55A868", edgecolor="k", linewidth=.3)
for n, row in ld.iterrows():
    ax.annotate(n, (row["PC1"], row["PC2"]), fontsize=5.8,
                xytext=(3, 3), textcoords="offset points")
ax.axhline(0, c="grey", lw=.6), ax.axvline(0, c="grey", lw=.6)
ax.set_xlabel("PC1 载荷"), ax.set_ylabel("PC2 载荷"), ax.set_title("载荷图（化合物）")
fig.suptitle("图 05  样品空间 PCA —— 浓香型白酒样品在主成分空间的分布", y=1.02, fontsize=13)
fig.savefig(os.path.join(FIG, "fig05_pca_samples.png"))
plt.close(fig)

# ---- DBSCAN on the same space (proposal step 1.2)
nn = NearestNeighbors(n_neighbors=5).fit(Xs)
dist, _ = nn.kneighbors(Xs)
kdist = np.sort(dist[:, -1])
best = None
for eps in np.linspace(np.percentile(kdist, 20), np.percentile(kdist, 85), 40):
    lab = DBSCAN(eps=eps, min_samples=4).fit_predict(Xs)
    ncl = len(set(lab)) - (1 if -1 in lab else 0)
    noise = float((lab == -1).mean())
    if ncl >= 2 and noise <= 0.35:
        score = ncl - 3 * noise
        if best is None or score > best[0]:
            best = (score, eps, lab, ncl, noise)
if best is None:
    eps = float(np.percentile(kdist, 60))
    lab = DBSCAN(eps=eps, min_samples=4).fit_predict(Xs)
    best = (0, eps, lab, len(set(lab)) - (1 if -1 in lab else 0), float((lab == -1).mean()))
_, eps, lab, ncl, noise = best
db = scores.copy()
db["dbscan"] = lab
db.to_csv(os.path.join(OUT, "dbscan_labels.csv"), encoding="utf-8-sig")
print(f"DBSCAN: eps={eps:.2f}, clusters={ncl}, noise={noise * 100:.1f}%")

fig, axes = plt.subplots(1, 2, figsize=(14, 5.2))
axes[0].plot(range(len(kdist)), kdist, c="#4C72B0")
axes[0].axhline(eps, ls="--", c="crimson", label=f"选定 eps = {eps:.2f}")
axes[0].set_xlabel("按 5-近邻距离排序的样本"), axes[0].set_ylabel("到第 5 近邻的距离")
axes[0].set_title("k-距离图（选择 DBSCAN 的 eps）"), axes[0].legend()
ax = axes[1]
noise_m = db["dbscan"] == -1
ax.scatter(db.loc[noise_m, "PC1"], db.loc[noise_m, "PC2"], s=46, marker="x",
           c="crimson", label=f"噪声/离群 ({int(noise_m.sum())})")
pal = plt.get_cmap("Dark2")
for k in sorted(set(lab) - {-1}):
    m = db["dbscan"] == k
    ax.scatter(db.loc[m, "PC1"], db.loc[m, "PC2"], s=46, color=pal(k % 8),
               label=f"簇 {k} (n={int(m.sum())})", edgecolor="k", linewidth=.3)
ax.set_xlabel(f"PC1 ({evr[0] * 100:.1f}%)"), ax.set_ylabel(f"PC2 ({evr[1] * 100:.1f}%)")
ax.set_title("样本 DBSCAN 聚类（有效样本簇 / 离群样本）")
ax.legend(fontsize=7.5)
fig.suptitle("图 06  样品密度聚类 —— 判定“有效样本簇”", y=1.02, fontsize=13)
fig.savefig(os.path.join(FIG, "fig06_dbscan_samples.png"))
plt.close(fig)

# ---- sample dendrogram
fig, ax = plt.subplots(figsize=(15, 6.2))
Zs = hc.linkage(Xs, method="ward")
lbl = [metak.loc[i, "full_label"] for i in Xk.index]
hc.dendrogram(Zs, labels=lbl, leaf_rotation=90, leaf_font_size=6.0, ax=ax)
ax.set_ylabel("Ward 距离")
ax.set_title("样品层面层次聚类（62 化合物标准化的 log 浓度）", pad=10)
ax.grid(False)
fig.savefig(os.path.join(FIG, "fig07_sample_dendrogram.png"))
plt.close(fig)

# ===========================================================================
# 5. threshold vs concentration, OAV, contribution weights
# ===========================================================================
med = long[long["usable_absolute"]].groupby(["name_en", "name_zh", "chem_class", "name_short"],
                                            dropna=False)["value_ugL"].median().reset_index()
thr = oav_sum[["name_en", "threshold_ugL", "oav_median", "oav_max", "n_measurements"]]
tv = med.merge(thr, on="name_en", how="inner").dropna(subset=["threshold_ugL", "value_ugL"])
tv = tv[(tv["value_ugL"] > 0) & (tv["threshold_ugL"] > 0)]
tv["oav"] = tv["value_ugL"] / tv["threshold_ugL"]
tv.to_csv(os.path.join(OUT, "threshold_vs_concentration.csv"), index=False, encoding="utf-8-sig")

fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.2),
                         gridspec_kw={"width_ratios": [1.35, 1]})
ax = axes[0]
for cls, g in tv.groupby("chem_class"):
    ax.scatter(g["threshold_ugL"], g["value_ugL"], s=np.clip(g["n_measurements"] * 1.6, 12, 190),
               color=CLS_COLOR.get(cls, "#888"), alpha=.82, edgecolor="k", linewidth=.4, label=BIO.get(cls, cls))
xs = np.logspace(np.log10(tv["threshold_ugL"].min() * .3), np.log10(tv["threshold_ugL"].max() * 3), 50)
for k, ls in [(1, "-"), (10, "--"), (100, ":")]:
    ax.plot(xs, k * xs, ls, color="k", lw=.9, alpha=.65)
    ax.annotate(f"OAV={k}", (xs[-1], k * xs[-1]), fontsize=7, color="k",
                xytext=(-30, 4), textcoords="offset points")
ax.set_xscale("log"), ax.set_yscale("log")
ax.set_xlabel("气味阈值 / (μg/L)"), ax.set_ylabel("中位质量浓度 / (μg/L)")
ax.set_title("阈值—浓度分布图（气泡大小 = 文献报道次数）")
ax.legend(fontsize=7.5, title="化合物类别", ncol=2, title_fontsize=8)
for _, r in tv.nlargest(8, "oav").iterrows():
    ax.annotate(r["name_short"], (r["threshold_ugL"], r["value_ugL"]), fontsize=6.4,
                xytext=(4, 4), textcoords="offset points", color="#111")
ax = axes[1]
top = tv[tv["n_measurements"] >= 5].nlargest(18, "oav").sort_values("oav")
cols_ = [CLS_COLOR.get(c, "#888") for c in top["chem_class"]]
ax.barh([f"{short(n)}  (n={int(m)})" for n, m in zip(top["name_en"], top["n_measurements"])],
        top["oav"], color=cols_, edgecolor="k", linewidth=.35)
ax.set_xscale("log")
ax.set_xlabel("中位 OAV（对数轴）")
ax.set_title("香气活性值排名前 18 的化合物")
ax.axvline(1, c="crimson", ls="--", lw=1.2)
ax.tick_params(axis="y", labelsize=7.6)
fig.suptitle("图 08  气味阈值 → OAV → 关键香气化合物", y=1.01, fontsize=13)
fig.savefig(os.path.join(FIG, "fig08_threshold_oav.png"))
plt.close(fig)

# ---- relative-OAV contribution weights (风味贡献权重表)
oav_mat = long[(long["oav"].notna()) & long["usable_absolute"]].pivot_table(
    index="name_short", columns="col_index", values="oav", aggfunc="median")
oav_mat = oav_mat.loc[:, oav_mat.sum(axis=0) > 0]
share = oav_mat.div(oav_mat.sum(axis=0), axis=1) * 100
w = pd.DataFrame({
    "mean_weight_%": share.mean(axis=1),
    "median_weight_%": share.median(axis=1),
    "n_samples": share.notna().sum(axis=1),
    "oav_median": oav_sum.set_index(oav_sum["name_en"].map(short))["oav_median"],
}).dropna(subset=["mean_weight_%"]).sort_values("mean_weight_%", ascending=False)
w["chem_class"] = [cm.set_index(cm["name_en"].map(short))["chem_class"].get(i, "其他 Other")
                   for i in w.index]
w.to_csv(os.path.join(OUT, "oav_weights.csv"), encoding="utf-8-sig")
share.to_csv(os.path.join(OUT, "oav_share_matrix.csv"), encoding="utf-8-sig")

fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.4),
                         gridspec_kw={"width_ratios": [1, 1.25]})
ax = axes[0]
t = w.head(16).sort_values("mean_weight_%")
ax.barh(list(t.index), t["mean_weight_%"],
        color=[CLS_COLOR.get(c, "#888") for c in t["chem_class"]],
        edgecolor="k", linewidth=.35)
ax.set_xlabel("平均相对 OAV 贡献权重 / %")
ax.set_title("风味贡献权重表（相对 OAV 法，前 16 位）")
ax.tick_params(axis="y", labelsize=7.6)
for i, (v, n) in enumerate(zip(t["mean_weight_%"], t["n_samples"])):
    ax.text(v + .3, i, f"{v:.1f}% (n={int(n)})", va="center", fontsize=6.6)
ax = axes[1]
cls_share = w.groupby("chem_class")["mean_weight_%"].sum().sort_values()
ax.barh([BIO.get(c, c) for c in cls_share.index], cls_share.values,
        color=[CLS_COLOR.get(c, "#888") for c in cls_share.index],
        edgecolor="k", linewidth=.35)
ax.set_xlabel("类别合计权重 / %")
ax.set_title("按化合物类别的香气贡献构成")
for i, v in enumerate(cls_share.values):
    ax.text(v + .5, i, f"{v:.1f}%", va="center", fontsize=7.4)
fig.suptitle("图 09  风味贡献权重表 —— 谁在贡献浓香型白酒的香气", y=1.01, fontsize=13)
fig.savefig(os.path.join(FIG, "fig09_flavor_weights.png"))
plt.close(fig)

# ===========================================================================
# 6. compound x study landscape + chemical-class profiles
# ===========================================================================
cls_of = cm.set_index(cm["name_en"].map(short))["chem_class"].to_dict()
cl = long[long["usable_absolute"]].copy()
cl["cls"] = cl["name_short"].map(cls_of)
cls_study = cl.pivot_table(index="study_no", columns="cls", values="value_ugL",
                           aggfunc="median")
cls_rel = cls_study.div(cls_study.sum(axis=1), axis=0) * 100
cls_rel.to_csv(os.path.join(OUT, "class_profile_by_study.csv"), encoding="utf-8-sig")

# compound x study heat map (z-scored log median)
cs = cl.pivot_table(index="name_short", columns="study_no", values="value_ugL",
                    aggfunc="median")
cs_log = np.log10(np.clip(cs, 1e-2, None))
z = cs_log.sub(cs_log.mean(axis=1), axis=0).div(cs_log.std(axis=1).replace(0, np.nan), axis=0)
z = z.dropna(how="all")
row_order = z.mean(axis=1).sort_values(ascending=False).index
z = z.loc[row_order]
z.to_csv(os.path.join(OUT, "compound_by_study_z.csv"), encoding="utf-8-sig")

fig = plt.figure(figsize=(17, 10.5))
gs = fig.add_gridspec(1, 2, width_ratios=[2.15, 1], wspace=.30)
ax = fig.add_subplot(gs[0, 0])
sns.heatmap(z, cmap="vlag", center=0, vmin=-2.2, vmax=2.2, ax=ax,
            cbar_kws={"label": "标准化 log 浓度 (z)", "shrink": .55})
ax.set_xlabel("文献编号"), ax.set_ylabel("")
ax.set_title("化合物 × 文献 相对丰度图谱（每化合物行内标准化）")
ax.tick_params(axis="y", labelsize=5.6)
ax.tick_params(axis="x", labelsize=7.6)
# class colour strip
for i, n in enumerate(z.index):
    ax.add_patch(plt.Rectangle((-1.05, i), .55, 1,
                               color=CLS_COLOR.get(cls_of.get(n, "其他 Other"), "#ccc"),
                               clip_on=False, lw=0))
ax = fig.add_subplot(gs[0, 1])
rel = cls_rel[[c for c in cls_rel.columns if c in BIO]]
sns.heatmap(rel.T, cmap="YlOrRd", ax=ax, annot=True, fmt=".0f", annot_kws={"fontsize": 6},
            cbar_kws={"label": "类别占比 / %", "shrink": .55},
            linewidths=.4, linecolor="white")
ax.set_yticklabels([BIO.get(c, c) for c in rel.columns], rotation=0, fontsize=8)
ax.set_xlabel("文献编号"), ax.set_ylabel("")
ax.set_title("各文献的化合物类别构成（中位浓度占比）")
fig.suptitle("图 10  化合物 × 文献 landscape 与类别构成", y=.985, fontsize=13)
fig.savefig(os.path.join(FIG, "fig10_compound_study_landscape.png"))
plt.close(fig)

# ===========================================================================
# 7. co-occurrence network of compounds
# ---------------------------------------------------------------------------
# Correlations pooled over the whole library mostly reflect *between-study*
# offsets (different labs, dilutions, methods), so the network is built from a
# WITHIN-STUDY meta-analysis instead: a compound pair only becomes an edge when
# independent studies agree on the sign and the pooled effect is strong.
# ===========================================================================
MIN_COLS_PER_STUDY = 5
MIN_PAIRS_IN_STUDY = 5
within = []
for st, g in long[long["usable_absolute"] & long["value_mean"].notna()].groupby("study_no"):
    piv = g.pivot_table(index="name_short", columns="col_index", values="value_mean",
                        aggfunc="first")
    if piv.shape[1] < MIN_COLS_PER_STUDY:
        continue
    nn_ = list(piv.index)
    for i, a in enumerate(nn_):
        for b in nn_[i + 1:]:
            m = piv.loc[a].notna() & piv.loc[b].notna()
            if m.sum() < MIN_PAIRS_IN_STUDY:
                continue
            va, vb = piv.loc[a][m], piv.loc[b][m]
            if va.std() == 0 or vb.std() == 0:
                continue
            r, p = stats.spearmanr(va, vb)
            if np.isfinite(r):
                within.append(dict(study_no=int(st), a=a, b=b, R=r, p=p, n=int(m.sum())))
W = pd.DataFrame(within)
W.to_csv(os.path.join(OUT, "within_study_correlations.csv"), index=False, encoding="utf-8-sig")


def consensus(df):
    rows = []
    for (a, b), g in df.groupby(["a", "b"]):
        n = len(g)
        pos = int((g["R"] > 0).sum())
        neg = int((g["R"] < 0).sum())
        # Stouffer's weighted z, signed by the majority direction
        sign = 1 if pos >= neg else -1
        zs = stats.norm.isf(np.clip(g["p"] / 2, 1e-12, 1 - 1e-12)) * np.sign(g["R"])
        zcomb = zs.sum() / np.sqrt(n)
        pcomb = 2 * (1 - stats.norm.cdf(abs(zcomb)))
        rows.append(dict(
            a=a, b=b, n_studies=n, n_pos=pos, n_neg=neg,
            frac_same_sign=max(pos, neg) / n,
            mean_R=float(np.tanh(np.mean(np.arctanh(np.clip(g["R"], -.999, .999))))),
            stouffer_z=zcomb, p_combined=pcomb, studies=";".join(map(str, sorted(g["study_no"]))),
        ))
    return pd.DataFrame(rows)


cons = consensus(W)
cons = cons[cons["n_studies"] >= 2].sort_values("mean_R", key=lambda s: -s.abs())
cons.to_csv(os.path.join(OUT, "consensus_correlations.csv"), index=False, encoding="utf-8-sig")
EDGE_R, EDGE_FRAC, EDGE_N = 0.60, 0.99, 3
edges_df = cons[(cons["n_studies"] >= EDGE_N) & (cons["frac_same_sign"] >= EDGE_FRAC) &
                (cons["mean_R"].abs() >= EDGE_R)].copy()
print(f"within-study meta-analysis: {len(cons)} pairs in >=2 studies; "
      f"{len(edges_df)} consensus edges (>= {EDGE_N} studies, |mean R| >= {EDGE_R}, "
      f"sign agreement {EDGE_FRAC:.0%})")
edges_df.to_csv(os.path.join(OUT, "network_edges.csv"), index=False, encoding="utf-8-sig")

net_nodes = sorted(set(edges_df["a"]) | set(edges_df["b"]))
# keep the network legible: at most the 26 best-connected compounds
degw = pd.concat([edges_df.groupby("a")["mean_R"].apply(lambda x: x.abs().sum()),
                  edges_df.groupby("b")["mean_R"].apply(lambda x: x.abs().sum())],
                 axis=1).fillna(0).sum(axis=1).sort_values(ascending=False)
net_nodes = list(degw.head(26).index)
edges_df = edges_df[edges_df["a"].isin(net_nodes) & edges_df["b"].isin(net_nodes)]
G = nx.Graph()
for n in net_nodes:
    G.add_node(n, cls=cls_of.get(n, "其他 Other"))
for _, r in edges_df.iterrows():
    G.add_edge(r["a"], r["b"], weight=abs(r["mean_R"]), r=r["mean_R"], ns=int(r["n_studies"]))
print(f"network: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

fig, axes = plt.subplots(1, 2, figsize=(18.5, 8.6),
                         gridspec_kw={"width_ratios": [1.32, 1]})
ax = axes[0]
# layout by metric MDS on the correlation distance (1 - |R|) so that strongly
# co-varying compounds are drawn close together
nodes = list(G.nodes())
nN = len(nodes)
Dm = np.ones((nN, nN))
for u, v, d in G.edges(data=True):
    i, j = nodes.index(u), nodes.index(v)
    Dm[i, j] = Dm[j, i] = 1.0 - d["weight"]
np.fill_diagonal(Dm, 0.0)
from sklearn.manifold import MDS  # noqa: E402
xy = MDS(n_components=2, dissimilarity="precomputed", random_state=3,
         n_init=24, max_iter=900, normalized_stress="auto").fit_transform(Dm)
xy = xy / (np.abs(xy).max() or 1.0)
pos = {n: xy[i] for i, n in enumerate(nodes)}
nx.draw_networkx_edges(
    G, pos, ax=ax,
    edge_color=["#C0392B" if G[u][v]["r"] > 0 else "#2471A3" for u, v in G.edges()],
    width=[.6 + 3.0 * (G[u][v]["weight"] - EDGE_R) / (1 - EDGE_R) for u, v in G.edges()],
    alpha=.7)
nx.draw_networkx_nodes(
    G, pos, ax=ax,
    node_size=[140 + 60 * dict(G.degree())[n] for n in G.nodes()],
    node_color=[CLS_COLOR.get(G.nodes[n]["cls"], "#999") for n in G.nodes()],
    edgecolors="k", linewidths=.55)
nx.draw_networkx_labels(G, pos, ax=ax, font_size=6.9,
                        bbox=dict(facecolor="white", alpha=.72, edgecolor="none", pad=.35))
ax.set_title(f"化合物共现网络（跨文献一致性：≥{EDGE_N} 篇文献同向且 |平均 R| ≥ {EDGE_R}）\n"
             "红边 = 正相关（协同积累），蓝边 = 负相关（此消彼长）；边宽 ∝ 相关强度")
ax.axis("off")
ax.margins(.16)
present_cls = {G.nodes[n]["cls"] for n in G}
ax.legend(handles=[Patch(facecolor=v, edgecolor="k", label=BIO.get(k, k))
                   for k, v in CLS_COLOR.items() if k in present_cls],
          fontsize=8, loc="lower left", title="化合物类别", title_fontsize=8.5)
ax = axes[1]
top_e = edges_df.reindex(edges_df["mean_R"].abs().sort_values(ascending=False).index).head(20)
lbl = [f"{a} — {b}" for a, b in zip(top_e["a"], top_e["b"])]
colors = ["#C0392B" if v > 0 else "#2471A3" for v in top_e["mean_R"]]
ax.barh(lbl[::-1], top_e["mean_R"][::-1], color=colors[::-1], edgecolor="k", linewidth=.35)
for i, (v, n) in enumerate(zip(top_e["mean_R"][::-1], top_e["n_studies"][::-1])):
    ax.text(v + (.02 if v > 0 else -.02), i, f"{v:+.2f} (n={n})",
            va="center", ha="left" if v > 0 else "right", fontsize=6.6)
ax.axvline(0, c="k", lw=.9)
ax.set_xlim(-1.05, 1.28)
ax.set_xlabel("跨文献合并平均 R（Fisher z）")
ax.set_title("一致性最强的化合物对（Top 20）")
ax.tick_params(axis="y", labelsize=7.0)
fig.suptitle("图 11  化合物之间的共现关系网络（文献内相关 + 跨文献一致性检验）",
             y=1.0, fontsize=13.5)
fig.savefig(os.path.join(FIG, "fig11_correlation_network.png"))
plt.close(fig)

# ===========================================================================
# 8. aging axis: trend + PLSR/VIP (the only real Y available in this library)
# ===========================================================================
AGE = {
    9: {"Y1": 1, "Y3": 3, "Y5": 5, "Y8": 8, "Y11": 11},          # study 2 columns
    8: {"X0": 0, "X1": 1, "X3": 3, "X5": 5, "X8": 8},            # study 18 columns
    7: {"2 年陈": 2, "3 年陈": 3, "5 年陈": 5},                    # study 23 columns
}
age_rows = []
for ci, r in cols.set_index("col_index").iterrows():
    lab = str(r["sample_label"]).strip()
    for _study, m in AGE.items():
        if lab in m:
            age_rows.append(dict(col_index=ci, sample_label=lab, age=m[lab]))
age_map = {r["col_index"]: r["age"] for r in age_rows}
print(f"aging samples with a known age: {len(age_map)} -> {sorted(age_map.values())}")

fig, axes = plt.subplots(1, 2, figsize=(16, 5.8), gridspec_kw={"width_ratios": [1.15, 1]})
ax = axes[0]
focus = [short(x) for x in ["Ethyl Hexanoate", "Ethyl Acetate", "Ethyl Lactate",
                            "Ethyl Butyrate", "Hexanoic acid", "Acetic acid",
                            "3-Methyl-1-butanol", "Ethyl Caprylate"]]
ages = sorted(set(age_map.values()))
trend = {}
for ci, a in age_map.items():
    if ci not in usable_ids:
        continue                      # drop unit-implausible columns (e.g. study 23)
    for n in focus:
        v = wide_use.loc[n, ci] if (n in wide_use.index and ci in wide_use.columns) else np.nan
        if np.isfinite(v) and v > 0:
            trend.setdefault(n, {}).setdefault(a, []).append(v)
for n in focus:
    if n not in trend:
        continue
    xs = sorted(trend[n])
    ys = [np.median(trend[n][a]) for a in xs]
    ax.plot(xs, ys, "o-", ms=4.5, lw=1.4, label=n)
ax.set_yscale("log")
ax.set_xlabel("陈酿年份 / 年"), ax.set_ylabel("中位质量浓度 / (μg/L)")
ax.set_title("关键化合物随陈酿年份的变化（对数纵轴）")
ax.legend(fontsize=6.8, ncol=2)
ax = axes[1]
Xa, ya = [], []
for ci, a in sorted(age_map.items()):
    row = []
    ok = True
    for n in key_short:
        n2 = n if n in wide_use.index else None
        v = wide_use.loc[n2, ci] if (n2 and ci in wide_use.columns) else np.nan
        row.append(v)
    Xa.append(row), ya.append(a)
Xa = pd.DataFrame(Xa, columns=key_short)
ya = np.array(ya, dtype=float)
good = Xa.notna().sum(axis=1) >= 10
Xa, ya = Xa[good], ya[good]
Xa_f = Xa.fillna(Xa.median())
Xa_l = np.log10(np.clip(Xa_f.to_numpy(dtype=float), 1e-2, None))
Xa_s = StandardScaler().fit_transform(Xa_l)
ncomp = min(3, Xa_s.shape[0] - 1, Xa_s.shape[1])
pls = PLSRegression(n_components=ncomp, scale=False).fit(Xa_s, ya)
T = pls.x_scores_
W = pls.x_weights_
Q = pls.y_loadings_
p_, q_ = W.shape
vip = np.sqrt(p_ * ((W / np.linalg.norm(W, axis=0)) ** 2 @ (Q.T ** 2).ravel()) / (Q.T ** 2).sum())
vip_s = pd.Series(vip, index=key_short).sort_values(ascending=False)
vip_s.to_csv(os.path.join(OUT, "vip.csv"), encoding="utf-8-sig")
r2y = 1 - ((ya - pls.predict(Xa_s).ravel()) ** 2).sum() / ((ya - ya.mean()) ** 2).sum()
ax.barh(vip_s.index[::-1], vip_s.values[::-1],
        color=["#C0392B" if v > 1 else "#7F8C8D" for v in vip_s.values[::-1]],
        edgecolor="k", linewidth=.35)
ax.axvline(1, ls="--", c="crimson", lw=1.2)
ax.set_xlabel("VIP 值")
ax.set_title(f"PLSR VIP（Y = 陈酿年份，n={Xa_s.shape[0]}，{ncomp} 成分，R²Y={r2y:.2f}）")
ax.tick_params(axis="y", labelsize=7.2)
fig.suptitle("图 12  陈酿轴：趋势与 PLSR 变量投影重要性（VIP）", y=1.02, fontsize=13)
fig.savefig(os.path.join(FIG, "fig12_aging_vip.png"))
plt.close(fig)

# ===========================================================================
# 9. data-quality dashboard
# ===========================================================================
fig = plt.figure(figsize=(17, 9.6))
gs = fig.add_gridspec(2, 3, hspace=.42, wspace=.28)
# (a) completeness matrix
ax = fig.add_subplot(gs[0, :2])
Mraw = wide_raw.copy()
Mraw = Mraw.loc[present.sort_values(ascending=False).index]
keepc = [c for c in Mraw.columns if c in usable_ids]
Mm = Mraw[keepc]
ax.imshow(Mm.notna().to_numpy(), aspect="auto", cmap="Greys",
          interpolation="nearest", vmin=0, vmax=1.35)
ax.set_yticks(range(len(Mm.index)))
ax.set_yticklabels(Mm.index, fontsize=4.4)
ax.set_xlabel("样品列（%d 个通过单位校验的列）" % len(keepc))
ax.set_ylabel("化合物")
ax.set_title(f"数据完整度矩阵：黑 = 有值  白 = 缺失（{int(Mm.notna().sum().sum())} / "
             f"{Mm.size} = {Mm.notna().mean().mean() * 100:.0f}%）")
ax.grid(False)
# (b) cells per study
ax = fig.add_subplot(gs[0, 2])
perstudy = long.groupby("study_no").size().sort_index()
ax.bar([str(int(s)) for s in perstudy.index], perstudy.values, color="#4C72B0",
       edgecolor="k", linewidth=.3)
ax.set_xlabel("文献编号"), ax.set_ylabel("数值单元数"), ax.set_title("各文献贡献的数据量")
ax.tick_params(axis="x", labelsize=6.5)
# (c) cleaning-flag composition
ax = fig.add_subplot(gs[1, 0])
fc = long["flags"].fillna("").str.split("|").explode().replace("", "正常解析").value_counts()
ax.barh(fc.index[::-1], fc.values[::-1], color="#55A868", edgecolor="k", linewidth=.3)
ax.set_xlabel("单元数"), ax.set_title("单元格清洗标记构成")
ax.tick_params(axis="y", labelsize=7.2)
# (d) issues by type / severity
ax = fig.add_subplot(gs[1, 1])
it = issues.groupby(["issue_type", "severity"]).size().unstack(fill_value=0)
it = it.reindex(columns=[c for c in ["high", "medium", "low"] if c in it.columns])
it.plot(kind="barh", stacked=True, ax=ax,
        color={"high": "#C0392B", "medium": "#E67E22", "low": "#7F8C8D"})
ax.set_xlabel("问题数"), ax.set_ylabel(""), ax.set_title("清洗问题清单")
ax.legend(fontsize=6.8, title="严重度", title_fontsize=7)
ax.tick_params(axis="y", labelsize=7)
# (e) unit verdict
ax = fig.add_subplot(gs[1, 2])
uv = cols["unit_verdict"].value_counts()
ax.pie(uv.values, labels=[f"{k}\n({v})" for k, v in uv.items()], autopct="%1.0f%%",
       colors=["#55A868", "#C0392B", "#7F8C8D"][:len(uv)],
       textprops={"fontsize": 8.5}, wedgeprops={"edgecolor": "w"})
ax.set_title("列单位可信度判定\n（己酸乙酯尺度校验）")
ax.grid(False)
fig.suptitle("图 01  数据清洗总览", y=.96, fontsize=14)
fig.savefig(os.path.join(FIG, "fig01_cleaning_overview.png"))
plt.close(fig)

# ===========================================================================
# 10. reporting-coverage map: compound x study (which study reports what)
# ===========================================================================
pres = long[long["value_mean"].notna()].pivot_table(
    index="name_short", columns="study_no", values="value_mean", aggfunc="size").fillna(0)
pres = pres.loc[pres.sum(axis=1).sort_values(ascending=False).index]
pres.to_csv(os.path.join(OUT, "coverage_compound_by_study.csv"), encoding="utf-8-sig")
fig, ax = plt.subplots(figsize=(15.5, 9.6))
sns.heatmap(pres.gt(0).astype(int), cmap="Blues", cbar=False, linewidths=.3,
            linecolor="#dddddd", ax=ax)
ax.set_xlabel("文献编号"), ax.set_ylabel("")
ax.set_title("文献覆盖图：哪些文献报道了哪些化合物（可用单位列）")
ax.tick_params(axis="y", labelsize=5.6)
fig.savefig(os.path.join(FIG, "fig13_coverage_map.png"))
plt.close(fig)

print("\nfigures written to", FIG)
for f in sorted(os.listdir(FIG)):
    print("  ", f)

# ===========================================================================
# 11. findings summary (markdown fragment consumed by the report)
# ===========================================================================
strong = []
for i, a in enumerate(names):
    for b in names[i + 1:]:
        r, p = corr_R.loc[a, b], corr_P.loc[a, b]
        n_obs = int(NOBS[i, names.index(b)])
        if np.isfinite(r) and p < 0.001 and abs(r) >= 0.75 and n_obs >= 8:
            strong.append((a, b, r, p, n_obs))
strong.sort(key=lambda t: -abs(t[2]))
pd.DataFrame(strong, columns=["compound_A", "compound_B", "R", "p", "n_obs"]).to_csv(
    os.path.join(OUT, "top_correlations.csv"), index=False, encoding="utf-8-sig")

# Benjamini-Hochberg FDR over all testable pairs
tri = [(i, j) for i in range(N) for j in range(i + 1, N) if np.isfinite(P[i, j])]
pv = np.array([P[i, j] for i, j in tri])
order = np.argsort(pv)
m = len(pv)
q = np.empty(m)
prev = 1.0
for rank, idx in enumerate(order[::-1]):
    k = m - rank
    prev = min(prev, pv[idx] * m / k)
    q[idx] = prev
n_fdr = int((q < 0.05).sum())
print(f"\nstrong pairs (|R|>=0.75, p<0.001, n>=8): {len(strong)}")
print(f"pairs testable: {m}; surviving BH-FDR 5%: {n_fdr}")
for a, b, r, p, n in strong[:12]:
    print(f"  {a:<26} {b:<26} R={r:+.3f}  n={n}")
