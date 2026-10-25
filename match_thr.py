# -*- coding: utf-8 -*-
"""步骤1: '周'阈值 与 浓香型数据库化合物名 匹配试验 -> match_thr.txt
通过: 1)精确 2)规范化(去符号) 3)别名表(后续人工补)
"""
import re
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
THR = r"C:\Users\24252\Desktop\PPT\课题\26年\26.10\英文\阈值.xlsx"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

thr = pd.read_excel(THR, sheet_name="周")
thr.columns = ["name", "thr"]
thr = thr.dropna(subset=["name"])
w("周阈值条数=%d 单位核对: 乙酸乙酯=%s(应32552ppb=32.55mg/L) 己酸乙酯=%s(应55.3)" % (
    len(thr),
    thr.loc[thr["name"]=="乙酸乙酯","thr"].tolist(),
    thr.loc[thr["name"]=="己酸乙酯","thr"].tolist()))

def norm(s):
    s = str(s).strip().lower()
    s = re.sub(r"[\s\-—–·()（）\[\]、,，.。/]", "", s)
    return s

tmap_exact = {str(r["name"]).strip(): float(r["thr"]) for _, r in thr.iterrows() if pd.notna(r["thr"])}
tmap_norm = {}
for _, r in thr.iterrows():
    if pd.notna(r["thr"]):
        tmap_norm.setdefault(norm(r["name"]), float(r["thr"]))

df = pd.read_excel(BASE + r"\浓香型数据库.xlsx", sheet_name="all data")
w("数据库化合物=%d" % len(df))

m_exact, m_norm, miss = [], [], []
for _, r in df.iterrows():
    zh = str(r["中文名称"]).strip() if pd.notna(r["中文名称"]) and str(r["中文名称"]).strip() else ""
    en = str(r["Odorants"]).strip() if pd.notna(r["Odorants"]) else ""
    if not zh:
        miss.append((en, "", "无中文名"))
        continue
    if zh in tmap_exact:
        m_exact.append((zh, zh)); continue
    if norm(zh) in tmap_norm:
        m_norm.append((zh, [k for k in tmap_exact if norm(k)==norm(zh)][0])); continue
    # 包含匹配候选
    cands = [k for k in tmap_exact if norm(k) and (norm(k) in norm(zh) or norm(zh) in norm(k))]
    miss.append((en, zh, "候选: %s" % "|".join(cands[:4])))

w("精确匹配=%d 规范化匹配=%d 未匹配=%d" % (len(m_exact), len(m_norm), len(miss)))
w("")
w("== 规范化命中的(名称写法不同) ==")
for a, b in m_norm: w("  db:%s <- 周:%s" % (a, b))
w("")
w("== 未匹配(共%d, 含候选) ==" % len(miss))
for en, zh, c in miss:
    w("  [%s] %s  %s" % (en[:40], zh, c))

# 周表中未被用到的阈值
used = set(a for a, _ in m_exact) | set(a for a, _ in m_norm)
unused = [k for k in tmap_exact if k not in used and norm(k) not in
          set(norm(x[1]) for x in miss if x[1])]
w("")
w("== 周表未被匹配的阈值条目(%d) ==" % len(unused))
for k in unused: w("  %s (%s)" % (k, tmap_exact[k]))

with open(BASE + r"\match_thr.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE")
