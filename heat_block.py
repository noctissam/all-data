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
cax = fig.add_axes([0.035, 0.80, 0.006, 0.10])
cb = fig.colorbar(im, cax=cax); cb.set_label("z-score", fontsize=8)
cb.ax.tick_params(labelsize=7)
lg = fig.add_axes([0.055, 0.80, 0.09, 0.10]); lg.axis("off")
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
ax.yaxis.tick_right()
ax.tick_params(length=0)
ax.set_title("文献层面均值热图（41化合物 × 27文献，按文献内样品均值）", fontsize=12)
cb2 = fig.colorbar(im2, ax=ax, fraction=0.03, pad=0.02); cb2.set_label("z-score", fontsize=8)
fig.tight_layout(); fig.savefig(OUTD + r"\6_文献均值热图.png", dpi=200); plt.close(fig)

