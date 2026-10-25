# -*- coding: utf-8 -*-
"""
把 清洗后数据.xlsx(长表) 整理成 浓香型数据库.xlsx(宽表)
格式对齐 data总库.xlsx 的 'all data' 工作表:
  行 = 化合物(按 CAS 归并)
  列 = Order ID / CAS / Odorants(英文名) / 中文名称 / SMILES / Threshold(μg/L)
        + 各文献样品浓度列(带文献编号前缀) + 各文献样品OAV列
第一版:单位按原始检测标注,不做换算(单位表单独列出待确认)。
"""
import re
import math
import pandas as pd
import numpy as np

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
SRC = BASE + r"\清洗后数据.xlsx"
REF = BASE + r"\data总库.xlsx"
OUT = BASE + r"\浓香型数据库.xlsx"

# ---------------- 读取长表 ----------------
df = pd.read_excel(SRC, sheet_name="清洗后数据")
df.columns = [str(c).strip() for c in df.columns]

# ---------------- 工具函数 ----------------
def parse_num(x):
    """把数值解析成 float;处理千分位、±、<1/ND 等。返回 (value, flag)"""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return (np.nan, "empty")
    if isinstance(x, (int, float)):
        return (float(x), "ok")
    s = str(x).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return (np.nan, "empty")
    # 直接数字
    s2 = s.replace(",", "")
    try:
        return (float(s2), "ok")
    except ValueError:
        pass
    # 形如 "5320.56 ± 47.54b" / "12.21±0.93" -> 取 ± 前面
    m = re.match(r"^([<>]?)\s*([-+]?\d[\d,]*\.?\d*)\s*(?:±|±)?", s)
    if m:
        sign, num = m.group(1), m.group(2)
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            return (np.nan, "unparsed")
        if sign == "<":
            return (v, "lt")
        if sign == ">":
            return (v, "gt")
        return (v, "ok")
    return (np.nan, "unparsed")

# 垃圾样品名判定
JUNK_SAMPLE_PAT = re.compile(
    r"^(nan|none|null|nd|n\.d\.?|—|--|－|/|-|\+|<1|<0\.001|>100|>10|>1)$"
    r"|^[\d\.\s±<>±]+$"         # 纯数字/带± (必须 $ 锚,否则误伤 '3 年陈')
    r"|浓度|含量|量比|平均|序号|编号|No\.?|Category|ion|p值|SD|OAV值?|配度|加标|添加|重复性|稳定性"
    r"|\(I%\)|乙醛脱氢酶"
    # 类别/表头词(英文+中文),不应作为样品
    r"|^esters?$|^alcohols?$|^acids?$|^aldehydes?$|^ketones?$|^phenols?$"
    r"|^terpen\w*$|^nitrogen|^sulfur|^others?$|^totals?$|^compounds?$|^aroma"
    r"|^酯类$|^醇类$|^酸类$|^醛类$|^酮类$|^酚类$|^杂环$|^其他$|^总计$|^合计$"
    r"|mg\s*/?\s*l|μg\s*/?\s*l|g\s*/?\s*l|mg·l|μg·l|g·l|mg/L|μg/L|g/L",
    re.IGNORECASE,
)

def clean_sample(s):
    """规整样品名;返回 None 表示是垃圾需丢弃"""
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return None
    t = str(s).strip()
    if t == "" or t.lower() == "nan":
        return None
    if JUNK_SAMPLE_PAT.search(t):
        return None
    # 去掉脚注字母后缀: GRD-JCb -> GRD-JC ; LZLJb -> LZLJ ; 仅当结尾是"大写/数字+小写字母"才剥
    t2 = re.sub(r"(?<=[A-Z0-9])[a-z]{1,2}$", "", t)
    t2 = t2.strip()
    if t2 == "":
        return None
    # 仍是纯数字/极短无意义
    if re.fullmatch(r"[\d\.]+", t2):
        return None
    return t2

# ---------------- 归并化合物主键 ----------------
def norm_cas(c):
    if c is None or (isinstance(c, float) and math.isnan(c)):
        return None
    s = str(c).strip().replace("–", "-").replace("—", "-").replace(" ", "")
    return s if s else None

def norm_name(n):
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return ""
    return str(n).strip()

df["CAS_key"] = df["CAS号"].apply(norm_cas)
df["name"] = df["化合物"].apply(norm_name)
# 主键: 有CAS用 CAS, 无CAS用 name(加前缀避免与CAS冲突)
df["comp_key"] = df.apply(
    lambda r: ("CAS:" + r["CAS_key"]) if r["CAS_key"] else ("NM:" + re.sub(r"\s+", " ", r["name"].lower())), axis=1
)

# 中英文名收集
def has_cjk(s):
    return bool(re.search(r"[一-鿿]", s))

