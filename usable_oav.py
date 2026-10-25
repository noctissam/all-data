# -*- coding: utf-8 -*-
"""基于 OAV>1 判定"实际可用数据" -> 可用数据_OAV大于1.xlsx + 可用数据.txt
  表1 可用化合物汇总   93个 OAV>1>0 的化合物(有效率/分层)
  表2 样品列汇总       113列各自可用点数
  表3 可用数据透视     化合物x样品, 仅填 OAV>1 的值(空=不可用/未达阈值/无阈值)
  表4 无法判定         缺阈值但有数据的化合物(既非可用也非不可用)
"""
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
DB   = BASE + r"\浓香型数据库.xlsx"
OAVF = BASE + r"\OAV核算_周阈值.xlsx"
OUT  = BASE + r"\可用数据_OAV大于1.xlsx"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

db = pd.read_excel(DB, sheet_name="all data")
oav = pd.read_excel(OAVF, sheet_name="OAV")
stat = pd.read_excel(OAVF, sheet_name="化合物统计")
colst = pd.read_excel(OAVF, sheet_name="列统计")
miss = pd.read_excel(OAVF, sheet_name="缺阈值")

base_cols = ["Order ID", "CAS", "Odorants", "中文名称", "SMILES", "Threshold（μg/L）"]
conc_cols = [c for c in db.columns if c not in base_cols and c.endswith("(μg/L)")]
oav_cols = {c: c.replace("(μg/L)", "(OAV)") for c in conc_cols}

# ---- 总量 ----
n_filled = 0
for c in conc_cols:
    n_filled += int(pd.to_numeric(db[c], errors="coerce").fillna(0).gt(0).sum())
n_calc = int(colst["可算OAV"].sum())
n_use = int(colst["OAV>1"].sum())
n_nothr_filled = 0   # 缺阈值化合物占用的有值单元格(无法判定)
idx_thr = stat.set_index("Order ID")["阈值(ppb)"]
for i, r in db.iterrows():
    if not idx_thr.get(r["Order ID"]):
        row = pd.to_numeric(db.loc[i, conc_cols], errors="coerce").fillna(0)
        n_nothr_filled += int(row.gt(0).sum())
n_le1 = n_calc - n_use

w("== 可用性总账(OAV>1 为可用) ==")
w("全库有浓度值单元格: %d (373化合物 x 113样品列)" % n_filled)
w("  有阈值可判定:     %d (%.1f%%)" % (n_calc, 100*n_calc/n_filled))
w("    可用 OAV>1:     %d (占可判定%.1f%%, 占全库有值%.1f%%)" % (
    n_use, 100*n_use/n_calc, 100*n_use/n_filled))
w("    无效 OAV<=1:    %d (占可判定%.1f%%)" % (n_le1, 100*n_le1/n_calc))
w("  缺阈值无法判定:   %d (%.1f%%) <- 见'无法判定'表, 非不可用, 是待补阈值" % (
    n_nothr_filled, 100*n_nothr_filled/n_filled))

# ---- 化合物分层 ----
st = stat[stat["OAV>1列数"] > 0].copy()
st = st.rename(columns={"非0浓度列数": "有值列数"})
st["可算列数"] = stat.loc[st.index, "可算OAV列数"]
st["有效率(可用/可算)"] = (st["OAV>1列数"] / st["可算列数"].replace(0, pd.NA)).astype(float)
def tier(r):
    e = r["有效率(可用/可算)"]
    if e >= 0.8: return "T1 广泛有效(>=80%列)"
    if e >= 0.5: return "T2 多数有效(50-80%)"
    if e >= 0.2: return "T3 部分有效(20-50%)"
    return "T4 少数有效(<20%)"
st["分层"] = st.apply(tier, axis=1)
st = st.sort_values(["OAV>1列数", "有效率(可用/可算)"], ascending=False)
st = st[["Order ID", "Odorants", "中文名称", "阈值(ppb)", "有值列数", "可算列数",
         "OAV>1列数", "有效率(可用/可算)", "分层"]]
