# -*- coding: utf-8 -*-
"""probe_fix3: 1) D3分表列名 2) D12/D24整数值行(疑OAV混入浓度) -> probe_fix3.txt"""
import re, math
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

# 1) D3 分表列名+样例行
sh = pd.read_excel(BASE + r"\data总库.xlsx", sheet_name="2  Decoding the Molecular Mecha")
sh.columns = [str(c).strip() for c in sh.columns]
w("== D3 分表列 ==")
for c in sh.columns: w("  %r" % c)
w("  行数=%d 前3行化合物=%s" % (len(sh), list(sh.iloc[:3,0])))
# 乙酸乙酯/己酸乙酯值
m = sh[sh.iloc[:,0].astype(str).str.contains("thyl acetate|thyl hexanoate|cetate|xanoate", na=False, regex=True)]
for _, r in m.head(6).iterrows():
    w("  %s -> %s" % (r.iloc[0], {c: r[c] for c in sh.columns[1:] if pd.notna(r[c])}))

# 2) D12/D24 纯整数值行
src = pd.read_excel(BASE + r"\清洗后数据.xlsx", sheet_name="清洗后数据")
def rawstr(x):
    if isinstance(x,(int,float)):
        return str(int(x)) if float(x)==int(x) else str(x)
    return str(x).strip()
LIT = {"D12":"基于GC×GC-MS分析不同等级浓香型白酒的关键风味化合物",
       "D24":"洋河绵柔型白酒关键风味成分",
       "D11":"四川不同产区浓香型白酒风味物质差异化分析"}
for k, lit in LIT.items():
    g = src[src["文献名"]==lit]
    w("")
    w("== %s (总行%d) 纯整数值行 ==" % (k, len(g)))
    ints = g[g["数值"].apply(lambda x: bool(re.fullmatch(r"\d+", rawstr(x))))]
    w("  整数行数=%d / 非整数=%d" % (len(ints), len(g)-len(ints)))
    w("  整数行样品分布: %s" % ints["样品"].astype(str).value_counts().head(15).to_dict())
    # 每化合物出现2+行的样例(同一样品多值=浓度+OAV混)
    dup = g.groupby([g["化合物"].astype(str).str.strip(), g["样品"].astype(str).str.strip()]).size()
    dup = dup[dup>=2]
    w("  同(化合物,样品)>=2行的组合数=%d" % len(dup))
    shown=0
    for (cp,sp),n in dup.items():
        vals = g[(g["化合物"].astype(str).str.strip()==cp)&(g["样品"].astype(str).str.strip()==sp)]["数值"].tolist()
        w("    %s | %s | n=%d vals=%s" % (cp,sp,n,[rawstr(v) for v in vals]))
        shown+=1
        if shown>=12: break
    # 整数行样例
    w("  整数行样例(前12):")
    for _, r in ints.head(12).iterrows():
        w("    %s | 样品=%s | %s" % (str(r["化合物"]).strip(), r["样品"], rawstr(r["数值"])))

with open(BASE + r"\probe_fix3.txt","w",encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE")