comp_info = {}
for key, g in df.groupby("comp_key"):
    names = g["name"].dropna().unique().tolist()
    zh = [n for n in names if has_cjk(n)]
    en = [n for n in names if not has_cjk(n) and n]
    cas = g["CAS_key"].dropna().unique().tolist()
    comp_info[key] = {
        "cas": cas[0] if cas else None,
        "zh": zh[0] if zh else "",
        "en": en[0] if en else "",
        "names": names,
    }

# ---------------- 从 data总库 取 SMILES / 英文名 / 中文名 / Threshold ----------------
ref_wb = pd.ExcelFile(REF)
ref_all = pd.read_excel(REF, sheet_name="all data")
ref_all.columns = [str(c).strip() for c in ref_all.columns]
# 列: Order ID, CAS, Odorants, 中文名称, SMILES, Threshold, Concentration（μg/L）, ...
smiles_map = {}
en_map = {}
zh_map = {}
thr_map = {}
for _, rr in ref_all.iterrows():
    c = norm_cas(rr.get("CAS"))
    if not c:
        continue
    sm = rr.get("SMILES")
    if sm is not None and not (isinstance(sm, float) and math.isnan(sm)):
        smiles_map[c] = str(sm).strip()
    en = rr.get("Odorants")
    if en is not None and not (isinstance(en, float) and math.isnan(en)):
        en_map[c] = str(en).strip()
    zh = rr.get("中文名称")
    if zh is not None and not (isinstance(zh, float) and math.isnan(zh)):
        zh_map[c] = str(zh).strip()
    th = rr.get("Threshold")
    v, f = parse_num(th)
    if f in ("ok", "lt", "gt") and not math.isnan(v):
        thr_map[c] = v

# ---------------- 展开为宽表 ----------------
# 先确定文献顺序(按首次出现)
docs = df["文献名"].dropna().unique().tolist()
doc_idx = {d: i + 1 for i, d in enumerate(docs)}

# 收集 (文献, 类型) -> 样品集合,用于建列
conc_cols = {}   # doc -> [sample...]
oav_cols = {}
for _, r in df.iterrows():
    d = r["文献名"]
    if pd.isna(d):
        continue
    smp = clean_sample(r["样品"])
    if smp is None:
        continue
    if r["数据类型"] == "浓度":
        conc_cols.setdefault(d, {})
        conc_cols[d][smp] = True
    elif r["数据类型"] == "OAV":
        oav_cols.setdefault(d, {})
        oav_cols[d][smp] = True

for d in conc_cols:
    conc_cols[d] = sorted(conc_cols[d].keys())
for d in oav_cols:
    oav_cols[d] = sorted(oav_cols[d].keys())

# 每列对应单位(用原始垃圾样品名里检测到的单位,第一版不换算)
def detect_unit(doc):
    sub = df[df["文献名"] == doc]["样品"].astype(str)
    for s in sub:
        low = s.lower()
        if "mg" in low and "l" in low:
            return "mg/L"
        if "μg" in low or "ug" in low:
            return "μg/L"
        if re.search(r"\bg\s*/?\s*l\b", low):
            return "g/L"
    return "μg/L"   # 默认

doc_unit = {d: detect_unit(d) for d in docs}

# 构建数值查找: (comp_key, doc, sample) -> (conc_value, oav_value)
conc_val = {}
oav_val = {}
thr_val = {}
for _, r in df.iterrows():
    d = r["文献名"]
    if pd.isna(d):
        continue
    ck = r["comp_key"]
    smp = clean_sample(r["样品"])
    v, f = parse_num(r["数值"])
    dt = r["数据类型"]
    if dt == "阈值":
        if smp is None:
            # 阈值行样品常为垃圾名,仍记录一个阈值(取该化合物在该文献的阈值)
            if not math.isnan(v):
                key = (ck, d)
                # 保留最大可代表值;简单:若未记录则存
                if key not in thr_val:
                    thr_val[key] = v
        continue
    if smp is None or math.isnan(v):
        continue
    if dt == "浓度":
        conc_val[(ck, d, smp)] = v
    elif dt == "OAV":
        oav_val[(ck, d, smp)] = v

# ---------------- 组装输出行 ----------------
comp_keys = sorted(comp_info.keys())
# 排序: 按 CAS 数值 / 名称
def sort_key(k):
    info = comp_info[k]
    cas = info["cas"] or "zzz"
    return cas
comp_keys.sort(key=sort_key)

# 列定义
base_cols = ["Order ID", "CAS", "Odorants", "中文名称", "SMILES", "Threshold（μg/L）"]
col_headers = list(base_cols)
col_plan = []   # (kind, doc, sample, header)
for d in docs:
    if d not in conc_cols:
        continue
    for smp in conc_cols[d]:
        h = f"{doc_idx[d]}  {smp} ({doc_unit[d]})"
        col_plan.append(("conc", d, smp, h))
        col_headers.append(h)
