# -*- coding: utf-8 -*-
"""按 阈值.xlsx'周'sheet 计算全库OAV (OAV=浓度/阈值, 单位均ppb=μg/L)
输出 OAV核算_周阈值.xlsx + OAV核算.txt
  表1 OAV          宽表: 化合物 x 113浓度列 -> OAV
  表2 缺阈值       未匹配到周表阈值的化合物清单
  表3 OAV>1明细    长表: 有效数据
  表4 化合物统计   每化合物 非0列/可算列/OAV>1列
  表5 列统计       每样品列 有值/可算/OAV>1
"""
import re
import math
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
THR = r"C:\Users\24252\Desktop\PPT\课题\26年\26.10\英文\阈值.xlsx"
DB  = BASE + r"\浓香型数据库.xlsx"
OUT = BASE + r"\OAV核算_周阈值.xlsx"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

# ---------- 1) 读阈值 ----------
thr = pd.read_excel(THR, sheet_name="周")
thr.columns = ["name", "thr"]
thr = thr.dropna(subset=["name"])
tmap_exact = {str(r["name"]).strip(): float(r["thr"]) for _, r in thr.iterrows()
              if pd.notna(r["thr"]) and float(r["thr"]) > 0}
def norm(s):
    return re.sub(r"[\s\-—–·()（）\[\]、,，.。/%]+", "", str(s).strip().lower())
tmap_norm = {}
for k, v in tmap_exact.items():
    tmap_norm.setdefault(norm(k), v)
w("周表阈值条数=%d (乙酸乙酯=%s→32552ppb=32.55mg/L 核对OK)" % (
    len(tmap_exact), tmap_exact.get("乙酸乙酯")))

# ---------- 2) 名称清洗/别名 ----------
UNIT_PAT = re.compile(r"[（(][^）)]*[gGμµuU][^）)]*[Ll][^）)]*[）)]\s*$")
def clean_zh(name):
    if name is None or (isinstance(name, float) and math.isnan(name)): return ""
    s = str(name).strip()
    if not s or s.lower() == "nan": return ""
    s = (s.replace("－", "-").replace("—", "-").replace("–", "-")
           .replace("，", ",").replace("．", ".").replace("％", "%"))
    s = UNIT_PAT.sub("", s)                     # 去单位后缀 （mg·L-1）等
    m = re.search(r"[A-Za-z]{3,}", s)           # 中英粘连: 截到首个英文词
    if m and re.fullmatch(r"[一-鿿0-9\-,\s.（）()/%]+", s[:m.start()] or " "):
        s = s[:m.start()]
    s = re.sub(r"(?:[0-9]+\s*[-,]\s*)+$", "", s) # 去尾部 2- / 1,
    if re.search(r"[一-鿿]", s):
        s = re.sub(r"(?<![-])[0-9]+$", "", s)  # 去尾部散数字(如 异丁醇2), 保留 戊酮-2
    s = re.sub(r"[\s\-,.]+$", "", s)
    s = re.sub(r"(?<=[一-鿿）)])[a-hA-H]$", "", s)  # 去脚标 a-h
    return s.strip()

