# -*- coding: utf-8 -*-
"""综合探查:
A) data总库 D3/D6/D7 分表结构(用于单位定标)
B) data总库 all data 是否有 天之蓝/二锅头 列(D25回溯)
C) 中文PDF单位关键词扫描(D14/D18/D19/D21/D22/D25)
D) D23 编码样品在王晓欣论文中的定义
E) D25 清洗后数据原始行抽样
输出 -> probe_all.txt, probe_d23.txt
"""
import re, os
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
REF = BASE + r"\data总库.xlsx"
SRC = BASE + r"\清洗后数据.xlsx"
OUT = BASE + r"\probe_all.txt"
OUT2 = BASE + r"\probe_d23.txt"

lines = []
def w(s=""): lines.append(s)

# ---- A) 分表结构 ----
w("=" * 20 + " A) 分表结构 " + "=" * 20)
for sheet in ["2  Decoding the Molecular Mecha", "3  Characterization of the diff",
              "3  Unraveling variation on the "]:
    sh = pd.read_excel(REF, sheet_name=sheet)
    sh.columns = [str(c).strip() for c in sh.columns]
    w(f"[{sheet}] shape={sh.shape}")
    w("  cols: " + " | ".join(sh.columns[:40]))
    w("")

# ---- B) all data 中天之蓝相关列 ----
w("=" * 20 + " B) all data 天之蓝/二锅头/洋河 列 " + "=" * 20)
allsh = pd.read_excel(REF, sheet_name="all data")
allsh.columns = [str(c).strip() for c in allsh.columns]
hits = [c for c in allsh.columns if re.search(r"天之蓝|二锅头|洋河|tianzhilan|erguotou", c, re.I)]
w("命中列: " + repr(hits))
w("全部样品列数=%d" % (len(allsh.columns) - 6))

# ---- C) PDF 单位扫描 ----
w("=" * 20 + " C) PDF 单位关键词 " + "=" * 20)
import fitz  # pymupdf
pdfs = {
    "D14": r"寒假中文文献\5种品牌浓香型白酒香气成分分析_杨斌.pdf",
    "D18": r"寒假中文文献\浓香型白酒及其风味成分对乙醇代谢关键酶酶活性的影响_曾礼兰.pdf",
    "D19": r"寒假中文文献\3个年份浓香型白酒香气成分比较研究_曹玉发.pdf",
    "D21": r"寒假中文文献\浓香型白酒基酒挥发性成分分析及等级识别研究_周轩.pdf",
    "D22": r"寒假中文文献\基于GC-QTOF_MS技术的浓香型白酒原酒质量等级评价_栗新峰.pdf",
    "D25": r"寒假中文文献\浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究_张恩.pdf",
    "D23": r"寒假中文文献\酱香型和浓香型白酒中香气物质及其差异研究_王晓欣.pdf",
}
unit_pat = re.compile(r"[^\n]{0,45}(?:mg\s*/\s*100\s*m[lL]|mg/100m[lL]|μg\s*/\s*100\s*m[lL]|ug/L|μg/L|mg/L|g/L|mg/kg|μg/kg|ng/L)[^\n]{0,25}")
for k, rel in pdfs.items():
    p = os.path.join(BASE, rel)
    if not os.path.exists(p):
        w(f"[{k}] 缺文件 {rel}"); continue
    doc = fitz.open(p)
    txt = "\n".join(pg.get_text() for pg in doc)
    doc.close()
    cnt = {}
    for u in ["mg/100 mL", "mg/100mL", "μg/L", "ug/L", "mg/L", "g/L", "mg/kg", "μg/kg", "ng/L", "μg/100"]:
        cnt[u] = len(re.findall(re.escape(u), txt, re.I))
    w(f"[{k}] 页数={len(fitz.open(p)) if False else ''} 字数={len(txt)} 单位计数={ {a:b for a,b in cnt.items() if b} }")
    # 打印含单位的表题/首句
    shown = 0
    for m in unit_pat.finditer(txt):
        s = m.group(0).replace("\n", " ").strip()
        if re.search(r"表\s*\d|Table\s*\d|含量|浓度|含量/(μg|mg)|OAV|阈值", s):
            w("    · " + s[:120])
            shown += 1
        if shown >= 8: break
    w("")

# ---- E) D25 原始行抽样 ----
w("=" * 20 + " E) D25 原始行(前60) " + "=" * 20)
D25 = "浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究"
src = pd.read_excel(SRC, sheet_name="清洗后数据")
d25 = src[src["文献名"] == D25]
for _, r in d25.head(60).iterrows():
    w("  样品=%-25r 类型=%-6s 数值=%-15r 化合物=%s" % (r["样品"], r["数据类型"], r["数值"], r["化合物"]))
w("...")
w("D25 样品x类型 交叉表:")
w(str(pd.crosstab(d25["样品"].astype(str), d25["数据类型"])))

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("OK ->", OUT)

# ---- D) D23 编码定义 ----
w2 = []
def w(s=""): w2.append(s)
D23PDF = os.path.join(BASE, r"寒假中文文献\酱香型和浓香型白酒中香气物质及其差异研究_王晓欣.pdf")
doc = fitz.open(D23PDF)
full = "\n".join(pg.get_text() for pg in doc)
doc.close()
w("总字数=%d" % len(full))
# 找样品定义段
for pat in [r"[^\n]{0,80}(?:C-20|J-20|D-20|n-c|n-g|n-s|n-d|j-c|C-lun|J-lun|D-lun)[^\n]{0,80}"]:
    seen = set()
    for m in re.finditer(pat, full):
        s = m.group(0).strip()
        if s in seen: continue
        seen.add(s)
        w("· " + s)
        if len(seen) > 60: break
w("\n--- 含 '轮次/取样/样品' 的定义句 ---")
for m in re.finditer(r"[^\n。]{0,100}(?:轮次|取样|样品编号|编号含义|分别记为|简写)[^\n。]{0,100}[。;]", full):
    w("· " + m.group(0).replace("\n", " ").strip()[:220])
with open(OUT2, "w", encoding="utf-8") as f:
    f.write("\n".join(w2))
print("OK ->", OUT2)
