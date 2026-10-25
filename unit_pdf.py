# -*- coding: utf-8 -*-
"""单位硬核定标 v2: 清洗值 -> PDF原文数字 直接匹配
对每篇: 取清洗浓度值集合V, PDF文本数字集合T,
对每v, 检查是否存在 t in T 使 t/v ≈ factor(容差2%),
统计各factor命中数 -> 最可信因子。
输出 -> unit_pdf.txt
"""
import re, os, math, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
import pymupdf

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
SRC = BASE + r"\清洗后数据.xlsx"
OUT = BASE + r"\unit_pdf.txt"

DOCS = {
 1:"Characterization of key odorants causing the roasted and mud-like aromas in",
 2:"Key Aroma Compounds and Aroma Characteristics in",
 3:"Decoding the Molecular Mechanism of Cellar Aroma Loss",
 4:"Volatilomics and Lipidomics revealed flavoring mechanism in baijiu",
 5:"Impact of Pulsed Electric Fields Combined with Dissolved",
 6:"Characterization of the differences in aroma-active compounds in",
 7:"Unraveling variation on the profile aroma",
 8:"Aroma characterization and reconstitution of strong-aroma baijiu Insights",
 9:"Exploration of key aroma active compounds in strong flavor Baijiu during",
 10:"Investigation on the key factors associated with flavor quality in northern",
 11:"四川不同产区浓香型白酒风味物质差异化分析",
 12:"基于GC×GC-MS分析不同等级浓香型白酒的关键风味化合物",
 13:"基于全二维气相色谱-飞行时间质谱结合多元统计方法解析芝麻香型白酒的风味组分研究",
 14:"5种品牌浓香型白酒香气成分分析",
 15:"不同贮存年份的五粮浓香型白酒挥发性风味物质对比分析",
 16:"浓香、酱香、清香型白酒挥发性风味的特征与差异研究",
 17:"三种香型白酒的ICP-OES和GC-QTOF_MS分析及判别研究",
 18:"浓香型白酒及其风味成分对乙醇代谢关键酶酶活性的影响",
 19:"3个年份浓香型白酒香气成分比较研究",
 20:"山东沂蒙老区浓香型白酒特征风味研究",
 21:"浓香型白酒基酒挥发性成分分析及等级识别研究",
 22:"基于GC-QTOF_MS技术的浓香型白酒原酒质量等级评价",
 23:"酱香型和浓香型白酒中香气物质及其差异研究",
 24:"洋河绵柔型白酒关键风味成分",
 25:"浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究",
 26:"浓香型白酒基酒味觉特征与挥发性风味成分相关性研究",
 27:"宜宾产区浓香型白酒风味特征及香气活性物质鼻后释放规律的研究",
}
PDF = {
 1:r"定性定量\2  Characterization of key odorants causing the roasted and mud-like aromas in.pdf",
 2:r"定性定量\5  Key Aroma Compounds and Aroma Characteristics in.pdf",
 3:r"定性定量\2  Decoding the Molecular Mechanism of Cellar Aroma Loss.pdf",
 4:r"定性定量\2  Volatilomics and Lipidomics revealed flavoring mechanism in baijiu.pdf",
 5:r"定性定量\5  Impact of Pulsed Electric Fields Combined with Dissolved.pdf",
 6:r"定性定量\3  Characterization of the differences in aroma-active compounds in.pdf",
 7:r"定性定量\3  Unraveling variation on the profile aroma.pdf",
 8:r"定性定量\10  Aroma characterization and reconstitution of strong-aroma baijiu Insights.pdf",
 9:r"定性定量\8  Exploration of key aroma active compounds in strong flavor Baijiu during.pdf",
 10:r"定性定量\3  Investigation on the key factors associated with flavor quality in northern.pdf",
 11:r"寒假中文文献\四川不同产区浓香型白酒风味物质差异化分析_关宝义.pdf",
 12:r"寒假中文文献\基于GC×GC-MS分析不同等级浓香型白酒的关键风味化合物_陈乙源.pdf",
 13:r"寒假中文文献\基于全二维气相色谱-飞行时间质谱结合多元统计方法解析芝麻香型白酒的风味组分研究_江伟.pdf",
 14:r"寒假中文文献\5种品牌浓香型白酒香气成分分析_杨斌.pdf",
 15:r"寒假中文文献\不同贮存年份的五粮浓香型白酒挥发性风味物质对比分析_胥佳.pdf",
 16:r"寒假中文文献\浓香、酱香、清香型白酒挥发性风味的特征与差异研究_张卜升.pdf",
 17:r"寒假中文文献\三种香型白酒的ICP-OES和GC-QTOF_MS分析及判别研究_卓俊纳.pdf",
 18:r"寒假中文文献\浓香型白酒及其风味成分对乙醇代谢关键酶酶活性的影响_曾礼兰.pdf",
 19:r"寒假中文文献\3个年份浓香型白酒香气成分比较研究_曹玉发.pdf",
 20:r"寒假中文文献\山东沂蒙老区浓香型白酒特征风味研究_张伟建.pdf",
 21:r"寒假中文文献\浓香型白酒基酒挥发性成分分析及等级识别研究_周轩.pdf",
 22:r"寒假中文文献\基于GC-QTOF_MS技术的浓香型白酒原酒质量等级评价_栗新峰.pdf",
 23:r"寒假中文文献\酱香型和浓香型白酒中香气物质及其差异研究_王晓欣.pdf",
 24:r"寒假中文文献\洋河绵柔型白酒关键风味成分_范文来.pdf",
 25:r"寒假中文文献\浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究_张恩.pdf",
 26:r"寒假中文文献\浓香型白酒基酒味觉特征与挥发性风味成分相关性研究_路瑞.pdf",
 27:r"寒假中文文献\宜宾产区浓香型白酒风味特征及香气活性物质鼻后释放规律的研究_相里冉.pdf",
}
CURRENT = {1:1,2:1,3:1,4:1,5:1000,6:1,7:1,8:1,9:1000,10:1000,11:1000,12:1000,13:1,
 14:1,15:1,16:1,17:1,18:1,19:1000,20:1,21:1,22:1,23:1,24:1000,25:1,26:1,27:1}
