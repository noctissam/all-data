# -*- coding: utf-8 -*-
"""
浓香型数据库 v2
- 单位统一换算成 μg/L(逐篇文献判定换算因子)
- 6篇丢样品名文献: 回溯 data总库 分表补回样品名/数据
- 只保留浓香型样品列(剔除酱香/清香等)
- 样品名清洗归并(酒等级、感官词等)
输出 浓香型数据库.xlsx + 多张复核表
"""
import re, math
import pandas as pd
import numpy as np

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
SRC = BASE + r"\清洗后数据.xlsx"
REF = BASE + r"\data总库.xlsx"
OUT = BASE + r"\浓香型数据库.xlsx"

# ============ 配置: 每篇文献 ============
# (key用清洗后数据文献名; 因子: 清洗值*因子=μg/L)
D1  = "Characterization of key odorants causing the roasted and mud-like aromas in"
D2  = "Key Aroma Compounds and Aroma Characteristics in"
D3  = "Decoding the Molecular Mechanism of Cellar Aroma Loss"
D4  = "Volatilomics and Lipidomics revealed flavoring mechanism in baijiu"
D5  = "Impact of Pulsed Electric Fields Combined with Dissolved"
D6  = "Characterization of the differences in aroma-active compounds in"
D7  = "Unraveling variation on the profile aroma"
D8  = "Aroma characterization and reconstitution of strong-aroma baijiu Insights"
D9  = "Exploration of key aroma active compounds in strong flavor Baijiu during"
D10 = "Investigation on the key factors associated with flavor quality in northern"
D11 = "四川不同产区浓香型白酒风味物质差异化分析"
D12 = "基于GC×GC-MS分析不同等级浓香型白酒的关键风味化合物"
D13 = "基于全二维气相色谱-飞行时间质谱结合多元统计方法解析芝麻香型白酒的风味组分研究"
D14 = "5种品牌浓香型白酒香气成分分析"
D15 = "不同贮存年份的五粮浓香型白酒挥发性风味物质对比分析"
D16 = "浓香、酱香、清香型白酒挥发性风味的特征与差异研究"
D17 = "三种香型白酒的ICP-OES和GC-QTOF_MS分析及判别研究"
D18 = "浓香型白酒及其风味成分对乙醇代谢关键酶酶活性的影响"
D19 = "3个年份浓香型白酒香气成分比较研究"
D20 = "山东沂蒙老区浓香型白酒特征风味研究"
D21 = "浓香型白酒基酒挥发性成分分析及等级识别研究"
D22 = "基于GC-QTOF_MS技术的浓香型白酒原酒质量等级评价"
D23 = "酱香型和浓香型白酒中香气物质及其差异研究"
D24 = "洋河绵柔型白酒关键风味成分"
D25 = "浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究"
D26 = "浓香型白酒基酒味觉特征与挥发性风味成分相关性研究"
D27 = "宜宾产区浓香型白酒风味特征及香气活性物质鼻后释放规律的研究"

DOCS = [D1,D2,D3,D4,D5,D6,D7,D8,D9,D10,D11,D12,D13,D14,D15,D16,D17,
        D18,D19,D20,D21,D22,D23,D24,D25,D26,D27]
DOC_IDX = {d:i+1 for i,d in enumerate(DOCS)}

