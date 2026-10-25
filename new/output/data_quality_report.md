# 数据质量报告 — data总库.xlsx

本报告由 `new/20_clean_master.py` 自动生成；源文件只读，未被修改。

## 1. 数据规模

| 项目 | 数量 |
|---|---|
| 主表原始行（含表头） | 64 |
| 主表原始列 | 163 |
| 元数据列 | 7 |
| 数值列（文献/样品） | 156 |
| 非空数值列 | 156 |
| 化合物原始行 | 63 |
| 去重后化合物 | 62 |
| 文献工作表（sheet tab） | 12 |
| 解析出的数值单元 | 5330 |
| 可换算为 μg/L 的单元 | 5018 |

## 2. 清洗动作清单

### 2.1 CAS 号修复

| 状态 | 行数 | 含义 |
|---|---|---|
| repaired_sibling | 33 | 由 data.xlsx（按 SMILES 连接）取回正确值 |
| ok | 30 | 原始值即通过 CAS 校验位 |

主要损坏模式（详见 `issues_log.csv`）：

- **缺失的 0 被 Excel 删除**：`18-64-5` → `108-64-5`、`15-54-4` → `105-54-4`、`17-92-6` → `107-92-6`
- **被 Excel 识别为日期**：`3658-80-8` → `3658-08-08 00:00:00`；`106-30-9` → `216/3/9`；`106-70-7` → `216/7/7`
- **破折号混用**：`16–32–1`（en dash）应为 `106-32-1`
- **前导数字丢失**：`221-28-5`（无效）应为 `2021-28-5`；`51-52-` 应为 `501-52-0`

### 2.2 化合物名称规范化

| 原始名 | 规范名 | 说明 |
|---|---|---|
| `hexanole acid` | `Hexanoic acid` | 拼写/同义词纠正 |
| `pentanole acid` | `Pentanoic acid` | 拼写/同义词纠正 |
| `isovalenic acid` | `Isovaleric acid` | 拼写/同义词纠正 |
| `gamma-nonanolactone` | `gamma-Nonanolactone` | 拼写/同义词纠正 |
| `ethyl 4-methyl valerate` | `Ethyl 4-methylvalerate` | 拼写/同义词纠正 |
| `3-methylbutyl hexanoate/isoamyl hexanoate` | `Isoamyl hexanoate` | 拼写/同义词纠正 |
| `2-methylpropionic acid/isobutyric acid` | `2-Methylpropionic acid` | 拼写/同义词纠正 |
| `4-methylvaleric acid` | `4-Methylvaleric acid` | 拼写/同义词纠正 |
| `(e)-2-octenal` | `(E)-2-Octenal` | 拼写/同义词纠正 |
| `2-(ethoxymethyl)furan` | `2-(Ethoxymethyl)furan` | 拼写/同义词纠正 |
| `trimethyl-pyrazine` | `Trimethylpyrazine` | 拼写/同义词纠正 |
| `ethyl 3-phenylpropionate` | `Ethyl 3-phenylpropionate` | 拼写/同义词纠正 |
| `3-phenyl propionic acid` | `3-Phenylpropionic acid` | 拼写/同义词纠正 |

检测到 **2 行** 重复化合物（同一身份键），已合并：

| 化合物 | 原始 Order ID |
|---|---|
| 4-methylvaleric acid | 35, 53 |

### 2.3 单位统一

所有浓度按列单位换算为 μg/L：

| 单位 | 换算系数 → μg/L |
|---|---|
| ug/l | ×1 |
| μg/l | ×1 |
| ug/ml | ×1000 |
| μg/ml | ×1000 |
| ug/ml_ | ×1000 |
| mg/l | ×1000 |
| mg/ml | ×1e+06 |
| g/l | ×1e+06 |
| mg/100ml | ×10000 |
| mg/100g | ×10000 |

- 表头显式声明单位：**86** 列
- 由对应文献工作表推断：**57** 列
- 单元格内自带单位：**1** 个单元
- 单位未知：**0** 列（仅参与秩相关等无量纲分析）

### 2.4 缺失值与非数值编码

| 标记 | 单元数 | 含义与处理 |
|---|---|---|
| `clean` | 5234 | 正常解析 |
| `missing_code` | 96 | NF / ND / — / \ / (空) / N/D 等占位符 → 置为缺失 |

### 2.5 阈值补全与 OAV

主表 `Threshold` 与 `Concentration（μg/L）` 两列在源文件中**完全为空**。
本次从 12 个文献工作表中抽取了 **306** 个阈值单元，覆盖 238 个文献名，成功匹配 **55** 个主表化合物。

| 项目 | 数量 |
|---|---|
| 阈值单元 | 306 |
| 匹配到主表化合物 | 55 |
| 未匹配（文献独有化合物/拼写差异） | 131 |
| 可计算 OAV 的浓度单元 | 3304 |
| 中位 OAV > 1 的化合物 | 40 |

## 3. 问题清单（按严重度）

严重 high: 115 项；中等 medium: 78 项；轻微 low: 2 项。完整清单见 `issues_log.csv`。

## 4. 产出文件

| 文件 | 内容 |
|---|---|
| `sheets_long.csv` | 12 个文献工作表的整洁长表（复现 10_extract_sources.py 的结果） |
| `compound_registry.csv` | 化合物逐行登记（含 CAS 修复状态与来源） |
| `compound_master.csv` | 去重后的化合物主表（含化学类别与阈值） |
| `column_registry.csv` | 列登记表：研究编号 / 样品 / 单位 / 单位置信度 |
| `master_long.csv` | 全库整洁长表：每个浓度单元一行，含 μg/L 换算值与 OAV |
| `master_wide_raw.csv` | 宽表（原始数值） |
| `master_wide_ugL.csv` | 宽表（统一为 μg/L） |
| `master_wide_rank.csv` | 宽表（列内百分位秩，无量纲，用于跨单位相关分析） |
| `thresholds_raw.csv` | 从文献表抽取的全部阈值单元 |
| `thresholds_consensus.csv` | 化合物阈值共识值（取多来源中位数） |
| `oav_summary.csv` | OAV 汇总：中位/最大 OAV、OAV>1 样品比例 |
| `issues_log.csv` | 问题日志（类型/严重度/范围/细节/处理） |