# -*- coding: utf-8 -*-
"""单位定标:对比 清洗后数据 与 data总库分表 的同化合物数值, 识别倍数关系
分表表头单位是原文献单位; 若清洗数据=分表值 -> 同单位; 若差1000/1e6 -> 需换算
"""
import re
import math
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
REF = BASE + r"\data总库.xlsx"
SRC = BASE + r"\清洗后数据.xlsx"
OUT = BASE + r"\calib.txt"

def parse_num(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return math.nan
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    m = re.match(r"^([<>]?)\s*([-+]?\d[\d,]*\.?\d*)", s)
    if m:
        try:
            return float(m.group(2).replace(",", ""))
        except ValueError:
            return math.nan
    try:
        return float(s)
    except ValueError:
        return math.nan

def norm_cas(c):
    if c is None or (isinstance(c, float) and math.isnan(c)):
        return None
    s = str(c).strip().replace("–", "-").replace("—", "-").replace(" ", "")
    return s if re.fullmatch(r"[\d\-]+", s) else None

# 清洗后数据
src = pd.read_excel(SRC, sheet_name="清洗后数据")
src["CASk"] = src["CAS号"].apply(norm_cas)

# 挑选有分表的文献做定标: (清洗后数据文献名, 分表名, 分表浓度列, 单位)
checks = [
    ("Characterization of key odorants causing the roasted and mud-like aromas in",
     "2  Characterization of key odor", ["LZ–2016 base SAB (Mean ± SD)", "GJ–1573 (Mean ± SD)"], "μg/L"),
    ("Decoding the Molecular Mechanism of Cellar Aroma Loss",
     "2  Decoding the Molecular Mecha", ["Concentration LZLJ-M7 (Mean ± SD)", "Concentration LZLJ-T7 (Mean ± SD)"], "μg/L"),
    ("Impact of Pulsed Electric Fields Combined with Dissolved",
     "5  Impact of Pulsed Electric Fi", ["Blank (mg/L)", "S1 (mg/L)", "S2 (F3) (mg/L)", "S3 (mg/L)", "F1 (mg/L)", "F3 (mg/L)"], "mg/L"),
    ("Exploration of key aroma active compounds in strong flavor Baijiu during",
     "8  Exploration of key aroma act", [f"Concentration (mg/L) - {i}" for i in range(1, 9)], "mg/L"),
    ("Investigation on the key factors associated with flavor quality in northern",
     "3  Investigation on the key fac", [], "mg/L"),
    ("Unraveling variation on the profile aroma",
     "3  Unraveling variation on the ", [], "μg/L(存疑)"),
]

with open(OUT, "w", encoding="utf-8") as f:
    for lit, sheet, conc_cols, expect_unit in checks:
        f.write("="*80 + "\n")
        f.write(f"文献: {lit}\n分表: {sheet}  (原文献单位={expect_unit})\n")
        # 读分表
        sh = pd.read_excel(REF, sheet_name=sheet)
        sh.columns = [str(c).strip() for c in sh.columns]
        # 找化合物列
        comp_col = None
        for cand in ["Compounds", "Compound Name", "Compound", "Aroma compounds", "flavor components"]:
            if cand in sh.columns:
                comp_col = cand; break
        if comp_col is None:
            # '3 Investigation' 第2列是化合物
            comp_col = sh.columns[1] if len(sh.columns) > 1 else sh.columns[0]
        # 分表里可能有CAS列
        cas_col = None
        for cand in ["cas", "CAS", "CAS number"]:
            if cand in sh.columns:
                cas_col = cand; break
        # 分表 值 -> 用所有浓度列的最大值代表该化合物量级
        use_cols = [c for c in conc_cols if c in sh.columns]
        f.write(f"  化合物列={comp_col!r} CAS列={cas_col!r} 用浓度列={use_cols}\n")
        ref_vals = {}   # name(lower) -> list of values
        for _, rr in sh.iterrows():
            nm = str(rr[comp_col]).strip().lower() if pd.notna(rr[comp_col]) else ""
            if not nm:
                continue
            vals = [parse_num(rr[c]) for c in use_cols] if use_cols else []
            vals = [v for v in vals if not math.isnan(v)]
            if vals:
                ref_vals[nm] = max(vals)
        # 清洗后数据该文献 浓度行
        sub = src[(src["文献名"] == lit) & (src["数据类型"] == "浓度")]
        # 按 名称 或 CAS 匹配
        ratios = []
        matched = 0
        for _, rr in sub.iterrows():
            nm = str(rr["化合物"]).strip().lower() if pd.notna(rr["化合物"]) else ""
            v = parse_num(rr["数值"])
            if math.isnan(v) or v == 0:
                continue
            rv = ref_vals.get(nm)
            if rv and rv > 0:
                ratios.append(rv / v)   # 分表/清洗  (期望: 1=同单位, 1000=清洗是mg/L? 等)
                matched += 1
        f.write(f"  匹配到 {matched} 个化合物(按名称)\n")
        if ratios:
            ratios.sort()
            med = ratios[len(ratios)//2]
            f.write(f"  分表值/清洗值 中位数 = {med:.6g}\n")
            # 解读
            if abs(med-1) < 0.3:
                interp = "清洗数据与分表同单位(即 %s)" % expect_unit
            elif abs(med-1000) < 300:
                interp = "分表是清洗的1000倍 => 清洗单位 = 分表单位/1000"
            elif abs(med-0.001) < 0.0005:
                interp = "清洗是分表的1000倍 => 清洗单位 = 分表单位*1000"
            else:
                interp = "倍数不明确(可能匹配错化合物)"
            f.write(f"  解读: {interp}\n")
            f.write(f"  样本比值(前10): {[round(x,4) for x in ratios[:10]]}\n")
        f.write("\n")

print("DONE -> calib.txt")