# 换算因子 (26-03-20 补做: 逐PDF表头核对单位后修正)
UNIT_FACTOR = {
 D1:1, D2:1, D3:1, D4:1, D5:1000, D6:1, D7:1, D8:1, D9:1000, D10:1000,
 D11:1000, D12:1000, D13:1, D14:1000, D15:1, D16:1, D17:1, D18:1, D19:1000,
 D20:1, D21:1, D22:1000, D23:1, D24:1000, D25:1, D26:1, D27:1,
}
UNIT_BASIS = {
 D1:"分表μg/L+定标比值1.0", D2:"总库Y列μg/L(量级核对)",
 D3:"分表Concentration(μg/L)+量级核验(乙酸乙酯4.0e6/己酸乙酯8.7e5仅μg/L合理);分表回溯补浓度列",
 D4:"仅OAV,阈值μg/L", D5:"分表(mg/L)+定标≈1",
 D6:"分表仅OAV;量级核验(max2.4e5仅μg/L合理)(低置信)",
 D7:"量级核验(max5.3e4仅μg/L合理)(低置信)", D8:"分表'10 Aroma'μg/L",
 D9:"分表Concentration(mg/L)",
 D10:"定标0.001(A,B)+分表mg/L", D11:"原文献表1'质量浓度(mg/L)'表头(已确认);定标0.001(CJ/DJ/LJ)", D12:"原文献表1'含量/(mg·L⁻¹)'表头(已确认);浓度(小数)与OAV(整数)分流",
 D13:"芝麻香-整篇剔除",
 D14:"表2'质量浓度/(mg·L⁻¹)'原文献表头+己酸乙酯215-249>200mg/L",
 D15:"定标0.958(206化合物)",
 D16:"总库'19 LZ/(μg/L)'", D17:"三种香对比-整篇剔除",
 D18:"原文献'含量(μg/L)'表头+总量1.3-3.5e6μg/L",
 D19:"原文献'相对浓度/(mg/L)'表头(已确认)",
 D20:"定标0.997(9样品/462)",
 D21:"清洗值实为量比表(基准己酸乙酯=1)/FD表,非绝对浓度→浓度列剔除;OAV保留",
 D22:"原文献表3'(mg/L)'表头+标准液53.8-2427.5mg/L量程吻合",
 D23:"定标0.835(13样品/712)+附表μg/L", D24:"定标0.001(TZL/MZL/HZL)",
 D25:"'浓度(μg/L)'表头(阈值行核验OAV=浓度/阈值)", D26:"定标1.0;论文标mg/L实为μg/L(97g/L不可能)",
 D27:"总库总doc33 μg/L",
}
# 整篇剔除(非浓香型)
EXCLUDE_DOC = {D13:"芝麻香型", D17:"三种香型对比且样品名丢失"}

# 浓度列剔除(数据清洗时取错表,数值非绝对浓度): 文献 -> 原因
DROPCONC = {
 D21:"清洗到的是量比表(以己酸乙酯=1为基准)与FD因子表(1/4096等),真实浓度表为mg/100mL未进入清洗数据",
}

# D12/D24: 原文表内浓度与OAV块在清洗时均标为'浓度' -> 按规则分流
# 规则: 同(化合物,样品)多行 -> 最大值=浓度(块), 其余=OAV; 单行 -> 整数=OAV, 小数=浓度
# 依据: D12己酸乙酯A 56663=原文表1 OAV 56656, 丁酸乙酯A 5213=原文OAV 5213(均为整数);
#       D24己酸乙酯 36041=原文OAV(>27000,均值34799), 1994.14=原文表1浓度(mg/L,小数)
OAV_MIXED = {D12, D24}

# 香型剔除: 文献 -> {样品: 剔除原因}
AROMA_REMOVE = {
 D16: {"ZSW/":"香型不明(疑似非浓香)"},
 D23: {"茅台酒":"酱香型","习酒":"酱香型","习酒·窖藏1988":"酱香型","酱香型酒":"酱香型",
        "酱香":"酱香型感官词","香":"感官词","甜":"感官词","窖底":"感官词","底":"感官词",
        "碱":"感官词","碱 酸":"感官词","醇甜":"感官词","中":"感官词","原酒":"感官词"},
 D25: {"二锅头":"清香型"},
}
# D23编码样品核对(论文表2-1=酱香型样品: j/c/d-年份=上层酱香/中层醇甜/下层窖底原酒,
# c-lun/j-lun=轮次醇甜/酱香原酒;附表5大写J/C/D-*同为酱香型习酒原酒;
# 表2-2=浓香型样品: n-g/n-c=浓香成品, n-d=单粮原酒, n-s=多粮原酒 -> 保留)
_d23 = AROMA_REMOVE[D23]
for _c in ("C","J","D"):
    for _y in range(1990,2015):
        _d23[f"{_c}-{_y}"] = "酱香型原酒(表2-1/附表5)"
        _d23[f"{_c.lower()}-{_y}"] = "酱香型原酒(表2-1)"
