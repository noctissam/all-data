# -*- coding: utf-8 -*-
"""验证 浓香型数据库.xlsx v2"""
import pandas as pd
BASE = r"C:\Users\24252\Desktop\PPT\课题\26年\26年3月"
OUT = BASE + r"\浓香型数据库.xlsx"
CHK = BASE + r"\check_v2.txt"

df = pd.read_excel(OUT, sheet_name="all data")
idx = pd.read_excel(OUT, sheet_name="文献索引与单位")
xl = pd.ExcelFile(OUT)
data_cols=[c for c in df.columns if c not in ["Order ID","CAS","Odorants","中文名称","SMILES","Threshold（μg/L）"]]

with open(CHK,"w",encoding="utf-8") as f:
    f.write("工作表: %s\n" % xl.sheet_names)
    f.write("all data 形状: %s\n\n" % str(df.shape))

    f.write("### 文献索引与单位 ###\n")
    f.write(idx.to_string(index=False)+"\n\n")

    # 单位换算验证: 找 mg/L篇(×1000) 的代表化合物看数量级
    f.write("### 单位换算抽查(浓度列应为μg/L量级) ###\n")
    for c in ["12  B (μg/L)","24  41% TZL (μg/L)","11  CJ (μg/L)","20  GRD-JC (μg/L)","23  浓香型酒 (μg/L)","3  LZLJ-M7 (μg/L)","3  LZLJ-T7 (μg/L)"]:
        if c in df.columns:
            s=pd.to_numeric(df[c],errors="coerce").dropna()
            f.write("  %s: n=%d 中位=%.4g max=%.4g\n" % (c,len(s),s.median() if len(s) else 0,s.max() if len(s) else 0))
    f.write("\n")

    # 香型剔除验证
    f.write("### 香型剔除验证 ###\n")
    bad=[c for c in data_cols if any(x in c for x in ["茅台","习酒","酱香型酒","ZSW"])
         or ("二锅头" in c and not c.startswith("14 "))]   # 二锅头仅剔除#25(清香); #14红星二锅头为品牌名(存疑保留)
    f.write("  残留应剔除列: %s\n\n" % (bad if bad else "无(已剔除)"))
    suspect=[c for c in data_cols if any(x in c for x in ["牛栏山","红星"])]
    f.write("### D14保留(已确认)列 ###\n")
    f.write("  %s (原文献表2归为浓香型,经用户确认保留)\n\n" % (suspect if suspect else "无"))

    # #21 酒等级归并验证 (浓度列已整体剔除: 清洗到的是量比表/FD表)
    f.write("### #21 等级列(浓度已剔除,应仅剩OAV列) ###\n")
    g21=[c for c in data_cols if c.startswith("21 ")]
    for c in g21: f.write("  %s (n=%d)\n" % (c, df[c].notna().sum()))
    f.write("\n")

    # D12/D24 浓度/OAV分流验证: 抽查己酸乙酯
    f.write("### D12/D24 浓度与OAV分流抽查(己酸乙酯) ###\n")
    rr=df[df["CAS"].astype(str)=="123-66-0"]
    if len(rr):
        rr=rr.iloc[0]
        for c in data_cols:
            if c.startswith(("12 ","24 ")) and pd.notna(rr[c]) and rr[c]!="":
                f.write("  %s=%s\n" % (c, rr[c]))
    f.write("\n")

    # 分表回溯验证: #2 Y列, #5 S列, #9 应有数据
    f.write("### 分表回溯验证 ###\n")
    for pref in ["2 ","3 ","5 ","9 ","4 "]:
        cols=[c for c in data_cols if c.startswith(pref)]
        f.write("  文献%s: %d列 -> %s\n" % (pref.strip(),len(cols),cols[:8]))
    f.write("\n")

    # 己酸乙酯完整行
    f.write("### 抽查 己酸乙酯(CAS 123-66-0) ###\n")
    rr=df[df["CAS"].astype(str)=="123-66-0"]
    if len(rr):
        rr=rr.iloc[0]
        f.write("  中文=%s SMILES=%s Thr=%s\n" % (rr["中文名称"],rr["SMILES"],rr["Threshold（μg/L）"]))
        nz={c:rr[c] for c in data_cols if pd.notna(rr[c]) and rr[c]!=""}
        f.write("  非空列数=%d\n" % len(nz))
        for c,v in list(nz.items())[:20]: f.write("    %s=%s\n"%(c,v))
    f.write("\n")

    # 填充率
    f.write("### 填充率 ###\n")
    fill=df.notna().sum(); total=len(df)
    for c in ["CAS","Odorants","中文名称","SMILES","Threshold（μg/L）"]:
        f.write("  %s: %d/%d\n" % (c,fill.get(c,0),total))
    filled=[c for c in data_cols if df[c].notna().sum()>0]
    f.write("  有数据样品列: %d/%d\n" % (len(filled),len(data_cols)))
print("DONE -> check_v2.txt")
