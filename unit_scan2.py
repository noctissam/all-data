# -*- coding: utf-8 -*-
"""unit_scan2: D11/D12/D24 (×1000家族) PDF表头单位硬核 + PubChem name端点测试 -> unit_scan2.txt"""
import re, os, json, ssl, traceback, urllib.request
import warnings
warnings.filterwarnings("ignore")
import pymupdf

BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
L = []
def w(*a): L.append(" ".join(str(x) for x in a))

PDFS = {
 "D11": r"寒假中文文献\四川不同产区浓香型白酒风味物质差异化分析_关宝义.pdf",
 "D12": r"寒假中文文献\基于GC×GC-MS分析不同等级浓香型白酒的关键风味化合物_陈乙源.pdf",
 "D24": r"寒假中文文献\洋河绵柔型白酒关键风味成分_范文来.pdf",
}
unit_kw = re.compile(
    r"(?:μ|µ|u)g\s*(?:/|·|\s)\s*(?:100\s*)?m[lL]|mg\s*(?:/|·|\s)\s*(?:100\s*)?m[lL]"
    r"|g\s*(?:/|·|\s)\s*(?:100\s*)?m[lL]|mg\s*/\s*L|(?:μ|µ)g\s*/\s*L|g\s*/\s*L"
    r"|mg\s*·\s*L|(?:μ|µ)g\s*·\s*L|mg/kg|(?:μ|µ)g/kg|mg\s*·\s*(?:100\s*)?m[lL]", re.I)

for k, rel in PDFS.items():
    p = os.path.join(BASE, rel)
    doc = pymupdf.open(p)
    txt = "\n".join(pg.get_text() for pg in doc)
    doc.close()
    w("=" * 12 + " %s (%d字) " % (k, len(txt)) + "=" * 12)
    seen = set(); cnt = 0
    for m in unit_kw.finditer(txt):
        s = re.sub(r"\s+", " ", txt[max(0, m.start()-70):m.end()+30]).strip()
        if s in seen: continue
        seen.add(s); cnt += 1
        w("  · " + s[:140])
        if cnt >= 15: break
    # 表题行
    for m in re.finditer(r"表\s*\d[\d\-\.\s]{0,4}[^\n]{0,90}", txt):
        s = re.sub(r"\s+", " ", m.group(0)).strip()
        if re.search(r"含量|浓度|成分|风味|挥发|定性定量", s):
            w("  [表题] " + s[:120])
    # 关键化合物数值上下文: 己酸乙酯
    cnt = 0
    for m in re.finditer(r"己酸乙酯", txt):
        s = re.sub(r"\s+", "", txt[max(0, m.start()-40):m.end()+80])
        if re.search(r"\d{3,}", s):
            w("  [己酸乙酯] " + s[:140]); cnt += 1
        if cnt >= 5: break
    w("")

# ---- PubChem name 端点测试 ----
w("=" * 12 + " PubChem name端点 " + "=" * 12)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
for path in ["compound/name/123-66-0", "compound/name/50-21-5"]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/{path}/property/SMILES/JSON"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            d = json.load(r)
        w("  OK %s -> %s" % (path, d["PropertyTable"]["Properties"][0].get("SMILES")))
    except Exception as e:
        w("  FAIL %s -> %s" % (path, e))

with open(BASE + r"\unit_scan2.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("DONE")