for _n in range(1,8):
    for _p in ("C-lun","J-lun","D-lun","c-lun","j-lun","d-lun"):
        _d23[f"{_p}-{_n}"] = "酱香型轮次原酒(表2-1)"
_d23.update({"j-c-1":"酱香型成品酒(表2-1)","j-c-2":"酱香型成品酒(表2-1)"})

# 样品名归并: 文献 -> {清洗后样品: 规范名 或 None=丢弃}
SAMPLE_MAP = {
 D21: {"一级差酒":"一级差酒","一级 好酒":"一级好酒","一级 差酒":"一级差酒",
        "一级 差酒 H":"一级差酒","二级好酒":"二级好酒","二级差酒":"二级差酒","三级酒":"三级酒",
        "一级":None,"二级":None,"三级":None,"好酒":None,"差酒":None,
        "差酒 LH":None,"好酒 >工":None,"二级 差酒 三级 酒":None,"差酒 二级 三级酒":None},
 D6:  {"Average":None},
}

# 分表回溯: 文献 -> 分表名 (从data总库分表补数据)
RECOVER = {
 D2:"5  Key Aroma Compounds and Arom",
 D3:"2  Decoding the Molecular Mecha",
 D4:"2  Volatilomics and Lipidomics ",
 D5:"5  Impact of Pulsed Electric Fi",
 D9:"8  Exploration of key aroma act",
}
# 分表 -> (类型, [(列名,样品名)], 化合物列, CAS列, 单位因子)
RECOVER_SPEC = {
 D2: ("conc", [("Y1","Y1"),("Y3","Y3"),("Y5","Y5"),("Y8","Y8"),("Y11","Y11")], "flavor components", "CAS", 1),
 D3: ("conc", [("Concentration LZLJ-M7 (Mean ± SD)","LZLJ-M7"),
               ("Concentration LZLJ-T7 (Mean ± SD)","LZLJ-T7")], "Compounds", None, 1),
 D4: ("oav",  [("OAV LS","LS"),("OAV FS","FS")], "Aroma compound", None, 1),
 D5: ("conc", [("Blank (mg/L)","Blank"),("S1 (mg/L)","S1"),("S2 (F3) (mg/L)","S2 (F3)"),
               ("S3 (mg/L)","S3"),("F1 (mg/L)","F1"),("F3 (mg/L)","F3")], "Compound Name", None, 1000),
 D9: ("conc", [(f"Concentration (mg/L) - {i}", str(i)) for i in range(1,9)],
       "Aroma compounds", None, 1000),
}

# ============ 工具 ============
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

def norm_cas(c):
    if c is None or (isinstance(c,float) and math.isnan(c)): return None
    s=str(c).strip().replace("–","-").replace("—","-").replace(" ","")
    return s if re.fullmatch(r"\d[\d\-]*\d|\d+", s) else None

def has_cjk(s): return bool(re.search(r"[一-鿿]", s))

def clean_sample(s):
    if s is None: return None
    t=str(s).strip()
    if t=="" or t.lower()=="nan": return None
    junk=re.compile(r"^(nan|nd|n\.d\.?|—|--|－|/|-|<1|<0\.001|>100|>10|>1)$|^[\d\.\s±<>±]+$"
        r"|浓度|含量|量比|平均|序号|编号|No\.?|Category|ion|p值|SD|OAV值?|配度|加标|添加|重复性|稳定性"
        r"|\(I%\)|乙醛脱氢酶|^esters?$|^alcohols?$|^acids?$|^aldehydes?$|^ketones?$|^phenols?$"
        r"|^others?$|^totals?$|^compounds?$|^aroma|^酯类$|^醇类$|^酸类$|^醛类$|^酮类$|^酚类$"
        r"|^其他$|^总计$|^合计$"
        r"|mg\s*/?\s*l|μg\s*/?\s*l|g\s*/?\s*l|mg·l|μg·l|g·l|mg/L|μg/L|g/L", re.IGNORECASE)
    if junk.search(t): return None
    t2=re.sub(r"(?<=[A-Z0-9])[a-z]{1,2}$","",t).strip()
    if t2=="" or re.fullmatch(r"[\d\.]+",t2): return None
    return t2

