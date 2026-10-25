# -*- coding: utf-8 -*-
"""verify_final: 一次性核实剩余疑点 -> verify_final.txt
1) D14 己酸乙酯原值 + 5种酒的香型描述
2) D21 清洗值在PDF中的上下文(找单位)
3) D22 样品名 + mg/L表核对
4) D26 己酸乙酯原值(97397?)
5) D7 分表 左半是否=右半*1000
6) D3/D6 分表按英文名定标
7) D25 全部行按化合物分组 + PDF表头裸dump
8) D23 编码归属核对(表2-1/2-2)
"""
import re, os, math, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
import pymupdf

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
SRC = BASE + r"\清洗后数据.xlsx"
REF = BASE + r"\data总库.xlsx"
OUT = BASE + r"\verify_final.txt"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

def parse_num(x):
    if x is None or (isinstance(x,float) and math.isnan(x)): return math.nan
    if isinstance(x,(int,float)): return float(x)
    s=str(x).strip().replace(",","")
    m=re.match(r"^([<>]?)\s*([-+]?\d[\d,]*\.?\d*)",s)
    if m:
        try: return float(m.group(2).replace(",",""))
        except ValueError: return math.nan
    try: return float(s)
    except ValueError: return math.nan

src = pd.read_excel(SRC, sheet_name="清洗后数据")

def doc(name):
    return src[src["文献名"] == name]

# ---------- 1) D14 ----------
w("="*16+" 1) D14 "+"="*16)
d14 = doc("5种品牌浓香型白酒香气成分分析")
eh = d14[d14["化合物"].astype(str).str.contains("己酸乙酯", na=False)]
for _,r in eh.iterrows():
    w(f"  己酸乙酯 样品={r['样品']!r} 类型={r['数据类型']} 数值={r['数值']}")
w("  D14全部样品名:", sorted(d14["样品"].astype(str).unique()))
p14 = os.path.join(BASE, r"寒假中文文献\5种品牌浓香型白酒香气成分分析_杨斌.pdf")
docx = pymupdf.open(p14); t14 = "\n".join(pg.get_text() for pg in docx); docx.close()
for m in re.finditer(r"[^\n]{0,80}(?:香型)[^\n]{0,80}", t14):
    s=re.sub(r"\s+"," ",m.group(0))
    if any(k in s for k in ["浓香","清香","酱香","样品","选择","种品牌"]):
        w("   · "+s[:170])

# ---------- 2) D21 ----------
w("="*16+" 2) D21 "+"="*16)
d21 = doc("浓香型白酒基酒挥发性成分分析及等级识别研究")
vals21 = set()
for _,r in d21.iterrows():
    v=parse_num(r["数值"])
    if not math.isnan(v): vals21.add(round(v,4))
p21 = os.path.join(BASE, r"寒假中文文献\浓香型白酒基酒挥发性成分分析及等级识别研究_周轩.pdf")
docx = pymupdf.open(p21); t21 = "\n".join(pg.get_text() for pg in docx); docx.close()
# 找几个中等清洗值在PDF中的上下文
sample_hits = []
for v in sorted(vals21):
    if 10 <= v <= 5000 and v == int(v) and int(v) % 1 == 0:
        pass
# 挑己酸乙酯行
eh21 = d21[d21["化合物"].astype(str).str.contains("己酸乙酯", na=False)]
w("  己酸乙酯行:")
for _,r in eh21.head(20).iterrows():
    w(f"    样品={r['样品']!r} 类型={r['数据类型']} 数值={r['数值']}")
# 在PDF中搜"己酸乙酯"上下文
cnt=0
for m in re.finditer(r"己酸乙酯", t21):
    s=re.sub(r"\s+","",t21[max(0,m.start()-80):m.end()+120])
    w("   · "+s[:200]); cnt+=1
    if cnt>=6: break
# 搜 u/L 关键词上下文
for kw in ["μg/L","ug/L","µg/L","μg·L","g/L"]:
    for m in re.finditer(re.escape(kw), t21):
        s=re.sub(r"\s+","",t21[max(0,m.start()-100):m.end()+60])
        w(f"   [{kw}] "+s[:170])
        break

# ---------- 3) D22 ----------
w("="*16+" 3) D22 "+"="*16)
d22 = doc("基于GC-QTOF_MS技术的浓香型白酒原酒质量等级评价")
w("  样品名:", sorted(d22["样品"].astype(str).unique())[:30])
eh22 = d22[d22["化合物"].astype(str).str.contains("己酸乙酯", na=False)]
for _,r in eh22.iterrows():
    w(f"  己酸乙酯 样品={r['样品']!r} 类型={r['数据类型']} 数值={r['数值']}")

# ---------- 4) D26 ----------
w("="*16+" 4) D26 "+"="*16)
d26 = doc("浓香型白酒基酒味觉特征与挥发性风味成分相关性研究")
w("  样品名:", sorted(d26["样品"].astype(str).unique())[:20])
eh26 = d26[d26["化合物"].astype(str).str.contains("己酸乙酯", na=False)]
for _,r in eh26.iterrows():
    w(f"  己酸乙酯 样品={r['样品']!r} 类型={r['数据类型']} 数值={r['数值']}")

# ---------- 5) D7 分表左右半 ----------
w("="*16+" 5) D7 分表左右半关系 "+"="*16)
sh = pd.read_excel(REF, sheet_name="3  Unraveling variation on the ")
sh.columns=[str(c).strip() for c in sh.columns]
w("  cols: "+str(list(sh.columns)))
def norm_cas(c):
    if c is None or (isinstance(c,float) and math.isnan(c)): return None
    s=str(c).strip().replace("–","-").replace("—","-").replace(" ","")
    return s if re.fullmatch(r"\d[\d\-]*\d|\d+", s) else None
