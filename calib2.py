# -*- coding: utf-8 -*-
"""稳健单位定标:
把 data总库 'all data' 解析成长表(CAS, 分组号, 样品, 值_ugL)
每个清洗文献 -> 用样品名重叠匹配到某个总库分组 -> CAS匹配算比值(清洗值/总库值ugL)
比值 ~1 => μg/L; ~0.001 => mg/L; ~1e-6 => g/L
"""
import re
import math
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
REF = BASE + r"\data总库.xlsx"
SRC = BASE + r"\清洗后数据.xlsx"
OUT = BASE + r"\calib2.txt"

def parse_num(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return math.nan
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    m = re.match(r"^([<>]?)\s*([-+]?\d[\d,]*\.?\d*)", s)
    if m:
        try: return float(m.group(2).replace(",", ""))
        except ValueError: return math.nan
    try: return float(s)
    except ValueError: return math.nan

def norm_cas(c):
    if c is None or (isinstance(c, float) and math.isnan(c)):
        return None
    s = str(c).strip().replace("–", "-").replace("—", "-").replace(" ", "")
    return s if re.fullmatch(r"\d[\d\-]*\d|\d+", s) else None

# ---- data总库 'all data' -> 长表 ----
all_df = pd.read_excel(REF, sheet_name="all data")
all_df.columns = [str(c).strip() for c in all_df.columns]
info_cols = ["Order ID","CAS","Odorants","中文名称","SMILES","Threshold","Concentration（μg/L）"]
# 前6列信息(Threshold, Concentration 是第6/7)
hdr = all_df.columns.tolist()
data_hdr = hdr[6:]   # 从第7列(索引6)开始是样品列? 实际索引:0 OrderID..4 SMILES,5 Threshold,6 Concentration,7.. samples
# 修正: 信息列到 'Concentration（μg/L）' 为止
conc_idx = hdr.index("Concentration（μg/L）") if "Concentration（μg/L）" in hdr else 6
sample_hdr = hdr[conc_idx+1:]

# 解析分组
def parse_group(colname):
    m = re.match(r"^\s*(\d+)\s+(.*)$", colname)
    if m:
        return int(m.group(1)), m.group(2)
    return None, colname

# 构建 长表: (CAS) -> {group: {sample: value}}
ref_long = {}   # cas -> list of (group, sample, value)
cur_group = None
for c in sample_hdr:
    g, rest = parse_group(c)
    if g is not None:
        cur_group = g
    # 提取样品名(去掉单位)
    smp = re.sub(r"[\(（]\s*(?:μg/L|mg/L|g/L|μg/l|mg/l|g/l)\s*[\)）]", "", rest)
    smp = re.sub(r"\s*(?:μg/L|mg/L|g/L)\s*$", "", smp).strip()
    # 值
    for _, rr in all_df.iterrows():
        cas = norm_cas(rr.get("CAS"))
        v = parse_num(rr.get(c))
        if cas and not math.isnan(v):
            ref_long.setdefault(cas, []).append((cur_group, smp, v))

# ---- 清洗后数据 ----
src = pd.read_excel(SRC, sheet_name="清洗后数据")
src["CASk"] = src["CAS号"].apply(norm_cas)

def clean_sample(s):
    if s is None: return None
    t = str(s).strip()
    if t=="" or t.lower()=="nan": return None
    junk = re.compile(r"^(nan|nd|n\.d\.?|—|--|－|/|-|<1|>100|>10|>1)$|^[\d\.\s±<>±]+$"
        r"|浓度|含量|量比|平均|序号|No\.?|Category|ion|p值|SD|OAV值?|配度|加标|添加|重复性|稳定性"
        r"|\(I%\)|乙醛脱氢酶|^esters?$|^alcohols?$|^acids?$|^酯类$|^醇类$|^酸类$|^其他$"
        r"|mg\s*/?\s*l|μg\s*/?\s*l|g\s*/?\s*l|mg·l|μg·l|g·l|mg/L|μg/L|g/L", re.IGNORECASE)
    if junk.search(t): return None
    t2 = re.sub(r"(?<=[A-Z0-9])[a-z]{1,2}$","",t).strip()
    if t2=="" or re.fullmatch(r"[\d\.]+",t2): return None
    return t2

with open(OUT,"w",encoding="utf-8") as f:
    f.write("### 每个清洗文献 -> 匹配总库分组 -> 单位推断 ###\n")
    for lit, g in src.groupby("文献名", sort=False):
        # 清洗样品集合
        smp_set = set()
        for s in g["样品"].astype(str):
            cs = clean_sample(s)
            if cs: smp_set.add(cs)
        # 清洗浓度值 by CAS
        conc = {}
        for _, rr in g[g["数据类型"]=="浓度"].iterrows():
            cas = rr["CASk"]; v = parse_num(rr["数值"])
            if cas and not math.isnan(v) and v>0:
                conc.setdefault(cas, []).append(v)
        # 对每个总库分组, 算 与该文献的 样品重叠数 + CAS匹配比值
        best = None
        group_scores = {}
        for cas, lst in ref_long.items():
            for (grp, smp, rv) in lst:
                sc = group_scores.setdefault(grp, {"smp":set(), "ratios":[]})
                if smp in smp_set:
                    sc["smp"].add(smp)
                if cas in conc and rv>0:
                    # 用清洗该CAS的中位数
                    cv = sorted(conc[cas])[len(conc[cas])//2]
                    if cv>0:
                        sc["ratios"].append(cv/rv)   # 清洗/总库(ugL)
        # 选 重叠样品最多 且 比值中位数稳定的分组
        cands = [(len(sc["smp"]), sc) for grp, sc in group_scores.items() if sc["smp"] or sc["ratios"]]
        cands.sort(key=lambda x: -x[0])
        f.write(f"\n【{lit}】清洗样品={sorted(smp_set) if smp_set else '(无)'}\n")
        if not cands:
            f.write("   无匹配总库分组\n"); continue
        # 取重叠最多的前2个分组, 报告比值
        for ov, sc in cands[:2]:
            ratios = sorted(sc["ratios"])
            med = ratios[len(ratios)//2] if ratios else math.nan
            if not math.isnan(med):
                if 0.7<med<1.5: u="≈μg/L(比值1)"
                elif 0.0007<med<0.0015: u="≈mg/L(比值0.001)"
                elif 7e-7<med<1.5e-6: u="≈g/L(比值1e-6)"
                elif 700<med<1500: u="清洗=μg/L??(比值1000, 清洗比总库大1000)"
                else: u="比值%.4g 不明确"%med
                f.write(f"   分组{ov and ''}{''}样品重叠={len(sc['smp'])}{sorted(sc['smp'])[:6]} CAS比值中位={med:.4g} -> {u} (n={len(ratios)})\n")
            else:
                f.write(f"   样品重叠={len(sc['smp'])} 无CAS比值\n")

print("DONE -> calib2.txt")