# ============ 读取 & 展开清洗后数据 ============
src = pd.read_excel(SRC, sheet_name="清洗后数据")
src["CASk"]=src["CAS号"].apply(norm_cas)

# 收集化合物主键信息
# 名称->CAS索引(用于无CAS行归并: 如D24 OAV行名称为'乙酸乙酯ethyl acetate'粘连形式)
name2cas={}
for _,r in src.iterrows():
    if r["CASk"] and pd.notna(r["化合物"]):
        _nm=re.sub(r"\s+"," ",str(r["化合物"]).lower().strip())
        name2cas.setdefault(_nm, r["CASk"])
def compkey(row):
    if row["CASk"]: return "CAS:"+row["CASk"]
    nm=re.sub(r"\s+"," ",str(row["化合物"]).lower().strip()) if pd.notna(row["化合物"]) else ""
    c=name2cas.get(nm)
    if c: return "CAS:"+c
    # 中英粘连名: 拆中文前缀/英文后缀分别查
    m=re.match(r"^([一-鿿]+)\s*([a-z].*)$", nm)
    if m:
        c=name2cas.get(m.group(2)) or name2cas.get(m.group(1))
        if c: return "CAS:"+c
    return "NM:"+nm

# 展开记录: (compkey, doc, sample, kind) -> value(已换算μg/L)
records={}   # (ck,doc,smp,kind)->value
d25_n={}     # D25: 每化合物内 '浓度' 行出现序号
kept_rows=0
drop_aroma=0
drop_sample=0
drop_conc=0

# OAV_MIXED 文献: '浓度'行内浓度/OAV分类(见OAV_MIXED注释)
from collections import defaultdict
_om=defaultdict(list)
for _idx,_r in src.iterrows():
    if _r["文献名"] not in OAV_MIXED or _r["数据类型"]!="浓度": continue
    _v=parse_num(_r["数值"])
    if math.isnan(_v): continue
    _om[(_r["文献名"],str(_r["化合物"]).strip(),str(_r["样品"]).strip())].append((_idx,_v))
OM_KIND={}
for _k,_items in _om.items():
    if len(_items)==1:
        OM_KIND[_items[0][0]]="oav" if float(_items[0][1]).is_integer() else "conc"
    else:
        _dec=[it for it in _items if not float(it[1]).is_integer()]
        _mx=max(it[1] for it in _dec) if _dec else None
        for _idx,_v in _items:
            if float(_v).is_integer(): OM_KIND[_idx]="oav"
            elif len(_dec)>1 and _v<_mx: OM_KIND[_idx]="oav"
            else: OM_KIND[_idx]="conc"