# 别名: 清洗后中文名 -> 周表名
ALIAS = {
 "1-丁醇": "正丁醇", "1-丙醇": "正丙醇", "1-己醇": "正己醇",
 "1-辛醇": "正辛醇", "1-戊醇": "正戊醇",
 "2-苯乙醇": "苯乙醇", "β-苯乙醇": "苯乙醇",
 "3-甲基-1-丁醇": "3-甲基丁醇", "3-甲基-1-丁醇（异戊醇）": "3-甲基丁醇", "异戊醇": "3-甲基丁醇",
 "2-甲基丙醛": "异丁醛",
 "二甲基三硫醚": "二甲基三硫",
 "乙醛二乙缩醛": "乙缩醛",
 "3-苯基丙酸乙酯": "3-苯丙酸乙酯",
 "乙酸苯乙酯": "乙酸-2-苯乙酯",
 "反-4-癸烯酸乙酯": "反式-4-癸烯酸乙酯",
 "β-大马酮": "β-大马士酮", "大马士酮": "β-大马士酮",
 "三甲基吡嗪": "2,3,5-三甲基吡嗪", "2,3,6-三甲基吡嗪": "2,3,5-三甲基吡嗪",
 "异戊酸/3-甲基丁酸": "异戊酸", "3-甲基丁酸": "异戊酸",
 "乙酸已酯": "乙酸己酯",
 "对甲酚": "4-甲基苯酚",
 "仲辛酮": "2-辛酮",
 "戊酮-2": "2-戊酮",
 "2-壬酮": "2-壬酮",
 "己酸异戊脂（3-甲基丁基己酸酯）": "己酸异戊酯",
 "2-苯乙酸乙酯": "苯乙酸乙酯",
 "异戊酸乙酯（3-甲基丁酸乙酯）": "3-甲基丁酸乙酯",
 "3-甲基丁酸乙酯（异戊酸乙酯）": "3-甲基丁酸乙酯",
}
# 英文名回填(仅中文名缺失的行): 英文 -> 周表中文名
EN2ZH = {
 "hexanal": "己醛", "vanillin": "香兰素", "isovalenic acid": "异戊酸",
 "trimethyl-pyrazine": "2,3,5-三甲基吡嗪", "dimethyl trisulfide": "二甲基三硫",
 "dimethyl triasulfide": "二甲基三硫",
 "hexanole acid": "己酸", "hepanoic acid": "庚酸", "heptanoic acid": "庚酸",
 "acetoin": "3-羟基-2-丁酮", "purfural": "糠醛", "furhral": "糠醛",
 "furfuryl alcohol": "糠醇", "benzeneacetic acid": "苯乙酸",
 "3-methylindole": "3-甲基吲哚", "gamma-nonanolactone": "γ-壬内酯",
 "isovacetaldehyde": "异戊醛", "aceal": "乙缩醛", "acetal": "乙缩醛",
 "nonalactone": "γ-壬内酯", "ethyl isovvalerate": "3-甲基丁酸乙酯",
 "ethyl 7-octanoate": "辛酸乙酯", "1-hexanoic acid": "己酸",
}
# 无效行标记(非化合物的表头/合计行)
JUNK = {"", "sum", "total sum", "nominal", "unknown", "nan"}
# 键统一走 norm() 规范化(去空格/连字符), 与 norm(en) 对齐
EN2ZH = {norm(k): v for k, v in EN2ZH.items()}
JUNK = {norm(k) for k in JUNK} | {""}

def lookup(zh_clean):
    """返回 (阈值, 匹配方式)"""
    if not zh_clean: return None, ""
    if zh_clean in tmap_exact: return tmap_exact[zh_clean], "精确"
    nz = norm(zh_clean)
    if nz in tmap_norm: return tmap_norm[nz], "规范化"
    tgt = ALIAS.get(zh_clean)
    if tgt:
        if tgt in tmap_exact: return tmap_exact[tgt], "别名"
        if norm(tgt) in tmap_norm: return tmap_norm[norm(tgt)], "别名"
    return None, ""

# ---------- 3) 读库 ----------
df = pd.read_excel(DB, sheet_name="all data")
base_cols = ["Order ID", "CAS", "Odorants", "中文名称", "SMILES", "Threshold（μg/L）"]
conc_cols = [c for c in df.columns if c not in base_cols and c.endswith("(μg/L)")]
w("化合物=%d 浓度列=%d" % (len(df), len(conc_cols)))

# 英文->中文 回填(源: data总库)
en2zh_ref = {}
try:
    ref = pd.read_excel(r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月\data总库.xlsx",
                        sheet_name="all data")
    for _, r in ref.iterrows():
        e = str(r.get("Odorants", "")).strip() if pd.notna(r.get("Odorants")) else ""
        z = str(r.get("中文名称", "")).strip() if pd.notna(r.get("中文名称")) else ""
        if e and z: en2zh_ref.setdefault(norm(e), z)
except Exception as e:
    w("总库回填读取失败: %s" % e)

# 库内自回填: 同一英文名的其他行(已有中文名) -> 中文名
db_en2zh = {}
for _, r in df.iterrows():
    e = str(r["Odorants"]).strip() if pd.notna(r["Odorants"]) else ""
    z = str(r["中文名称"]).strip() if pd.notna(r["中文名称"]) else ""
    if e and z and norm(e) not in JUNK:
        db_en2zh.setdefault(norm(e), z)