for d in docs:
    if d not in oav_cols:
        continue
    for smp in oav_cols[d]:
        h = f"{doc_idx[d]}  {smp} OAV"
        col_plan.append(("oav", d, smp, h))
        col_headers.append(h)

# 填数据
rows = []
for i, ck in enumerate(comp_keys, 1):
    info = comp_info[ck]
    cas = info["cas"]
    en = en_map.get(cas) if cas else ""
    zh = zh_map.get(cas) if cas else ""
    sm = smiles_map.get(cas) if cas else ""
    en = en or info["en"]
    zh = zh or info["zh"]
    # threshold: 优先用本库阈值记录,否则用总库
    th = ""
    for d in docs:
        if (ck, d) in thr_val:
            th = thr_val[(ck, d)]
            break
    if th == "" and cas and cas in thr_map:
        th = thr_map[cas]
    row = {
        "Order ID": i,
        "CAS": cas or "",
        "Odorants": en,
        "中文名称": zh,
        "SMILES": sm,
        "Threshold（μg/L）": th,
    }
    for kind, d, smp, h in col_plan:
        if kind == "conc":
            val = conc_val.get((ck, d, smp))
        else:
            val = oav_val.get((ck, d, smp))
        row[h] = val if val is not None else ""
    rows.append(row)

out_df = pd.DataFrame(rows, columns=col_headers)

# ---------------- 文献索引表 ----------------
doc_rows = []
for d in docs:
    n_conc = len(conc_cols.get(d, []))
    n_oav = len(oav_cols.get(d, []))
    doc_rows.append({
        "文献编号": doc_idx[d],
        "文献名": d,
        "浓度样品列数": n_conc,
        "OAV样品列数": n_oav,
        "检测单位": doc_unit[d],
    })
doc_df = pd.DataFrame(doc_rows)

# ---------------- 数据质量报告 ----------------
# 统计每篇文献:总行数、浓度行、OAV行、阈值行、进入宽表的行数、被丢弃(样品为垃圾/数值不可解析)行数
qual_rows = []
for d in docs:
    g = df[df["文献名"] == d]
    n_total = len(g)
    n_conc_rows = int((g["数据类型"] == "浓度").sum())
    n_oav_rows = int((g["数据类型"] == "OAV").sum())
    n_thr_rows = int((g["数据类型"] == "阈值").sum())
    n_conc_col = len(conc_cols.get(d, []))
    n_oav_col = len(oav_cols.get(d, []))
    # 进入宽表的数值单元数
    used = sum(1 for (ck, dd, smp) in conc_val if dd == d) + sum(1 for (ck, dd, smp) in oav_val if dd == d)
    qual_rows.append({
        "文献编号": doc_idx[d],
        "文献名": d,
        "总行数": n_total,
        "浓度行": n_conc_rows,
        "OAV行": n_oav_rows,
        "阈值行": n_thr_rows,
        "浓度列数": n_conc_col,
        "OAV列数": n_oav_col,
        "入库数值数": used,
        "状态": "无可用样品名(全丢弃)" if (n_conc_col + n_oav_col) == 0 else "正常",
    })
qual_df = pd.DataFrame(qual_rows)
zero_docs = qual_df[qual_df["状态"] != "正常"]["文献名"].tolist()


# ---------------- 写出 ----------------
with pd.ExcelWriter(OUT, engine="openpyxl") as w:
    out_df.to_excel(w, sheet_name="all data", index=False)
    doc_df.to_excel(w, sheet_name="文献索引", index=False)

    # 单位待确认表:每个文献原始样品名里出现的单位线索
    unit_rows = []
    for d in docs:
        clues = set()
        for s in df[df["文献名"] == d]["样品"].astype(str):
            low = s.lower()
            if "mg" in low and "l" in low:
                clues.add("mg/L")
            elif "μg" in low or "ug" in low:
                clues.add("μg/L")
            elif re.search(r"\bg\s*/?\s*l\b", low):
                clues.add("g/L")
        unit_rows.append({
            "文献编号": doc_idx[d],
            "文献名": d,
            "检测到的单位线索": ", ".join(sorted(clues)) if clues else "(无,默认μg/L)",
            "第一版采用": doc_unit[d],
            "需人工确认": "是" if (not clues or len(clues) > 1) else "否",
        })
    pd.DataFrame(unit_rows).to_excel(w, sheet_name="单位待确认", index=False)
    qual_df.to_excel(w, sheet_name="数据质量", index=False)

print("输出:", OUT)
print("化合物数:", len(out_df), " 总列数:", out_df.shape[1])
print("文献数:", len(doc_df))
print("浓度列:", sum(1 for p in col_plan if p[0]=="conc"),
      " OAV列:", sum(1 for p in col_plan if p[0]=="oav"))
print("总入库数值:", int(qual_df["入库数值数"].sum()))
print("无可用样品名(全丢弃)的文献数:", len(zero_docs))
for z in zero_docs:
    print("   -", z)