for _idx,r in src.iterrows():
    d=r["文献名"]
    if pd.isna(d) or d in EXCLUDE_DOC: continue
    smp=clean_sample(r["样品"])
    dt=r["数据类型"]
    v=parse_num(r["数值"])
    if dt=="阈值": continue   # 阈值单独处理
    # D25: 两列样品名在清洗时丢失(表头'浓度'), 论文样品为洋河天之蓝(浓香)+二锅头(清香)
    if d==D25:
        raw="" if pd.isna(r["样品"]) else str(r["样品"]).strip()
        if raw.startswith("浓度 (μg/L)"):
            continue          # 实为嗅觉阈值(阈值通道另取)
        if raw=="量比关系" or raw.startswith("OAV值"):
            continue          # 占比/二锅头OAV, 非本库数据
        if raw=="OAV":
            smp="天之蓝-2"    # 核验: OAV=天之蓝-2浓度/阈值(37.7=33933.56/900等)
        elif raw=="浓度":
            _k=(D25, compkey(r))
            d25_n[_k]=d25_n.get(_k,0)+1
            smp="天之蓝-1" if d25_n[_k]==1 else "天之蓝-2"
    if smp is None: continue
    # 样品名归并
    smap=SAMPLE_MAP.get(d)
    if smap and smp in smap:
        new=smap[smp]
        if new is None:
            drop_sample+=1; continue
        smp=new
    # 香型剔除
    arem=AROMA_REMOVE.get(d)
    if arem and smp in arem:
        drop_aroma+=1; continue
    if math.isnan(v): continue
    ck=compkey(r)
    kind="oav" if dt=="OAV" else "conc"
    if d in OAV_MIXED and dt=="浓度":
        kind=OM_KIND.get(_idx,"conc")   # D12/D24: '浓度'行内分流OAV/浓度
    if kind=="conc" and d in DROPCONC:
        drop_conc+=1; continue
    if kind=="conc":
        v=v*UNIT_FACTOR.get(d,1)        # OAV无量纲, 不乘单位因子
    key=(ck,d,smp,kind)
    # 同键多值取均值
    if key in records:
        old=records[key]
        records[key]=(old[0]+v, old[1]+1) if isinstance(old,tuple) else (old,1)
    else:
        records[key]=(v,1)

# 均值化
records={k:(t[0]/t[1] if isinstance(t,tuple) and t[1] else t) for k,t in
         ((k,(v if isinstance(v,tuple) else (v,1))) for k,v in records.items())}

# 阈值: (compkey)->value(μg/L)
thresholds={}
for _,r in src.iterrows():
    _thr_d12=False
    if r["数据类型"]!="阈值":
        # D25伪'浓度'行实为阈值(核验: OAV=浓度/该行值, 如37.7=33933.56/900)
        if r["文献名"]==D25 and pd.notna(r["样品"]) \
                and str(r["样品"]).strip().startswith("浓度 (μg/L)"):
            pass
        # D12样品名残留表头'浓度(mg·L-1)'的行实为原文表1'阈值/(mg·L⁻¹)'列(如己酸乙酯0.06)
        elif r["文献名"]==D12 and pd.notna(r["样品"]) \
                and str(r["样品"]).strip().startswith("浓度 （mg·L-1）"):
            _thr_d12=True
        else:
            continue
    v=parse_num(r["数值"])
    if math.isnan(v) or v<=0: continue
    ck=compkey(r)
    if _thr_d12: v=v*1000   # mg/L -> μg/L
    thresholds.setdefault(ck,v)   # 阈值视为μg/L; 清洗数据已有值优先

print("清洗后数据展开: 保留键数=%d, 因香型剔除=%d, 因样品归并丢弃=%d, 因浓度剔除=%d" % (len(records),drop_aroma,drop_sample,drop_conc))

# ============ 分表回溯补数据 ============
# 英文名 -> compkey 索引(用于无CAS分表匹配到既有化合物)
en2ck={}
def add_en(nm, ck):
    if nm: en2ck.setdefault(re.sub(r"\s+"," ",str(nm).lower().strip()), ck)
for _,r in src.iterrows():
    ck=compkey(r)
    if pd.notna(r["化合物"]) and not has_cjk(str(r["化合物"])):
        add_en(r["化合物"], ck)

# 分表阈值补全: 扫描data总库各分表的 Threshold/阈值 列, 按英文名匹配
def _nmkey(s):
    return re.sub(r"\s+"," ",str(s).lower().strip()) if pd.notna(s) else ""
