# -*- coding: utf-8 -*-
import pandas as pd, numpy as np
f = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月\可用化合物原始数据.xlsx"
x = pd.ExcelFile(f)
print("sheets:", x.sheet_names)
a = pd.read_excel(f, sheet_name="all data")
o = pd.read_excel(f, sheet_name="OAV(周阈值)")
conc = [c for c in a.columns if c.endswith("(μg/L)")]
oavc = [c.replace("(μg/L)", "(OAV)") for c in conc]
print("列名可逆映射一致:", [c.replace("(OAV)", "(μg/L)") for c in o.columns] == list(a.columns),
      "| 浓度列%d OAV列%d" % (len(conc), len(oavc)))
nonc = [c for c in a.columns if not c.endswith("(μg/L)")]
same = all(a[c].astype(str).equals(o[c].astype(str)) for c in nonc)
print("非浓度列逐格一致:", same)
thr = a["阈值(ppb,周表)"]
bad = 0; chk = 0; blank_match = True
for c, oc in zip(conc, oavc):
    v = pd.to_numeric(a[c], errors="coerce")
    e = pd.to_numeric(o[oc], errors="coerce")
    m = v.notna()
    chk += int(m.sum())
    if not np.allclose((v[m] / thr[m]).round(3), e[m], atol=1e-9):
        bad += 1; print("BAD", c)
    if not v.isna().equals(e.isna()):
        blank_match = False
print("OAV=浓度/阈值 核对: 单元格%d 有问题列%d 空位一致:%s" % (chk, bad, blank_match))
print("\n抽查 (all data):")
print(a[["Order ID", "中文名称", "阈值(ppb,周表)", "1  GJ-1573 (μg/L)"]].head(5).to_string())
print("\n抽查 (OAV(周阈值)):")
print(o[["Order ID", "中文名称", "阈值(ppb,周表)", "1  GJ-1573 (OAV)"]].head(5).to_string())
n1 = pd.read_excel(f, sheet_name="说明")
print("\n说明表:")
print(n1.to_string())
