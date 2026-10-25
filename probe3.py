# -*- coding: utf-8 -*-
"""probe3: D25 PDF样品表头 + D21浓度表提取 -> probe3.txt"""
import re, os, warnings
warnings.filterwarnings("ignore")
import pymupdf

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
L=[]
def w(*a): L.append(" ".join(str(x) for x in a))

# ---- D25 ----
p25=os.path.join(BASE, r"寒假中文文献\浓香型洋河天之蓝和清香型二锅头大曲白酒特征香气成分研究_张恩.pdf")
d=pymupdf.open(p25)
t="\n".join(pg.get_text() for pg in d)
w("== D25 文本字数",len(t))
for kw in ["天之蓝","二锅头","大曲","量比","OAV","表2","表3","表4"]:
    idxs=[m.start() for m in re.finditer(re.escape(kw),t)]
    w(f"  {kw}: {len(idxs)}次")
for kw in ["天之蓝","二锅头"]:
    for i in [m.start() for m in re.finditer(re.escape(kw),t)][:4]:
        w(f"  [{kw}] ctx: "+re.sub(r"\s+"," ",t[max(0,i-150):i+150]))
# 表题
for m in re.finditer(r"表\s*\d[\d\-\.]*\s*[^\n]{0,90}",t):
    w("  表题: "+re.sub(r"\s+"," ",m.group(0))[:110])
# find_tables 裸dump前3页
for pno in range(min(6,len(d))):
    try: tabs=d[pno].find_tables()
    except Exception as e: w(f"  p{pno} err {e}"); continue
    for ti,tab in enumerate(tabs.tables):
        try: data=tab.extract()
        except Exception: continue
        if not data: continue
        w(f"  p{pno} t{ti} rows={len(data)} head={" | ".join(str(x)[:18] if x else "" for x in data[0])}")
d.close()

# ---- D21 ----
p21=os.path.join(BASE, r"寒假中文文献\浓香型白酒基酒挥发性成分分析及等级识别研究_周轩.pdf")
d=pymupdf.open(p21)
w("\n== D21 找表3.3/3.4页")
for pno,pg in enumerate(d):
    txt=pg.get_text()
    if re.search(r"表\s*3\.[34]",txt) or ("mg/100mL" in txt and "己酸乙酯" in txt):
        w(f"  p{pno}: "+[s for s in re.findall(r"表\s*3\.\d[^\n]{0,80}",txt)][:4].__repr__()[:200])
        try: tabs=pg.find_tables()
        except Exception as e: w(f"    err {e}"); continue
        for ti,tab in enumerate(tabs.tables):
            try: data=tab.extract()
            except Exception: continue
            if not data: continue
            w(f"    t{ti} rows={len(data)}")
            for row in data[:4]:
                w("      "+" | ".join(str(x)[:16] if x else "" for x in row))
        if pno>60: break
d.close()
with open(os.path.join(BASE,"probe3.txt"),"w",encoding="utf-8") as f: f.write("\n".join(L))
print("DONE")
