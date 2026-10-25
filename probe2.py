# -*- coding: utf-8 -*-
"""probe2: 
1) 英文PDF文本抽取调试(D1-D10)
2) 中文PDF表头单位标签(D11-D27重点14/21/22/25/26)
3) D3/D6/D7分表 vs 清洗值 定标
4) D25 表格结构/样品列
5) D21 关键值核对(234.3/163.87等 mg/100mL)
6) D23 编码定义
输出 -> probe2.txt
"""
import re, os, math, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
import pymupdf

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
SRC = BASE + r"\清洗后数据.xlsx"
REF = BASE + r"\data总库.xlsx"
OUT = BASE + r"\probe2.txt"
L = []
def w(s=""): L.append(str(s))

# ---------- 1) 英文PDF调试 ----------
w("=" * 15 + " 1) 英文PDF文本抽取(D1-D10) " + "=" * 15)
EN = {
 1:r"定性定量\2  Characterization of key odorants causing the roasted and mud-like aromas in.pdf",
 3:r"定性定量\2  Decoding the Molecular Mechanism of Cellar Aroma Loss.pdf",
 6:r"定性定量\3  Characterization of the differences in aroma-active compounds in.pdf",
 7:r"定性定量\3  Unraveling variation on the profile aroma.pdf",
}
for k, rel in EN.items():
    p = os.path.join(BASE, rel)
    if not os.path.exists(p): w(f"[{k}] 缺文件"); continue
    doc = pymupdf.open(p)
    txt = "\n".join(pg.get_text() for pg in doc)
    doc.close()
    nnum = len(re.findall(r"\d+\.\d+", txt))
    w(f"[{k}] chars={len(txt)} decimals={nnum} head={txt[:120]!r}")

# ---------- 2) 中文PDF表头单位标签 ----------
w("=" * 15 + " 2) 中文PDF单位标签行 " + "=" * 15)
ZH = {
 14:r"寒假中文文献\5种品牌浓香型白酒香气成分分析_杨斌.pdf",
 19:r"寒假中文文献\3个年份浓香型白酒香气成分比较研究_曹玉发.pdf",
 21:r"寒假中文文献\浓香型白酒基酒挥发性成分分析及等级识别研究_周轩.pdf",
 22:r"寒假中文文献\基于GC-QTOF_MS技术的浓香型白酒原酒质量等级评价_栗新峰.pdf",
 25:r"寒假中文文献\浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究_张恩.pdf",
 26:r"寒假中文文献\浓香型白酒基酒味觉特征与挥发性风味成分相关性研究_路瑞.pdf",
 18:r"寒假中文文献\浓香型白酒及其风味成分对乙醇代谢关键酶酶活性的影响_曾礼兰.pdf",
}
unit_kw = re.compile(r"(?:μ|µ|u)g\s*/\s*(?:100\s*)?m[lL]|mg\s*/\s*(?:100\s*)?m[lL]|g\s*/\s*(?:100\s*)?m[lL]|mg\s*/\s*L|(?:μ|µ)g\s*/\s*L|g\s*/\s*L|mg\s*·\s*L|g\s*·\s*L|mg/kg|ng/mL", re.I)
for k, rel in sorted(ZH.items()):
    p = os.path.join(BASE, rel)
    doc = pymupdf.open(p); txt = "\n".join(pg.get_text() for pg in doc); doc.close()
    w(f"\n[{k}] chars={len(txt)}")
    seen = set(); cnt = 0
    for m in unit_kw.finditer(txt):
        s = txt[max(0, m.start()-50):m.end()+20].replace("\n", " ").strip()
        s = re.sub(r"\s+", " ", s)
        if s in seen: continue
        seen.add(s); cnt += 1
        w("   · " + s[:110])
        if cnt >= 12: break

# ---------- 3) D3/D6/D7分表定标 ----------
w("\n" + "=" * 15 + " 3) 分表 vs 清洗 定标 " + "=" * 15)
src = pd.read_excel(SRC, sheet_name="清洗后数据")
def parse_num(x):
    if x is None or (isinstance(x, float) and math.isnan(x)): return math.nan
    if isinstance(x, (int, float)): return float(x)
    s = str(x).strip().replace(",", "")
    m = re.match(r"^([<>]?)\s*([-+]?\d[\d,]*\.?\d*)", s)
    if m:
        try: return float(m.group(2).replace(",", ""))
        except ValueError: return math.nan
    try: return float(s)
    except ValueError: return math.nan
def norm_cas(c):
    if c is None or (isinstance(c, float) and math.isnan(c)): return None
    s = str(c).strip().replace("–", "-").replace("—", "-").replace(" ", "")
    return s if re.fullmatch(r"\d[\d\-]*\d|\d+", s) else None

DLIT = {
 3:"Decoding the Molecular Mechanism of Cellar Aroma Loss",
 6:"Characterization of the differences in aroma-active compounds in",
 7:"Unraveling variation on the profile aroma",
}
# 清洗侧: CAS -> 中位浓度值(原始单位)
clean_v = {}
for d in DLIT.values():
    g = src[(src["文献名"] == d) & (src["数据类型"] == "浓度")]
    for _, r in g.iterrows():
        c = norm_cas(r["CAS号"]); v = parse_num(r["数值"])
        if c and not math.isnan(v) and v > 0:
            clean_v.setdefault(d, {}).setdefault(c, []).append(v)