thr_harvest=0
_xl=pd.ExcelFile(REF)
for _sheet in _xl.sheet_names:
    if _sheet=="all data": continue
    try: _sh=pd.read_excel(REF, sheet_name=_sheet)
    except Exception: continue
    _sh.columns=[str(c).strip() for c in _sh.columns]
    _tc=[c for c in _sh.columns if re.search(r"threshold|阈值", c, re.I)]
    _nc=[c for c in _sh.columns if re.search(r"compound|odorant|flavor|aroma|化合物", c, re.I)]
    if not _tc or not _nc: continue
    for _,rr in _sh.iterrows():
        nm=_nmkey(rr.get(_nc[0]))
        if not nm: continue
        ck=en2ck.get(nm)
        if ck is None and not has_cjk(nm): ck="NM:"+nm
        if ck is None: continue
        t=parse_num(rr.get(_tc[0]))
        if math.isnan(t) or t<=0: continue
        if ck not in thresholds:
            thresholds[ck]=t; thr_harvest+=1
print("分表阈值补全: 新增=%d" % thr_harvest)

recovered_counts={}
for d,sheet in RECOVER.items():
    kind,scols,ccol,cascol,fac=RECOVER_SPEC[d]
    sh=pd.read_excel(REF, sheet_name=sheet)
    sh.columns=[str(c).strip() for c in sh.columns]
    if ccol not in sh.columns:
        # 容错: 找一个像化合物名的列
        for cand in ["Compounds","Compound","Compound Name","Aroma compounds","flavor components"]:
            if cand in sh.columns: ccol=cand; break
    n=0
    for _,rr in sh.iterrows():
        if ccol not in sh.columns: break
        nm=rr[ccol]
        if pd.isna(nm): continue
        cnorm=re.sub(r"\s+"," ",str(nm).lower().strip())
        # CAS优先
        ckey=None
        if cascol and cascol in sh.columns:
            c=norm_cas(rr[cascol])
            if c: ckey="CAS:"+c
        if ckey is None:
            ckey=en2ck.get(cnorm) or ("NM:"+cnorm)
        for sc,snm in scols:
            if sc not in sh.columns: continue
            v=parse_num(rr[sc])
            if math.isnan(v): continue
            v=v*fac
            key=(ckey,d,snm,kind)
            records[key]=v
            n+=1
    recovered_counts[d]=n
print("分表回溯补入数值:", {DOC_IDX[k]:v for k,v in recovered_counts.items()})

# ============ 收集全部化合物主键 ============
all_ck=set(k[0] for k in records)

# 名称兜底: 从清洗数据按主键统计中/英文名(多数票)
def _natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]
ck_names={}
for _,r in src.iterrows():
    ck=compkey(r)
    nm=str(r["化合物"]).strip() if pd.notna(r["化合物"]) else ""
    if not nm: continue
    d=ck_names.setdefault(ck,{"en":[],"zh":[]})
    (d["zh"] if has_cjk(nm) else d["en"]).append(nm)
def pick_common(lst):
    return max(set(lst), key=lst.count) if lst else ""
en_fb={ck:pick_common(v["en"]) for ck,v in ck_names.items()}
zh_fb={ck:pick_common(v["zh"]) for ck,v in ck_names.items()}

# 参照: 从 data总库 all data 取 SMILES/英文/中文/阈值
ref=pd.read_excel(REF, sheet_name="all data")
ref.columns=[str(c).strip() for c in ref.columns]
smiles_map={}; en_map={}; zh_map={}; thr_ref={}
for _,rr in ref.iterrows():
    c=norm_cas(rr.get("CAS"))
    if not c: continue
    for col,mp in [("SMILES",smiles_map),("Odorants",en_map),("中文名称",zh_map)]:
        x=rr.get(col)
        if x is not None and not (isinstance(x,float) and math.isnan(x)):
            mp[c]=str(x).strip()
    t=parse_num(rr.get("Threshold"))
    if not math.isnan(t): thr_ref[c]=t

def sortkey(ck):
    if ck.startswith("CAS:"):
        c=ck[4:]
        parts=c.split("-")
        return (0, int(parts[0]) if parts[0].isdigit() else 999, c)
    return (1, 0, ck)
comp_keys=sorted(all_ck, key=sortkey)