FACTORS = [1, 1000, 0.001, 10000, 0.01, 1e6, 1e-6, 100, 0.1]

num_re = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")

def pdf_numbers(path):
    doc = pymupdf.open(path)
    txt = "\n".join(pg.get_text() for pg in doc)
    doc.close()
    vals = []
    for m in num_re.finditer(txt):
        try: v = float(m.group(0))
        except ValueError: continue
        if 1e-6 < abs(v) < 1e9: vals.append(v)
    # 也处理 ×10^ 上标形式: "2.71×104" 常见(上标丢失)
    for m in re.finditer(r"(\d+\.\d+)\s*[×x]\s*10\s*(\d{1,3})", txt):
        try: vals.append(float(m.group(1)) * 10 ** int(m.group(2)))
        except ValueError: pass
    return np.unique(np.array(vals))

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

lines = []
for i, lit in sorted(DOCS.items()):
    p = os.path.join(BASE, PDF.get(i, ""))
    if not os.path.exists(p):
        lines.append(f"[{i:2d}] 缺PDF"); continue
    T = pdf_numbers(p)
    if len(T) == 0:
        lines.append(f"[{i:2d}] PDF无数字"); continue
    g = src[src["文献名"] == lit]
    V = []
    for _, r in g.iterrows():
        if r["数据类型"] != "浓度": continue
        v = parse_num(r["数值"])
        if not math.isnan(v) and v > 0: V.append(v)
    V = np.unique(np.array(V))
    if len(V) == 0:
        lines.append(f"[{i:2d}] 无浓度值 (PDF数字={len(T)})"); continue
    # 因子命中统计: 对每个v*factor, 是否在T中(相对容差2%)
    hits = {f: 0 for f in FACTORS}
    for f in FACTORS:
        targets = V * f
        # searchsorted 容差匹配
        idx = np.searchsorted(T, targets)
        for j, t in enumerate(targets):
            best = None
            for k in (idx[j] - 1, idx[j], idx[j] + 1):
                if 0 <= k < len(T):
                    if abs(T[k] - t) <= 0.02 * t: best = T[k]; break
            if best is not None: hits[f] += 1
    tot = len(V)
    ranking = sorted(hits.items(), key=lambda x: -x[1])
    cur = CURRENT[i]
    seg = " ".join(f"{f:g}:{hits[f]}/{tot}({100*hits[f]/tot:.0f}%)" for f, c in ranking if c > 0)
    best_f, best_c = ranking[0]
    flag = "OK" if best_f == cur else f"!! 当前x{cur:g} vs 最佳x{best_f:g}"
    lines.append(f"[{i:2d}] V={tot} T={len(T)} {flag} | {seg}")
    print(lines[-1])

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("DONE ->", OUT)
