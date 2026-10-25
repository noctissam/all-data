# -*- coding: utf-8 -*-
"""调试: PubChem请求真实错误 + D3结构 + D12/D24极值 -> debug_net.txt"""
import os, re, json, math, traceback, ssl, urllib.request
import pandas as pd

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

# ---- 1) 代理环境 ----
w("== 1) 代理/环境变量 ==")
for k in ["HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","NO_PROXY"]:
    w("  %s = %r" % (k, os.environ.get(k)))
# 系统代理(注册表)
try:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
        v,_ = winreg.QueryValueEx(key, "ProxyEnable")
        s,_ = winreg.QueryValueEx(key, "ProxyServer")
        w("  IE ProxyEnable=%s ProxyServer=%s" % (v, s))
except Exception as e:
    w("  注册表读取失败: %s" % e)

# ---- 2) 单条PubChem请求(跳过证书校验) ----
w("== 2) PubChem 单条请求(verify off) ==")
url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cas/123-66-0/property/SMILES/JSON"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try:
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        d = json.load(r)
    w("  OK: %s" % d["PropertyTable"]["Properties"][0].get("SMILES"))
except Exception:
    w("  FAIL traceback:")
    for line in traceback.format_exc().strip().splitlines():
        w("    "+line)

# ---- 2b) 试 http(非TLS) 与其它端点 ----
w("== 2b) 备选端点 ==")
for u in ["http://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cas/123-66-0/property/SMILES/JSON",
          "https://rest.pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cas/123-66-0/property/SMILES/JSON"]:
    try:
        req = urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            d = json.load(r)
        w("  OK %s -> %s" % (u, d["PropertyTable"]["Properties"][0].get("SMILES")))
        break
    except Exception as e:
        w("  FAIL %s -> %s" % (u, e))

# ---- 3) D3 结构 ----
w("== 3) D3 清洗样品名/类型 ==")
src = pd.read_excel(BASE + r"\清洗后数据.xlsx", sheet_name="清洗后数据")
D3 = "Decoding the Molecular Mechanism of Cellar Aroma Loss"
d3 = src[src["文献名"] == D3]
w("  类型: %s" % d3["数据类型"].value_counts().to_dict())
w("  样品: %s" % d3["样品"].astype(str).value_counts().head(20).to_dict())
# 分表乙酸乙酯/己酸乙酯浓度量级
sh = pd.read_excel(BASE + r"\data总库.xlsx", sheet_name="2  Decoding the Molecular Mecha")
sh.columns = [str(c).strip() for c in sh.columns]
w("  分表列: %s" % list(sh.columns))
m = sh[sh["Compounds"].astype(str).str.contains("exanoate|cetate", na=False, regex=True)]
for _, r2 in m.head(8).iterrows():
    w("    %s | %s" % (r2["Compounds"], [r2[c] for c in sh.columns[2:]]))

# ---- 4) D12/D24 极值行 ----
w("== 4) D12/D24 极大值行 ==")
def parse_num(x):
    if x is None or (isinstance(x, float) and math.isnan(x)): return math.nan
    if isinstance(x, (int, float)): return float(x)
    s = str(x).strip().replace(",", "")
    m2 = re.match(r"^([<>]?)\s*([-+]?\d[\d,]*\.?\d*)", s)
    if m2:
        try: return float(m2.group(2).replace(",", ""))
        except ValueError: return math.nan
    try: return float(s)
    except ValueError: return math.nan
for lit, samp in [("基于GC×GC-MS分析不同等级浓香型白酒的关键风味化合物","A"),
                  ("洋河绵柔型白酒关键风味成分","41% TZL")]:
    g = src[(src["文献名"] == lit) & (src["数据类型"] == "浓度") &
            (src["样品"].astype(str) == samp)].copy()
    g["vn"] = g["数值"].apply(parse_num)
    g = g.dropna(subset=["vn"]).sort_values("vn", ascending=False)
    w("  [%s] 样品=%s 最大3行:" % (lit[:12], samp))
    for _, r2 in g.head(3).iterrows():
        w("    化合物=%s 数值=%s CAS=%s" % (r2["化合物"], r2["数值"], r2["CAS号"]))

with open(BASE + r"\debug_net.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE")