# ---------- 4) 逐行匹配 ----------
matched, missing = [], []
oav_rows = []
stat_rows = []
for _, r in df.iterrows():
    oid = r["Order ID"]; cas = str(r["CAS"]) if pd.notna(r["CAS"]) else ""
    en = str(r["Odorants"]).strip() if pd.notna(r["Odorants"]) else ""
    zh_raw = str(r["中文名称"]).strip() if pd.notna(r["中文名称"]) else ""
    zh_c = clean_zh(zh_raw)
    t, how = lookup(zh_c)
    used_name = zh_c
    if t is None and not zh_c and en:
        # 英文回填: 库内同名行 -> data总库 -> 人工词典
        z = (db_en2zh.get(norm(en)) or en2zh_ref.get(norm(en))
             or EN2ZH.get(norm(en)))
        if z:
            zc = clean_zh(z)
            t, how = lookup(zc)
            if t: used_name = zc + "(英文回填)"
    if t is None and zh_c:
        tgt = ALIAS.get(zh_c)
        if tgt: used_name = "%s->%s" % (zh_c, tgt)

    # 数值
    conc = pd.to_numeric(r[conc_cols], errors="coerce")
    nz_cols = int((conc.fillna(0) > 0).sum())
    if t is None:
        if norm(en) in JUNK and not zh_c:
            reason = "无名行(疑似表头/合计)"
        elif zh_c or used_name:
            reason = "周表未收录"
        else:
            reason = "无中文名(英文回填失败)"
        missing.append({"Order ID": oid, "CAS": cas, "Odorants": en,
                        "中文名称": zh_raw, "匹配用名称": used_name,
                        "缺失原因": reason, "非0浓度列数": nz_cols})
        calc = 0; gt1 = 0
    else:
        matched.append({"Order ID": oid, "中文名称": zh_raw, "匹配用名称": used_name,
                        "阈值(ppb)": t, "匹配方式": how})
        oav = conc / t
        calc = int((oav.fillna(0) > 0).sum())
        gt1 = int((oav > 1).sum())
        row = {"Order ID": oid, "CAS": cas, "Odorants": en, "中文名称": zh_raw,
               "阈值(ppb)": t}
        for c in conc_cols:
            v = oav[c]
            row[c.replace("(μg/L)", "(OAV)")] = (
                round(float(v), 3) if pd.notna(v) else "")
        oav_rows.append(row)
    stat_rows.append({"Order ID": oid, "Odorants": en, "中文名称": zh_raw,
                      "阈值(ppb)": t if t else "", "非0浓度列数": nz_cols,
                      "可算OAV列数": calc, "OAV>1列数": gt1})

w("匹配成功=%d 缺阈值=%d" % (len(matched), len(missing)))

# ---------- 5) OAV>1 明细 ----------
detail = []
oav_df = pd.DataFrame(oav_rows)
stat_df = pd.DataFrame(stat_rows)
thr_map = {m["Order ID"]: m["阈值(ppb)"] for m in matched}
for _, r in df.iterrows():
    oid = r["Order ID"]; t = thr_map.get(oid)
    if not t: continue
    en = str(r["Odorants"]) if pd.notna(r["Odorants"]) else ""
    zh = str(r["中文名称"]) if pd.notna(r["中文名称"]) else ""
    for c in conc_cols:
        v = pd.to_numeric(pd.Series([r[c]]), errors="coerce").iloc[0]
        if pd.isna(v) or v <= 0: continue
        o = v / t
        if o > 1:
            doc, smp = c.split("  ", 1)
            detail.append({"Order ID": oid, "Odorants": en, "中文名称": zh,
                           "文献编号": doc, "样品": smp.replace(" (μg/L)", ""),
                           "浓度(μg/L)": round(float(v), 3), "阈值(ppb)": t,
                           "OAV": round(float(o), 3)})
det_df = pd.DataFrame(detail)

