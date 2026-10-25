# new/ —— 浓香型白酒风味数据库：清洗与关系挖掘

本目录是 `data总库.xlsx`（主库）与 `data.xlsx`（姊妹库）的**清洗、校验与关系挖掘成果**。
**两个源文件均为只读，未被修改。**

## 先看这两个文件

| 文件 | 说明 |
|---|---|
| [`数据清洗与关系挖掘报告.md`](数据清洗与关系挖掘报告.md) | **主报告**：数据理解 → 清洗方法与发现 → 关系挖掘结果 → 对课题的建议 |
| [`白酒风味数据库_清洗版.xlsx`](白酒风味数据库_清洗版.xlsx) | **32 个工作表的汇总成果**，含清洗后的宽表、相关矩阵、聚类、OAV 权重表、问题日志 |

## 图（`figures/`）

| 图 | 内容 |
|---|---|
| [`fig01_cleaning_overview.png`](figures/fig01_cleaning_overview.png) | 数据清洗总览 |
| [`fig02_corr20_significance.png`](figures/fig02_corr20_significance.png) | **20×20 关键化合物相关矩阵（含显著性）** |
| [`fig03_corr_full_clustered.png`](figures/fig03_corr_full_clustered.png) | 62×62 全库聚类相关矩阵 |
| [`fig04_dendrogram_compounds.png`](figures/fig04_dendrogram_compounds.png) | **变量级层次聚类（5 个变量组）** |
| [`fig05_pca_samples.png`](figures/fig05_pca_samples.png) | 样品 PCA |
| [`fig06_dbscan_samples.png`](figures/fig06_dbscan_samples.png) | **DBSCAN 有效样本簇 / 离群** |
| [`fig07_sample_dendrogram.png`](figures/fig07_sample_dendrogram.png) | 样品层次聚类 |
| [`fig08_threshold_oav.png`](figures/fig08_threshold_oav.png) | **阈值—浓度—OAV** |
| [`fig09_flavor_weights.png`](figures/fig09_flavor_weights.png) | **风味贡献权重表** |
| [`fig10_compound_study_landscape.png`](figures/fig10_compound_study_landscape.png) | 化合物 × 文献景观 |
| [`fig11_correlation_network.png`](figures/fig11_correlation_network.png) | **共现网络（跨文献一致性检验）** |
| [`fig12_aging_vip.png`](figures/fig12_aging_vip.png) | 陈酿趋势 + PLSR VIP |
| [`fig13_coverage_map.png`](figures/fig13_coverage_map.png) | 文献覆盖图 |

## 脚本（按顺序执行）

环境：`C:\anaconda\python.exe`（含 pandas / numpy / scipy / sklearn / matplotlib / seaborn / networkx / openpyxl）

```powershell
$py = "C:\anaconda\python.exe"
& $py new\10_extract_sources.py    # 12 个文献工作表 → 整洁长表
& $py new\20_clean_master.py       # 主库清洗：CAS / 名称 / 单位 / 数值修复 / 阈值 / OAV
& $py new\30_analyze.py            # 关系挖掘 + 全部绘图
& $py new\40_export_excel.py       # 汇总导出 Excel
```

| 脚本 | 作用 |
|---|---|
| `cleanlib.py` | 共享原语：CAS 校验位与修复、单元格数值解析、单位换算、化学分类、表头解析 |
| `10_extract_sources.py` | 自动识别文献工作表中的并列数据块（一次运行解析出 13 个逻辑表、4 174 个数值单元） |
| `20_clean_master.py` | 主库清洗主流程，输出 `data_quality_report.md` 与 `issues_log.csv` |
| `30_analyze.py` | 相关 / 聚类 / PCA / DBSCAN / PLSR-VIP / 网络 / 权重表 + 13 张图 |
| `40_export_excel.py` | 汇总为一个 Excel |

## 中间产物（`output/`）

约 30 个 CSV，关键几个：

- `compound_master.csv` —— 62 个化合物主表（CAS、SMILES、类别、阈值）
- `column_registry.csv` —— 156 列登记表（文献 / 样品 / 单位 / 可信度 / 可用性）
- `master_long.csv` / `master_wide_ugL.csv` —— 全库长表 / 统一 μg/L 宽表
- `thresholds_consensus.csv` / `oav_summary.csv` —— 阈值共识 / OAV 汇总
- `corr_key20_R.csv`、`corr_key20_P.csv` —— 20×20 相关矩阵与 P 值
- `consensus_correlations.csv`、`network_edges.csv` —— 文献内相关与稳健边
- `oav_weights.csv` —— 风味贡献权重表
- `issues_log.csv`、`data_quality_report.md` —— 195 条清洗问题日志与质量报告

## 三条最重要的结论

1. **CAS 与浓度数值都曾被"删除所有 0"破坏**：33 行 CAS、100 个数值单元已被精确还原（CAS 现在 100% 通过校验位）。
2. **主库的整合率只有 18%**：12 个文献工作表里有 341 个不同化合物，主矩阵只整合了 62 个，**281 个已录入的化合物尚未进库**。
3. **数据库缺少感官 Y 矩阵**（`Threshold` 列为空、没有 QDA/RATA 评分），所以 PLSR/VIP 与符号回归目前无法真正执行；本目录已把 X 侧准备好，并给出 OAV 权重表作为基线。

## scratch/

调试脚本与四份课题文档的阅读笔记（`context_notes.md`），**不是交付物**。
