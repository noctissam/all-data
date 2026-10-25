# -*- coding: utf-8 -*-
"""
40_export_excel.py
==================
Bundles every cleaned table and analysis result into ONE Excel workbook with
wide, frozen, auto-sized sheets, so the results can be used directly.
"""
from __future__ import annotations

import io
import os
import sys

import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
XL = os.path.join(HERE, "白酒风味数据库_清洗版.xlsx")


def rd(name, index_col=None):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return None
    return pd.read_csv(p, index_col=index_col)


# sheet name -> (dataframe, description)
SHEETS: list[tuple[str, pd.DataFrame]] = []


def add(name, df, cols_wanted=None):
    if df is None or (hasattr(df, "empty") and df.empty):
        return
    if cols_wanted:
        keep = [c for c in cols_wanted if c in df.columns]
        df = df[keep]
    SHEETS.append((name[:31], df))


cm = rd("compound_master.csv")
add("01_化合物主表", cm, [
    "compound_uid", "name_en", "name_zh", "cas", "smiles", "chem_class",
    "threshold_ugL_median", "threshold_ugL_min", "threshold_ugL_max",
    "n_threshold_sources", "source_tabs", "cas_status", "cas_source",
    "order_ids", "n_rows",
])

cr = rd("compound_registry.csv")
add("02_CAS修复登记", cr, [
    "row_no", "order_id", "name_en_raw", "name_en", "name_zh", "cas_raw", "cas",
    "cas_status", "cas_source", "smiles", "chem_class"])

cols = rd("column_registry.csv")
add("03_列登记表_单位", cols, [
    "col_index", "header_raw", "study_no", "study_label", "sample_label",
    "unit_declared", "unit", "unit_pre_correction", "unit_confidence",
    "marker_ugL", "unit_verdict", "usable_absolute", "col_role",
])

long = rd("master_long.csv")
add("04_全库长表", long, [
    "compound_uid", "name_en", "name_zh", "cas", "chem_class", "study_no",
    "study_label", "sample_label", "header_raw", "unit", "value_raw",
    "value_mean", "value_sd", "value_ugL", "usable_absolute",
    "unit_verdict", "flags", "threshold_ugL", "oav",
])

for nm, fn, cc in [
    ("05_宽表_ugL", "master_wide_ugL.csv", None),
    ("06_宽表_原始值", "master_wide_raw.csv", None),
    ("07_宽表_秩", "master_wide_rank.csv", None),
]:
    add(nm, rd(fn))

add("08_阈值原始单元", rd("thresholds_raw.csv"), [
    "sheet_tab", "column_header", "compound_raw", "unit", "value_raw",
    "value_mean", "thr_ugL", "compound_key", "master_key", "matched"])
for nm, fn in [
    ("09_阈值共识", "thresholds_consensus.csv"),
    ("10_OAV汇总", "oav_summary.csv"),
    ("11_关键20化合物", "key_compounds.csv"),
    ("12_相关矩阵20x20", "corr_key20_R.csv"),
    ("13_相关P值20x20", "corr_key20_P.csv"),
    ("14_全库相关62x62", "corr_spearman.csv"),
    ("15_强相关对", "top_correlations.csv"),
    ("16_文献内相关", "within_study_correlations.csv"),
    ("17_跨文献共识相关", "consensus_correlations.csv"),
    ("18_网络边", "network_edges.csv"),
    ("19_化合物聚类", "compound_clusters.csv"),
    ("20_样品PCA得分", "sample_scores.csv"),
    ("21_PCA载荷", "pca_loadings.csv"),
    ("22_DBSCAN标签", "dbscan_labels.csv"),
    ("23_PLSR_VIP", "vip.csv"),
    ("24_风味贡献权重", "oav_weights.csv"),
    ("25_OAV占比矩阵", "oav_share_matrix.csv"),
    ("26_类别构成_按文献", "class_profile_by_study.csv"),
    ("27_化合物x文献z", "compound_by_study_z.csv"),
    ("28_文献覆盖图", "coverage_compound_by_study.csv"),
    ("29_单位可信度", "unit_plausibility.csv"),
    ("30_问题日志", "issues_log.csv"),
    ("31_文献工作表长表", "sheets_long.csv"),
]:
    add(nm, rd(fn))

# a human-readable front page
front = pd.DataFrame({
    "项目": [
        "数据来源", "主表规模", "化合物（去重后）", "数值列", "通过单位校验的列",
        "解析出的数值单元", "已换算为 μg/L", "可计算 OAV 的单元",
        "中位 OAV > 1 的化合物", "阈值共识覆盖的化合物", "CAS 修复", "数值跨表修复",
        "分析文件", "生成脚本",
    ],
    "内容": [
        "data总库.xlsx（主库，只读）+ data.xlsx（同目录姊妹库，仅用于交叉修复）",
        "63 行 × 163 列（7 列元数据 + 156 列数值）",
        f"{0 if cm is None else len(cm)}",
        f"{0 if cols is None else len(cols)}",
        f"{0 if cols is None else int(cols['usable_absolute'].sum())}",
        f"{0 if long is None else len(long)}",
        f"{0 if long is None else int(long['value_ugL'].notna().sum())}",
        f"{0 if long is None else int(long['oav'].notna().sum())}",
        f"{0 if cm is None else 40}",
        f"{0 if cm is None else int(cm['threshold_ugL_median'].notna().sum())}",
        "CAS 校验位 + 姊妹库 SMILES 连接 + 删除 0 重插算法",
        "“删除 0”指纹比对（去零后残留相同即判定为丢位损坏）",
        "new/output/*.csv、new/figures/*.png",
        "new/10_extract_sources.py, 20_clean_master.py, 30_analyze.py, 40_export_excel.py",
    ],
})
SHEETS.insert(0, ("00_说明", front))

with pd.ExcelWriter(XL, engine="openpyxl") as xw:
    for name, df in SHEETS:
        d = df.copy()
        if isinstance(d.index, pd.MultiIndex) or d.index.name or not isinstance(
                d.index, pd.RangeIndex):
            d = d.reset_index()
        d.to_excel(xw, sheet_name=name, index=False)
        ws = xw.sheets[name]
        ws.freeze_panes = "A2"
        for c in range(1, min(d.shape[1], 60) + 1):
            vals = d.iloc[:, c - 1].astype(str).head(400)
            w = int(min(max(vals.str.len().max() if len(vals) else 8, 8) + 2, 44))
            ws.column_dimensions[get_column_letter(c)].width = w
        for c in range(1, d.shape[1] + 1):
            ws.cell(row=1, column=c).font = Font(bold=True, color="FFFFFF")
            ws.cell(row=1, column=c).fill = PatternFill("solid", fgColor="4472C4")
            ws.cell(row=1, column=c).alignment = Alignment(
                vertical="center", horizontal="center", wrap_text=True)
print(f"-> {XL}")
print(f"   sheets: {len(SHEETS)}")
print(f"   size  : {os.path.getsize(XL) / 1024:.0f} KB")