left={}  # cas -> (BCSG,GJG,LZ)
right={}
for _,r in sh.iterrows():
    c=norm_cas(r.get("CAS number"))
    if c:
        vals=[parse_num(r.get(k)) for k in ["BC/SG","GJG","LZ"]]
        if any(not math.isnan(v) for v in vals): left[c]=vals
    c2=norm_cas(r.get("CAS"))
    if c2:
        vals=[parse_num(r.get(k)) for k in ["BCSG","GJG.1","LZ.1"]]
        if any(not math.isnan(v) for v in vals): right[c2]=vals
w(f"  left={len(left)} right={len(right)} 交集={len(set(left)&set(right))}")
rats=[]
for c in set(left)&set(right):
    for a,b in zip(left[c],right[c]):
        if a and b and not math.isnan(a) and not math.isnan(b) and b>0:
            rats.append(a/b)
if rats:
    rats=sorted(rats)
    w(f"  左/右 比值中位={np.median(rats):.6g} n={len(rats)} p25={np.percentile(rats,25):.6g} p75={np.percentile(rats,75):.6g}")

# ---------- 6) D3/D6 分表按名定标 ----------
w("="*16+" 6) D3/D6 分表按名定标 "+"="*16)
def name_key(s):
    return re.sub(r"\s+"," ",str(s).lower().strip()) if s is not None and not (isinstance(s,float) and math.isnan(s)) else ""
# D3
d3 = doc("Decoding the Molecular Mechanism of Cellar Aroma Loss")
c3={}
for _,r in d3[d3["数据类型"]=="浓度"].iterrows():
    k=name_key(r["化合物"]); v=parse_num(r["数值"])
    if k and not math.isnan(v) and v>0: c3.setdefault(k,[]).append(v)
c3={k:sorted(v)[len(v)//2] for k,v in c3.items()}
sh3 = pd.read_excel(REF, sheet_name="2  Decoding the Molecular Mecha")
sh3.columns=[str(c).strip() for c in sh3.columns]
rats=[]
for _,r in sh3.iterrows():
    k=name_key(r.get("Compounds"))
    if k in c3:
        for col in ["Concentration LZLJ-M7 (Mean ± SD)","Concentration LZLJ-T7 (Mean ± SD)"]:
            v=parse_num(r.get(col))
            if not math.isnan(v) and v>0: rats.append(c3[k]/v)
if rats:
    rats=sorted(rats); w(f"  D3 清洗/分表: n={len(rats)} 中位={np.median(rats):.6g} p25={np.percentile(rats,25):.6g} p75={np.percentile(rats,75):.6g}")
else: w("  D3 无名匹配")
# D6: 用 OAV*阈值 反推浓度
d6 = doc("Characterization of the differences in aroma-active compounds in")
w("  D6 数据类型:", d6["数据类型"].value_counts().to_dict())
c6={}
for _,r in d6[d6["数据类型"]=="浓度"].iterrows():
    k=name_key(r["化合物"]); v=parse_num(r["数值"])
    if k and not math.isnan(v) and v>0: c6.setdefault(k,[]).append(v)
c6={k:sorted(v)[len(v)//2] for k,v in c6.items()}
w(f"  D6 清洗浓度名数={len(c6)} 样品={sorted(d6['样品'].astype(str).unique())[:10]}")
sh6 = pd.read_excel(REF, sheet_name="3  Characterization of the diff")
sh6.columns=[str(c).strip() for c in sh6.columns]
rats=[]
for _,r in sh6.iterrows():
    k=name_key(r.get("Compound"))
    if k in c6:
        thr=parse_num(r.get("Odor Threshold (μg/L)")); oav=parse_num(r.get("Average OAV"))
        if not math.isnan(thr) and not math.isnan(oav) and thr>0 and oav>0:
            implied=thr*oav  # 浓度μg/L
            rats.append(c6[k]/implied)
if rats:
    rats=sorted(rats); w(f"  D6 清洗/(OAV*阈值μg/L): n={len(rats)} 中位={np.median(rats):.6g} p25={np.percentile(rats,25):.6g} p75={np.percentile(rats,75):.6g}")
else: w("  D6 无名匹配或无阈值")

# ---------- 7) D25 结构 ----------
w("="*16+" 7) D25 行结构 "+"="*16)
D25="浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究"
d25=doc(D25)
groups={}
order=[]
for _,r in d25.iterrows():
    c=str(r["化合物"])
    if c not in groups: groups[c]=[]; order.append(c)
    groups[c].append((r["样品"],r["数据类型"],r["数值"]))
for c in order[:6]:
    w(f"  [{c}]")
    for s,k,v in groups[c]: w(f"     {k:4s} 样品={s!r} 值={v}")
# 二锅头行属于哪些化合物(前后行)
n=0
for c in order:
    rows=groups[c]
    if any(str(s)=="二锅头" for s,_,_ in rows):
        w(f"  含二锅头: [{c}] -> "+"; ".join(f"{k}:{s}={v}" for s,k,v in rows))
        n+=1
        if n>=3: break

# ---------- 8) D23 表2-1/2-2 ----------
w("="*16+" 8) D23 表2-1 酱香样品清单 "+"="*16)
p23=os.path.join(BASE, r"寒假中文文献\酱香型和浓香型白酒中香气物质及其差异研究_王晓欣.pdf")
docx=pymupdf.open(p23); t23="\n".join(pg.get_text() for pg in docx); docx.close()
i=t23.find("表2-1")
if i>=0:
    w(re.sub(r"\s+"," ",t23[i:i+900]))

with open(OUT,"w",encoding="utf-8") as f: f.write("\n".join(L))
print("DONE ->",OUT)
