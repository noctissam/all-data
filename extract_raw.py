# -*- coding: utf-8 -*-
"""可用化合物的【完整原始数据】-> 可用化合物原始数据.xlsx
  严格照搬 浓香型数据库.xlsx 'all data':
    93行(OAV>1判定可用) x 全部144原列(含原Threshold列、113浓度列、25文献OAV列)
    原行序(Order ID升序)、原列序、原数值, 不做任何换算/增删数值
  仅在 Threshold（μg/L） 之后插1列: 阈值(ppb,周表)  —— 标注用, 不计算OAV
"""
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
DB   = BASE + r"\浓香型数据库.xlsx"
USE  = BASE + r"\可用数据_OAV大于1.xlsx"
OAVF = BASE + r"\OAV核算_周阈值.xlsx"
OUT  = BASE + r"\可用化合物原始数据.xlsx"

db  = pd.read_excel(DB, sheet_name="all data")
use = pd.read_excel(USE, sheet_name="可用化合物汇总")
mat = pd.read_excel(OAVF, sheet_name="匹配明细")

# 筛选: 保留可用性排名中 "1-辛烯-3-醇" 及以上(OAV>1列数 >= 17)的化合物
CUTOFF_NAME = "1-辛烯-3-醇"
rk = use.sort_values(["OAV>1列数", "有效率(可用/可算)"], ascending=False).reset_index(drop=True)
hit = rk[rk["中文名称"].astype(str).str.contains(CUTOFF_NAME, na=False)].index[0]
CUT = int(rk.loc[hit, "OAV>1列数"])
rank_map = {r["Order ID"]: i + 1 for i, r in rk.iterrows()}
keep_ids = list(rk[rk["OAV>1列数"] >= CUT]["Order ID"])
print("cutoff=%s OAV>1列数>=%d 保留=%d行" % (CUTOFF_NAME, CUT, len(keep_ids)))

ids = keep_ids
sub = db[db["Order ID"].isin(ids)].sort_values("Order ID").reset_index(drop=True)

# 插入 阈值(周表) 标注列, 紧跟原 Threshold（μg/L）
thr = sub["Order ID"].map(mat.set_index("Order ID")["阈值(ppb)"])
pos = list(db.columns).index("Threshold（μg/L）") + 1
sub.insert(pos, "阈值(ppb,周表)", thr)

# 阈值来源明细(供核对)
idx = mat.set_index("Order ID")
u = use.set_index("Order ID")
tsrc = pd.DataFrame({
    "可用排名": sub["Order ID"].map(rank_map),
    "Order ID": sub["Order ID"],
    "Odorants": sub["Odorants"],
    "中文名称": sub["中文名称"],
    "阈值(ppb,周表)": sub["阈值(ppb,周表)"],
    "OAV>1列数": sub["Order ID"].map(u["OAV>1列数"]),
    "匹配用名称": sub["Order ID"].map(idx["匹配用名称"]),
    "匹配方式": sub["Order ID"].map(idx["匹配方式"]),
    "周表文件": r"26.10\英文\阈值.xlsx 第2表单'周'",
}).sort_values("可用排名")

orig_cols = list(db.columns)
conc_cols = [c for c in db.columns if c.endswith("(μg/L)")]

# OAV 版: 形式与原始数据完全一致, 仅把 113 个浓度列换成 OAV=浓度(μg/L)/周表阈值(ppb)
oavsh = sub.copy()
for c in conc_cols:
    v = pd.to_numeric(oavsh[c], errors="coerce")
    oavsh[c] = (v / sub["阈值(ppb,周表)"]).round(3)
    oavsh = oavsh.rename(columns={c: c.replace("(μg/L)", "(OAV)")})
# 注: 列名带括号的 "(OAV)" = 本次计算; 原始25列 " OAV"(不带括号) = 文献原报告值, 原样保留

notes = pd.DataFrame([
    ["筛选", "可用性排名(按OAV>1列数降序)中 '%s' 及以上: OAV>1列数>=%d, 保留 %d 行" % (CUTOFF_NAME, CUT, len(sub))],
    ["数据范围", "浓香型数据库.xlsx 'all data' 中上述化合物的完整原始行"],
    ["完整性", "全部 %d 个原始列, 原列序原行序, 数值未做任何改动" % len(orig_cols)],
    ["新增列", "仅 1 列: 阈值(ppb,周表), 来自 阈值.xlsx 第2表单'周'(共120条), 插在 Threshold（μg/L） 之后"],
    ["OAV", "'all data' 表不含计算OAV; 另建表单'OAV(周阈值)': 形式与本表完全一致, 仅113个浓度列换成 OAV=浓度(μg/L)/周表阈值(ppb)"],
    ["OAV列名", "带括号 '(OAV)' = 本次计算; 原始25列 ' OAV'(不带括号) = 文献原报告值, 两张表均原样保留"],
    ["浓度单位", "μg/L(=ppb); 文献OAV列无量纲; 阈值列单位 ppb"],
    ["规模", "%d行 x %d列(原%d列+1阈值标注列)" % (len(sub), len(sub.columns), len(orig_cols)),
     ],
    ["来源", "浓香型数据库.xlsx + 阈值.xlsx('周') + 可用数据_OAV大于1.xlsx(筛选依据)"],
], columns=["项目", "说明"])

with pd.ExcelWriter(OUT, engine="openpyxl") as wri:
    sub.to_excel(wri, sheet_name="all data", index=False)
    oavsh.to_excel(wri, sheet_name="OAV(周阈值)", index=False)
    tsrc.to_excel(wri, sheet_name="阈值来源", index=False)
    notes.to_excel(wri, sheet_name="说明", index=False)

print("DONE rows=%d cols=%d(原%d+1) oav_sheet=%s -> %s" % (
    len(sub), len(sub.columns), len(orig_cols), oavsh.shape, OUT))
