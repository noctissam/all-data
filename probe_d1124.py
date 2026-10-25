# -*- coding: utf-8 -*-
"""probe_d1124: D11/D12/D24 清洗值 vs 总库分表值对照 -> probe_d1124.txt

PDF硬证据:
  D11 表1 质量浓度(mg/L) 己酸乙酯 YJ=175.85 DJ=139.92 CJ=145.13 LJ=159.55
  D12 表1 含量(mg/L) 己酸乙酯A=3116.48; 但OAV己酸乙酯A=56656, 丁酸乙酯A=5213
  D24 表1-7 质量浓度(mg/L) 己酸乙酯 TZL41%=1994.14 (五样2212.7/1994.1/1522.3/1650.3/2247.6)
疑点: 清洗后数据 D12 浓度行 己酸乙酯A=56663(≈OAV), 丁酸乙酯A=5213(=OAV) => 疑似OAV被误标为浓度
任务: 对照总库分表真浓度, 判断D12/D24清洗浓度行是否为误标OAV, 是否应改走分表回溯
"""
import re, math
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

KEYS = ["乙酸乙酯", "丁酸乙酯", "戊酸乙酯", "己酸乙酯", "乳酸乙酯", "乙酸"]

src = pd.read_excel(BASE + r"\清洗后数据.xlsx", sheet_name="清洗后数据")
xl = pd.ExcelFile(BASE + r"\data总库.xlsx")
sheets = xl.sheet_names

LIT = {
 "D11": "四川不同产区浓香型白酒风味物质差异化分析",
 "D12": "基于GC×GC-MS分析不同等级浓香型白酒的关键风味化合物",
 "D24": "洋河绵柔型白酒关键风味成分",
}
# 猜总库分表名
def find_sheet(pat):
    for s in sheets:
        if re.search(pat, s):
            return s
    return None

for k, lit in LIT.items():
    w("=" * 12 + " %s " % k + "=" * 12)
    g = src[src["文献名"] == lit]
    w("  类型: %s" % g["数据类型"].value_counts().to_dict())
    g2 = g[g["化合物"].astype(str).str.strip().isin(KEYS)]
    w("  -- 清洗后数据 关键酯 --")
    for _, r in g2.iterrows():
        w("    %s | %s | 样品=%s | 数值=%s" % (r["化合物"], r["数据类型"], r["样品"], r["数值"]))
    # 找分表
    pat = {"D11": r"四川不同产区", "D12": r"GC×GC|不同等级", "D24": r"洋河绵柔"}[k]
    sh_name = find_sheet(pat)
    w("  -- 总库分表: %r --" % sh_name)
    if sh_name:
        sh = pd.read_excel(BASE + r"\data总库.xlsx", sheet_name=sh_name)
        sh.columns = [str(c).strip() for c in sh.columns]
        w("    列: %s" % list(sh.columns))
        namecol = sh.columns[0]
        m = sh[sh[namecol].astype(str).str.strip().isin(KEYS)]
        for _, r in m.iterrows():
            vals = {c: r[c] for c in sh.columns[1:] if not pd.isna(r[c])}
            w("    %s -> %s" % (r[namecol], vals))
    w("")

with open(BASE + r"\probe_d1124.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE")