for t in ["T1 广泛有效(>=80%列)", "T2 多数有效(50-80%)", "T3 部分有效(20-50%)",
          "T4 少数有效(<20%)"]:
    sub = st[st["分层"] == t]
    w("")
    w("== %s: %d个化合物 ==" % (t, len(sub)))
    for _, r in sub.head(12).iterrows():
        w("  %-45s %-14s 阈值=%-10s 可用%d/%d列" % (
            str(r["Odorants"])[:45], str(r["中文名称"])[:14], r["阈值(ppb)"],
            r["OAV>1列数"], r["可算列数"]))
    if len(sub) > 12:
        w("  ... 其余%d个见 可用化合物汇总表" % (len(sub) - 12))

# ---- 样品列 ----
cs = colst.sort_values("OAV>1", ascending=False).copy()
cs["可用率(可用/可算)"] = (cs["OAV>1"] / cs["可算OAV"].replace(0, pd.NA)).astype(float)
w("")
w("== 样品列可用点数分布 ==")
w("最大=%d (%s)  最小=%d (%s)  中位=%d" % (
    int(cs["OAV>1"].max()), cs.iloc[0]["浓度列"][:40],
    int(cs["OAV>1"].min()), cs.iloc[-1]["浓度列"][:40],
    int(cs["OAV>1"].median())))
w("可用点数<=5 的样品列(%d个):" % int((cs["OAV>1"] <= 5).sum()))
for _, r in cs[cs["OAV>1"] <= 5].iterrows():
    w("  %s | 有值%d 可算%d 可用%d" % (r["浓度列"], r["有浓度值"], r["可算OAV"], r["OAV>1"]))
w("")
w("可用点数 TOP10 样品列:")
for _, r in cs.head(10).iterrows():
    w("  %-40s 可用%d/%d可算" % (r["浓度列"], r["OAV>1"], r["可算OAV"]))

# ---- 透视: 可用数据 ----
piv = oav[["Order ID", "CAS", "Odorants", "中文名称", "阈值(ppb)"]].copy()
_new = {}
for c in conc_cols:
    oc = oav_cols[c]
    s = oav[oc] if oc in oav.columns else pd.Series([None]*len(oav))
    s = pd.to_numeric(s, errors="coerce")
    _new[c] = s.where(s > 1, "")
piv = pd.concat([piv, pd.DataFrame(_new, index=oav.index)], axis=1)
n_use2 = int(sum(
    int(pd.to_numeric(piv[c], errors="coerce").gt(1).sum()) for c in conc_cols))

# ---- 无法判定 ----
nothr = miss[miss["非0浓度列数"] > 0].sort_values("非0浓度列数", ascending=False)
nothr = nothr[["Order ID", "CAS", "Odorants", "中文名称", "缺失原因", "非0浓度列数"]]

with pd.ExcelWriter(OUT, engine="openpyxl") as wri:
    st.to_excel(wri, sheet_name="可用化合物汇总", index=False)
    cs.to_excel(wri, sheet_name="样品列汇总", index=False)
    piv.to_excel(wri, sheet_name="可用数据透视(OAV>1)", index=False)
    nothr.to_excel(wri, sheet_name="无法判定(缺阈值)", index=False)

w("")
w("透视表可用点核对: %d (应=%d)" % (n_use2, n_use))
w("")
w("== 结论 ==")
w("1) 可直接使用(OAV>1): %d个数据点, 覆盖 %d个化合物 x %d个样品列" % (
    n_use, int((st["OAV>1列数"] > 0).sum()), int((cs["OAV>1"] > 0).sum())))
w("2) 可判定但无效(OAV<=1): %d个 -> 化合物虽有浓度但未达嗅觉阈值, 不作关键香气物质" % n_le1)
w("3) 无法判定(缺阈值): %d个数据点, %d个化合物 -> 补阈值后可重新判定, 不等于不可用" % (
    n_nothr_filled, len(nothr)))
w("4) T1+T2化合物(>=50%%列有效)共%d个, 可作为该批样品的稳健关键香气物质候选" % int(
    (st["分层"].str.startswith(("T1", "T2"))).sum()))

with open(BASE + r"\可用数据.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE -> 可用数据_OAV大于1.xlsx / 可用数据.txt")