# SMILES补全: PubChem PUG REST(按CAS, 带本地缓存, 断网静默跳过)
_pub=[ck for ck in comp_keys if ck.startswith("CAS:") and not smiles_map.get(ck[4:])]
if _pub:
    import json, urllib.request, time
    _cf=BASE+r"\smiles_cache.json"
    try: _cache=json.load(open(_cf,encoding="utf-8"))
    except Exception: _cache={}
    _new=0
    for ck in _pub:
        cas=ck[4:]
        if _cache.get(cas):
            smiles_map[cas]=_cache[cas]
            continue          # 已有非空结果才跳过, 空条目(上次失败)重试
        _s=""
        try:
            import ssl as _ssl
            _ctx=_ssl.create_default_context()
            _ctx.check_hostname=False; _ctx.verify_mode=_ssl.CERT_NONE  # 代理环境自签证书
            _url=f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}/property/SMILES/JSON"
            with urllib.request.urlopen(_url, timeout=10, context=_ctx) as _resp:
                _d=json.load(_resp)
            _s=_d["PropertyTable"]["Properties"][0].get("SMILES","") or ""
        except Exception:
            _s=""
        _cache[cas]=_s
        if _s: smiles_map[cas]=_s; _new+=1
        time.sleep(0.25)
    try: json.dump(_cache, open(_cf,"w",encoding="utf-8"))
    except Exception: pass
    print("PubChem补SMILES: 尝试=%d 新增=%d" % (len(_pub), _new))

# ============ 组装宽表 ============
# 决定列: 每文献(浓度/OAV)的样品集合(考虑香型剔除已含在records)
conc_samples={}; oav_samples={}
for (ck,d,smp,kind) in records:
    if kind=="conc": conc_samples.setdefault(d,set()).add(smp)
    else: oav_samples.setdefault(d,set()).add(smp)

base_cols=["Order ID","CAS","Odorants","中文名称","SMILES","Threshold（μg/L）"]
col_headers=list(base_cols)
col_plan=[]
for d in DOCS:
    if d in EXCLUDE_DOC: continue
    for smp in sorted(conc_samples.get(d,[]), key=_natkey):
        h=f"{DOC_IDX[d]}  {smp} (μg/L)"
        col_plan.append(("conc",d,smp,h)); col_headers.append(h)
for d in DOCS:
    if d in EXCLUDE_DOC: continue
    for smp in sorted(oav_samples.get(d,[]), key=_natkey):
        h=f"{DOC_IDX[d]}  {smp} OAV"
        col_plan.append(("oav",d,smp,h)); col_headers.append(h)

rows=[]
for i,ck in enumerate(comp_keys,1):
    cas=ck[4:] if ck.startswith("CAS:") else ""
    # 名称: 优先 data总库(按CAS), 否则清洗数据自身名称兜底
    en=en_map.get(cas,"") or en_fb.get(ck,"")
    zh=zh_map.get(cas,"") or zh_fb.get(ck,"")
    sm=smiles_map.get(cas,"")
    if not en and ck.startswith("NM:"):
        en=ck[3:].title()
    th=thresholds.get(ck, thr_ref.get(cas,""))
    row={"Order ID":i,"CAS":cas,"Odorants":en,"中文名称":zh,"SMILES":sm,"Threshold（μg/L）":th}
    for kind,d,smp,h in col_plan:
        v=records.get((ck,d,smp,kind))
        row[h]=round(v,4) if isinstance(v,(int,float)) and not math.isnan(v) else ""
    rows.append(row)
out_df=pd.DataFrame(rows,columns=col_headers)

