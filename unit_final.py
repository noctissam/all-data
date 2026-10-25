# -*- coding: utf-8 -*-
"""各清洗文献浓度量级 + 最终单位判定表"""
import re, math
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
SRC = BASE + r"\清洗后数据.xlsx"
OUT = BASE + r"\unit_final.txt"

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

# 定标结论(样品重叠>=2 或 干净比值): 文献 -> (因子, 依据)
# 因子: 清洗值 * 因子 = μg/L
conf = {
 "Characterization of key odorants causing the roasted and mud-like aromas in": (1, "分表单位μg/L + 名称定标比值1.0(88化合物)"),
 "Key Aroma Compounds and Aroma Characteristics in": (1, "总库Y列μg/L; 无重叠, 量级核对"),
 "Decoding the Molecular Mechanism of Cellar Aroma Loss": (1, "分表μg/L(阈值/浓度), 低置信"),
 "Volatilomics and Lipidomics revealed flavoring mechanism in baijiu": (1, "仅OAV, 分表阈值μg/L"),
 "Impact of Pulsed Electric Fields Combined with Dissolved": (1000, "分表(mg/L) + 定标比值≈1"),
 "Characterization of the differences in aroma-active compounds in": (1, "分表仅OAV/阈值μg/L, 浓度存疑"),
 "Unraveling variation on the profile aroma": (1, "总库μg/L, 低置信"),
 "Aroma characterization and reconstitution of strong-aroma baijiu Insights": (1, "分表'10 Aroma...'μg/L"),
 "Exploration of key aroma active compounds in strong flavor Baijiu during": (1000, "分表Concentration(mg/L)"),
 "Investigation on the key factors associated with flavor quality in northern": (1000, "定标比值0.001(A,B重叠) + 分表mg/L"),
 "四川不同产区浓香型白酒风味物质差异化分析": (1000, "定标比值0.001(CJ/DJ/LJ重叠3)"),
 "基于GC×GC-MS分析不同等级浓香型白酒的关键风味化合物": (1000, "定标比值0.001(A/B/C重叠3)"),
 "基于全二维气相色谱-飞行时间质谱结合多元统计方法解析芝麻香型白酒的风味组分研究": (1, "芝麻香-将剔除"),
 "5种品牌浓香型白酒香气成分分析": (1, "量级核对(待定)"),
 "不同贮存年份的五粮浓香型白酒挥发性风味物质对比分析": (1, "定标比值0.958(206化合物)"),
 "浓香、酱香、清香型白酒挥发性风味的特征与差异研究": (1, "总库'19 LZ /(μg/L)'"),
 "三种香型白酒的ICP-OES和GC-QTOF_MS分析及判别研究": (1, "三种香对比-将剔除"),
 "浓香型白酒及其风味成分对乙醇代谢关键酶酶活性的影响": (1, "总库总doc22 μg/L(SC1/2/3比值0.84), 低置信"),
 "3个年份浓香型白酒香气成分比较研究": (1, "量级核对(待定)"),
 "山东沂蒙老区浓香型白酒特征风味研究": (1, "定标比值0.997(9样品/462化合物)"),
 "浓香型白酒基酒挥发性成分分析及等级识别研究": (1, "总库'一级好酒(μ/L)', 低置信"),
 "基于GC-QTOF_MS技术的浓香型白酒原酒质量等级评价": (1, "总库总doc27 μg/L, 低置信"),
 "酱香型和浓香型白酒中香气物质及其差异研究": (1, "定标比值0.835(13样品/712化合物)"),
 "洋河绵柔型白酒关键风味成分": (1000, "定标比值0.001(TZL/MZL/HZL重叠5)"),
 "浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究": (1, "量级核对(待定)"),
 "浓香型白酒基酒味觉特征与挥发性风味成分相关性研究": (1, "定标比值1.0(4样品); 总库标g/L存疑"),
 "宜宾产区浓香型白酒风味特征及香气活性物质鼻后释放规律的研究": (1, "总库总doc33 μg/L"),
}

with open(OUT,"w",encoding="utf-8") as f:
    f.write("文献 | 因子 | 浓度中位 | 浓度90分位 | 浓度max | 依据\n")
    for i,(lit,g) in enumerate(src.groupby("文献名",sort=False),1):
        vals=[parse_num(v) for v in g[g["数据类型"]=="浓度"]["数值"]]
        vals=[v for v in vals if not math.isnan(v) and v>0]
        if vals:
            vals.sort()
            med=vals[len(vals)//2]; p90=vals[int(len(vals)*0.9)]; mx=vals[-1]
        else:
            med=p90=mx=math.nan
        fac,srcdesc = conf.get(lit,(1,"未分类"))
        f.write(f"[{i:2d}] x{fac:<5} med={med:<12.4g} p90={p90:<12.4g} max={mx:<12.4g} | {lit[:34]} | {srcdesc}\n")
print("DONE -> unit_final.txt")
