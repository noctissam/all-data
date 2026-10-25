# -*- coding: utf-8 -*-
"""提取 OAV>1 判定为可用的93行化合物 -> 可用化合物数据.xlsx
  只保留: 基础信息 + 周表阈值(标注, 不算OAV) + 113个浓度列原始值(μg/L)
  表1 可用化合物数据   按 OAV>1列数 降序
  表2 阈值与匹配       阈值来源/匹配用名称/匹配方式
  表3 说明             口径与统计
"""
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
DB   = BASE + r"\浓香型数据库.xlsx"
USE  = BASE + r"\可用数据_OAV大于1.xlsx"
OAVF = BASE + r"\OAV核算_周阈值.xlsx"
OUT  = BASE + r"\可用化合物数据.xlsx"

db = pd.read_excel(DB, sheet_name="all data")
use = pd.read_excel(USE, sheet_name="可用化合物汇总")
mat = pd.read_excel(OAVF, sheet_name="匹配明细")   # Order ID, 中文名称, 匹配用名称, 阈值(ppb), 匹配方式

base_cols = ["Order ID", "CAS", "Odorants", "中文名称", "SMILES", "Threshold（μg/L）"]
conc_cols = [c for c in db.columns if c not in base_cols and c.endswith("(μg/L)")]

ids = list(use["Order ID"])
sub = db[db["Order ID"].isin(ids)].copy()

# 合并 阈值/匹配方式/可用列数
m = mat.set_index("Order ID")
sub["阈值(ppb)"] = sub["Order ID"].map(m["阈值(ppb)"])
sub["阈值匹配用名称"] = sub["Order ID"].map(m["匹配用名称"])
sub["阈值匹配方式"] = sub["Order ID"].map(m["匹配方式"])
u = use.set_index("Order ID")
sub["OAV>1列数(仅用于排序)"] = sub["Order ID"].map(u["OAV>1列数"])
sub["有效率"] = sub["Order ID"].map(u["有效率(可用/可算)"])
sub["分层"] = sub["Order ID"].map(u["分层"])
sub = sub.sort_values("OAV>1列数(仅用于排序)", ascending=False)

cols = (["Order ID", "CAS", "Odorants", "中文名称", "SMILES",
         "阈值(ppb)", "阈值匹配用名称", "阈值匹配方式"]
        + ["分层", "OAV>1列数(仅用于排序)", "有效率"]
        + conc_cols)
main = sub[cols].reset_index(drop=True)

thrsheet = (sub[["Order ID", "Odorants", "中文名称", "阈值(ppb)",
                 "阈值匹配用名称", "阈值匹配方式", "分层",
                 "OAV>1列数(仅用于排序)", "有效率"]]
            .reset_index(drop=True))

n_thr = int(sub["阈值(ppb)"].notna().sum())
n_cells = sum(int(pd.to_numeric(sub[c], errors="coerce").fillna(0).gt(0).sum())
              for c in conc_cols)
notes = [
    ["提取对象", "OAV>1 判定为可用的 %d 行化合物记录(独立化合物约85个)" % len(main)],
    ["浓度单位", "μg/L (=ppb, 水溶液基准), 与周表阈值同量纲; 数值为原库原始浓度, 未做任何换算"],
    ["阈值列", "阈值(ppb) 来自 阈值.xlsx 第2个表单'周'(共120条), 仅标注, 不计算OAV"],
    ["OAV", "本表不计算OAV; 判定过程见 OAV核算_周阈值.xlsx / 可用数据_OAV大于1.xlsx"],
    ["排序", "按 OAV>1列数 降序(可用性从高到低)"],
    ["数据规模", "%d化合物 x %d浓度列, 非空浓度值 %d 个" % (len(main), len(conc_cols), n_cells)],
    ["阈值覆盖", "%d/%d 行有周表阈值" % (n_thr, len(main))],
    ["来源", "浓香型数据库.xlsx(all data) + 阈值.xlsx('周') + 可用数据_OAV大于1.xlsx"],
]
notes_df = pd.DataFrame(notes, columns=["项目", "说明"])

with pd.ExcelWriter(OUT, engine="openpyxl") as wri:
    main.to_excel(wri, sheet_name="可用化合物数据", index=False)
    thrsheet.to_excel(wri, sheet_name="阈值与匹配", index=False)
    notes_df.to_excel(wri, sheet_name="说明", index=False)

print("DONE rows=%d cols=%d thr=%d cells=%d -> %s"
      % (len(main), len(main.columns), n_thr, n_cells, OUT))