# ============ 复核表 ============
# 1) 文献索引+单位
doc_rows=[]
for d in DOCS:
    nc=len(conc_samples.get(d,[])); no=len(oav_samples.get(d,[]))
    _proc=[]
    if d in EXCLUDE_DOC: _proc.append("整篇剔除:"+EXCLUDE_DOC[d])
    if d in DROPCONC: _proc.append("浓度列剔除(数据取错表):"+DROPCONC[d])
    if d in RECOVER: _proc.append("分表回溯")
    if d in OAV_MIXED: _proc.append("清洗'浓度'行内分流: 整数=OAV(原文表1的OAV块),小数=浓度(mg/L);同组多小数行取最大为浓度")
    if d==D25: _proc.append("样品名丢失列按论文样品回溯为天之蓝-1/-2(洋河天之蓝系,浓香);二锅头(清香)剔除")
    doc_rows.append({"文献编号":DOC_IDX[d],"文献名":d,"浓度样品列数":nc,"OAV样品列数":no,
        "换算因子(→μg/L)":UNIT_FACTOR.get(d,1),"单位依据":UNIT_BASIS.get(d,""),
        "处理":"; ".join(_proc)})
doc_df=pd.DataFrame(doc_rows)

# 2) 样品名清洗对照表
clean_rows=[]
for d,mapping in SAMPLE_MAP.items():
    for raw,new in mapping.items():
        clean_rows.append({"文献编号":DOC_IDX[d],"文献名":d,"原始样品名":raw,
            "归并为":new if new else "(丢弃)","说明":""})
# D25 样品名丢失列回溯
for raw,new,note in [
    ("浓度(第1列)","天之蓝-1","原表样品名丢失;论文样品=洋河天之蓝(浓香,新/老酒)+二锅头(清香,已剔除);两列列序待核"),
    ("浓度(第2列)","天之蓝-2","同上;本列浓度/阈值与OAV列精确对应(逐一核验)"),
    ("OAV","天之蓝-2 OAV","核验: OAV=本列浓度/阈值(37.7=33933.56/900等5例)"),
    ("浓度 (μg/L) [μg/l]","阈值(入Threshold列)","原误标为浓度样品;实为嗅觉阈值(μg/L)")]:
    clean_rows.append({"文献编号":DOC_IDX[D25],"文献名":D25,"原始样品名":raw,
        "归并为":new,"说明":note})
# 3) 香型剔除表
aroma_rows=[]
for d,mapping in AROMA_REMOVE.items():
    for smp,why in mapping.items():
        aroma_rows.append({"文献编号":DOC_IDX[d],"文献名":d,"样品":smp,"处理":"剔除","原因":why})
# D14: 文献表2将5种品牌均归为浓香型(含通常清香型品牌) -> 用户确认保留
for _s in ["牛栏山","红星二锅头"]:
    aroma_rows.append({"文献编号":DOC_IDX[D14],"文献名":D14,"样品":_s,"处理":"保留(已确认)",
                       "原因":"原文献表2归为'5种浓香型白酒';该品牌通常为清香型,经用户确认保留"})
# D23 编码样品: 经论文表2-1/2-2与附表5核对
for d in [D23]:
    for smp in sorted(oav_samples.get(d,[])|conc_samples.get(d,[])):
        _why=("浓香型(表2-2: n-g/n-c=浓香成品, n-d=单粮原酒, n-s=多粮原酒)" if smp.startswith("n-")
              else "浓香型(表列样品)")
        aroma_rows.append({"文献编号":DOC_IDX[d],"文献名":d,"样品":smp,"处理":"保留(已核对)","原因":_why})

clean_df=pd.DataFrame(clean_rows) if clean_rows else pd.DataFrame()
aroma_df=pd.DataFrame(aroma_rows) if aroma_rows else pd.DataFrame()

# ============ 写出 ============
with pd.ExcelWriter(OUT,engine="openpyxl") as w:
    out_df.to_excel(w,sheet_name="all data",index=False)
    doc_df.to_excel(w,sheet_name="文献索引与单位",index=False)
    if not clean_df.empty: clean_df.to_excel(w,sheet_name="样品名清洗对照",index=False)
    if not aroma_df.empty: aroma_df.to_excel(w,sheet_name="香型判定",index=False)

print("输出:",OUT)
print("化合物行=%d 总列=%d (浓度列=%d OAV列=%d)" % (
    out_df.shape[0],out_df.shape[1],
    sum(1 for p in col_plan if p[0]=="conc"),sum(1 for p in col_plan if p[0]=="oav")))