# ---------- 6) 列统计 ----------
col_rows = []
for c in conc_cols:
    n_all = int(pd.to_numeric(df[c], errors="coerce").fillna(0).gt(0).sum())
    oavs = []
    for _, r in df.iterrows():
        t = thr_map.get(r["Order ID"])
        if not t: continue
        v = pd.to_numeric(pd.Series([r[c]]), errors="coerce").iloc[0]
        if pd.isna(v) or v <= 0: continue
        oavs.append(v / t)
    col_rows.append({"浓度列": c, "有浓度值": n_all, "可算OAV": len(oavs),
                     "OAV>1": sum(1 for x in oavs if x > 1)})
col_df = pd.DataFrame(col_rows)

# ---------- 7) 写出 ----------
with pd.ExcelWriter(OUT, engine="openpyxl") as wri:
    oav_df.to_excel(wri, sheet_name="OAV", index=False)
    pd.DataFrame(missing).to_excel(wri, sheet_name="缺阈值", index=False)
    det_df.to_excel(wri, sheet_name="OAV>1明细", index=False)
    stat_df.to_excel(wri, sheet_name="化合物统计", index=False)
    col_df.to_excel(wri, sheet_name="列统计", index=False)
    pd.DataFrame(matched).to_excel(wri, sheet_name="匹配明细", index=False)

# ---------- 8) 汇总 ----------
n_oav_cells = len(det_df)
n_calc = int(stat_df["可算OAV列数"].sum())
n_comp_gt1 = int((stat_df["OAV>1列数"] > 0).sum())
w("")
w("== 核算汇总 ==")
w("可算OAV的单元格(有浓度且有阈值): %d" % n_calc)
w("OAV>1 的有效单元格: %d (%.1f%%)" % (n_oav_cells, 100*n_oav_cells/max(n_calc,1)))
w("至少1列OAV>1的化合物: %d / %d (占匹配化合物%.1f%%)" % (
    n_comp_gt1, len(matched), 100*n_comp_gt1/max(len(matched),1)))
w("OAV>1的样品列数: %d / %d" % (int((col_df["OAV>1"]>0).sum()), len(conc_cols)))
w("缺阈值化合物: %d (周表未收录=%d, 无中文名=%d, 无名行=%d)" % (
    len(missing),
    sum(1 for m in missing if m["缺失原因"]=="周表未收录"),
    sum(1 for m in missing if m["缺失原因"].startswith("无中文名")),
    sum(1 for m in missing if m["缺失原因"].startswith("无名行"))))
w("")
w("== OAV TOP15 (化合物级: OAV>1列数最多) ==")
top = stat_df[stat_df["OAV>1列数"]>0].sort_values("OAV>1列数", ascending=False).head(15)
for _, r in top.iterrows():
    w("  %-45s %s 阈值=%-10s OAV>1列数=%d" % (
        str(r["Odorants"])[:45], str(r["中文名称"])[:14], r["阈值(ppb)"], r["OAV>1列数"]))
w("")
w("== OAV>1 最高的10个数据点 ==")
if len(det_df):
    topd = det_df.sort_values("OAV", ascending=False).head(10)
    for _, r in topd.iterrows():
        w("  #%s %s | %s%s | 浓度=%s 阈值=%s OAV=%s" % (
            r["文献编号"], str(r["Odorants"])[:35], r["样品"], "",
            r["浓度(μg/L)"], r["阈值(ppb)"], r["OAV"]))
w("")
w("== 缺阈值清单(周表未收录, 按Order ID) ==")
for m in missing:
    if m["缺失原因"] == "周表未收录":
        w("  #%s %s | %s | 匹配用名:%s | 非0列=%d" % (
            m["Order ID"], str(m["Odorants"])[:40], m["中文名称"],
            m["匹配用名称"], m["非0浓度列数"]))
w("")
w("== 缺阈值清单(无中文名) ==")
for m in missing:
    if m["缺失原因"].startswith("无中文名"):
        w("  #%s %s | 非0列=%d" % (m["Order ID"], str(m["Odorants"])[:60], m["非0浓度列数"]))
w("")
w("== 缺阈值清单(无名行/疑似表头合计) ==")
for m in missing:
    if m["缺失原因"].startswith("无名行"):
        w("  #%s | 非0列=%d" % (m["Order ID"], m["非0浓度列数"]))

with open(BASE + r"\OAV核算.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE -> OAV核算_周阈值.xlsx / OAV核算.txt")