for d in clean_v:
    clean_v[d] = {c: sorted(v)[len(v)//2] for c, v in clean_v[d].items()}

def calib(sheet, d, val_cols, cas_col, name_col):
    sh = pd.read_excel(REF, sheet_name=sheet)
    sh.columns = [str(c).strip() for c in sh.columns]
    w(f"\n[{sheet}] 列={list(sh.columns)}")
    cv = clean_v.get(d, {})
    w(f"  清洗CAS数={len(cv)}")
    for vc in val_cols:
        if vc not in sh.columns: 
            w(f"  缺列 {vc}"); continue
        ratios = []
        for _, rr in sh.iterrows():
            c = norm_cas(rr.get(cas_col)) if cas_col else None
            v = parse_num(rr.get(vc))
            if c and c in cv and not math.isnan(v) and v > 0:
                ratios.append(cv[c] / v)
        if ratios:
            r = np.array(ratios)
            med = float(np.median(r))
            w(f"  {vc}: n={len(r)} 比值中位={med:.4g}  p25={np.percentile(r,25):.4g}  p75={np.percentile(r,75):.4g}")
        else:
            w(f"  {vc}: 无CAS重叠")

calib("2  Decoding the Molecular Mecha", DLIT[3],
      ["Concentration LZLJ-M7 (Mean ± SD)", "Concentration LZLJ-T7 (Mean ± SD)"],
      None, None)  # 该表无CAS列? 先看列
calib("3  Characterization of the diff", DLIT[6], ["OAV Sample 1", "OAV Sample 2", "OAV Sample 3", "Average OAV"], None, None)
calib("3  Unraveling variation on the ", DLIT[7], ["BC/SG", "GJG", "LZ", "(mg L⁻¹)", "BCSG"], "CAS", None)

# ---------- 4) D25 表格 ----------
w("\n" + "=" * 15 + " 4) D25 PDF表格 " + "=" * 15)
p25 = os.path.join(BASE, ZH[25])
doc = pymupdf.open(p25)
for pno, pg in enumerate(doc):
    try:
        tabs = pg.find_tables()
    except Exception as e:
        w(f"page{pno} find_tables异常 {e}"); continue
    for ti, t in enumerate(tabs.tables):
        try:
            data = t.extract()
        except Exception:
            continue
        if not data: continue
        head = data[0]
        # 找含天之蓝/二锅头/浓度/OAV的表头
        htxt = " | ".join(str(x) if x else "" for x in head)
        if re.search(r"天之蓝|二锅头|浓度|OAV|阈值|含量", htxt):
            w(f"page{pno} table{ti} rows={len(data)} head={htxt[:200]}")
            for row in data[1:4]:
                w("    " + " | ".join(str(x)[:22] if x else "" for x in row))
doc.close()

# ---------- 5) D21 关键值 ----------
w("\n" + "=" * 15 + " 5) D21 关键值核对 " + "=" * 15)
d21 = src[(src["文献名"] == DLIT[21] if False else src["文献名"] == "浓香型白酒基酒挥发性成分分析及等级识别研究")]
vals21 = set()
for _, r in d21.iterrows():
    v = parse_num(r["数值"])
    if not math.isnan(v): vals21.add(round(v, 2))
for probe_v in [234.30, 163.87, 61.58, 21.57, 5.256, 9.23, 700, 17.40, 8.32, 20.92]:
    hit = probe_v in vals21 or any(abs(x - probe_v) < 0.01 for x in vals21)
    w(f"  {probe_v} 在清洗D21值中: {hit}")
# 清洗D21里己酸乙酯等大值化合物
d21c = d21[d21["数据类型"] == "浓度"]
big = d21c.copy(); big["vn"] = big["数值"].apply(parse_num)
big = big.dropna(subset=["vn"]).sort_values("vn", ascending=False).head(8)
for _, r in big.iterrows():
    w(f"  大值: {r['化合物']} = {r['vn']} 样品={r['样品']}")

# ---------- 6) D23 编码定义 ----------
w("\n" + "=" * 15 + " 6) D23 编码定义 " + "=" * 15)
p23 = os.path.join(BASE, r"寒假中文文献\酱香型和浓香型白酒中香气物质及其差异研究_王晓欣.pdf")
doc = pymupdf.open(p23); full = "\n".join(pg.get_text() for pg in doc); doc.close()
# 找表标题行: 含样品编号的完整表格头
pats = [
    r"[^\n]{0,60}(?:浓香型白酒样品|酱香型白酒样品|董香|豉香|小曲清香|大曲清香)[^\n]{0,80}",
    r"[^\n]{0,80}(?:分别表示|分别代表|代表|缩写|简称|记为)[^\n]{0,120}",
    r"C-(?:19|20)\d\d[^\n]{0,60}",
]
seen = set()
for pat in pats:
    for m in re.finditer(pat, full):
        s = re.sub(r"\s+", " ", m.group(0)).strip()
        if s in seen: continue
        seen.add(s)
        w("  · " + s[:200])
        if len(seen) > 40: break
# 上下文: C-2013 前后200字
i = full.find("C-2013")
if i >= 0:
    w("\n  --C-2013上下文--")
    w("  " + re.sub(r"\s+", " ", full[max(0, i-400):i+400]))
i = full.find("n-d-2000")
if i >= 0:
    w("\n  --n-d-2000上下文--")
    w("  " + re.sub(r"\s+", " ", full[max(0, i-400):i+300]))

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE ->", OUT)
