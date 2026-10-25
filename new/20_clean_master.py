# -*- coding: utf-8 -*-
"""
20_clean_master.py
==================
Step 2 of the cleaning pipeline: clean the master library `data总库.xlsx`.

What it does
------------
1.  Reads the master matrix `data总库.xlsx :: 'all data'` (65 compounds x 163 columns)
    plus its 12 literature sheet tabs (already flattened by 10_extract_sources.py).
2.  Repairs the CAS column:
      * dash normalisation (en/em dashes, stray spaces)
      * Excel date coercion ('3658-08-08 00:00:00', '216/3/9')
      * deleted leading/trailing zeros ('18-64-5' -> '108-64-5')
      * cross-repair from the sibling workbook `data.xlsx` (joined on SMILES)
      * CAS check-digit validation on every result
3.  Canonicalises compound names (English + Chinese), repairs the known typos,
    flags duplicate rows and assigns a chemical class.
4.  Builds a column registry (study / sample / unit) and harmonises every
    concentration to μg/L.
5.  Harvests odour thresholds from the 12 literature tabs to fill the master's
    empty `Threshold` column, then computes OAV = C / threshold.
6.  Writes a full data-quality report and an auditable issues log.

Source workbooks are opened read-only; nothing outside ./output is touched.
"""
from __future__ import annotations

import io
import os
import re
import sys

import numpy as np
import pandas as pd
import openpyxl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cleanlib as cl  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "output")
os.makedirs(OUT, exist_ok=True)

MASTER = os.path.join(SRC, "data总库.xlsx")
SIBLING = os.path.join(SRC, "data.xlsx")

ISSUES: list[dict] = []


def issue(kind, severity, scope, detail, action=""):
    ISSUES.append(
        {"issue_type": kind, "severity": severity, "scope": scope,
         "detail": detail, "action_taken": action}
    )


# ===========================================================================
# 1. read the master matrix
# ===========================================================================
def read_all_data(path, sheet="all data"):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    hdr = rows[0]
    while hdr and hdr[-1] is None:
        hdr.pop()
    width = len(hdr)
    body = []
    for r in rows[1:]:
        r = list(r[:width]) + [None] * max(0, width - len(r))
        if any(cl.s(c) for c in r):
            body.append(r)
    return hdr, body


print("reading master library ...")
m_hdr, m_body = read_all_data(MASTER)
print(f"  master  : {len(m_body)} compound rows x {len(m_hdr)} columns")
s_hdr, s_body = read_all_data(SIBLING)
print(f"  sibling : {len(s_body)} rows x {len(s_hdr)} columns")

META_COLS = 7
DATA_HEADERS = m_hdr[META_COLS:]

# ===========================================================================
# 2. compound registry + CAS repair
# ===========================================================================
# -- 2a. sibling reference keyed on SMILES and on normalised English name
sib_by_smiles, sib_by_name = {}, {}
for r in s_body:
    cas = cl.s(r[1])
    en = cl.s(r[2])
    smi = cl.s(r[4])
    if cl.cas_ok(cas):
        if smi:
            sib_by_smiles.setdefault(smi, cas)
        if en:
            sib_by_name.setdefault(cl.norm_key(en), cas)

# -- 2b. curated name repairs for the master library
NAME_REPAIR = {
    "hexanole acid": ("Hexanoic acid", "己酸"),
    "pentanole acid": ("Pentanoic acid", "戊酸"),
    "isovalenic acid": ("Isovaleric acid", "异戊酸"),
    "gamma-nonanolactone": ("gamma-Nonanolactone", "γ-壬内酯"),
    "ethyl 4-methyl valerate": ("Ethyl 4-methylvalerate", "4-甲基戊酸乙酯"),
    "3-methylbutyl hexanoate/isoamyl hexanoate": ("Isoamyl hexanoate", "己酸异戊酯"),
    "2-methylpropionic acid/isobutyric acid": ("2-Methylpropionic acid", "异丁酸"),
    "4-methylvaleric acid": ("4-Methylvaleric acid", "4-甲基戊酸"),
    "(e)-2-octenal": ("(E)-2-Octenal", "(E)-2-辛烯醛"),
    "2-(ethoxymethyl)furan": ("2-(Ethoxymethyl)furan", "2-(乙氧基甲基)呋喃"),
    "trimethyl-pyrazine": ("Trimethylpyrazine", "三甲基吡嗪"),
    "ethyl 3-phenylpropionate": ("Ethyl 3-phenylpropionate", "3-苯基丙酸乙酯"),
    "3-phenyl propionic acid": ("3-Phenylpropionic acid", "3-苯基丙酸"),
}
ZH_REPAIR = {"异己酸（4-甲基戊酸）": "4-甲基戊酸", "己酸异戊脂（3-甲基丁基己酸酯）": "己酸异戊酯"}

compound_rows = []
cas_issues = 0
for i, r in enumerate(m_body):
    order_id = cl.s(r[0])
    cas_raw = cl.s(r[1])
    en_raw = cl.s(r[2])
    zh_raw = cl.s(r[3])
    smiles = cl.s(r[4])

    # ---- canonical name
    key = cl.norm_key(en_raw)
    if key in NAME_REPAIR:
        en_can, zh_can = NAME_REPAIR[key]
        issue("compound_name", "medium", f"row {i + 2}",
              f"mis-spelled synonym {en_raw!r}", f"-> {en_can!r}")
    else:
        en_can = en_raw.strip()
        zh_can = ZH_REPAIR.get(zh_raw, zh_raw)
    # strip a trailing synonym after '/'
    if "/" in en_can:
        parts = [p.strip() for p in en_can.split("/") if p.strip()]
        # keep the more standard (ester) name if one contains a known class word
        en_can = max(parts, key=len) if len(parts) > 1 else parts[0]
        issue("compound_name", "low", f"row {i + 2}",
              f"synonym list {en_raw!r}", f"-> {en_can!r}")

    # ---- CAS repair
    cas_fixed, cas_stat, cas_src = "", "missing", ""
    cand = cl.norm_dash(cas_raw)
    # strip an Excel datetime artefact
    dt = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:\s|$)", cand)
    if dt:
        cand = cand[:10]
    if cl.cas_ok(cand):
        cas_fixed, cas_stat, cas_src = cl.cas_format(cand), "ok", "as-is"
    else:
        sib = sib_by_smiles.get(smiles) or sib_by_name.get(key)
        if sib and cl.cas_ok(sib):
            cas_fixed, cas_stat, cas_src = cl.cas_format(sib), "repaired_sibling", "data.xlsx"
        else:
            # Excel date coercion:  '216/3/9' -> 2016-03-09 -> try digit re-joins
            alt = re.sub(r"\D", "", cand)
            cands = cl.cas_candidates(cand)
            if cands:
                cas_fixed, cas_stat, cas_src = cands[0], "repaired_checksum", "zero-reinsertion"
            elif len(alt) >= 5:
                cas_fixed, cas_stat, cas_src = cl.cas_format(alt), "unverified", "digits-only"
    if cas_stat != "ok":
        cas_issues += 1
        issue("cas", "high" if cas_stat == "unverified" else "medium",
              f"{en_can} (row {i + 2})",
              f"CAS {cas_raw!r} invalid/mangled",
              f"{cas_fixed!r} via {cas_src} [{cas_stat}]")

    compound_rows.append(
        dict(row_no=i + 2, order_id=order_id, cas_raw=cas_raw, cas=cas_fixed,
             cas_status=cas_stat, cas_source=cas_src,
             name_en_raw=en_raw, name_en=en_can, name_zh=zh_can, smiles=smiles,
             chem_class=cl.chem_class(en_can, smiles), norm_key=key)
    )

comp = pd.DataFrame(compound_rows)

# ---- duplicates
dups = comp[comp.duplicated("norm_key", keep=False)]
if len(dups):
    for k, g in dups.groupby("norm_key"):
        issue("duplicate_compound", "high", g["name_en"].iloc[0],
              f"{len(g)} rows share the identity key {k!r}: "
              f"order IDs {list(g['order_id'])}", "merged into one compound")
dup_map = {}
for k, g in comp.groupby("norm_key"):
    keep = g.index[0]
    for ix in g.index:
        dup_map[ix] = keep
comp["compound_uid"] = [f"C{dup_map[i]:03d}" for i in comp.index]

# ---- resolve the merged compound (prefer the row with an odour-relevant name)
comp_master = (
    comp.sort_values(["compound_uid", "row_no"])
    .groupby("compound_uid", as_index=False)
    .agg(
        order_ids=("order_id", lambda x: "/".join(map(str, x))),
        cas=("cas", "first"), cas_raw=("cas_raw", "first"),
        cas_status=("cas_status", "first"), cas_source=("cas_source", "first"),
        name_en=("name_en", "first"), name_zh=("name_zh", "first"),
        smiles=("smiles", "first"), chem_class=("chem_class", "first"),
        norm_key=("norm_key", "first"), n_rows=("row_no", "size"),
        row_no=("row_no", "first"),
    )
)
print(f"  compounds: {len(comp)} rows -> {len(comp_master)} unique compounds")
comp.to_csv(os.path.join(OUT, "compound_registry.csv"), index=False, encoding="utf-8-sig")
comp_master.to_csv(os.path.join(OUT, "compound_master.csv"), index=False, encoding="utf-8-sig")

# ===========================================================================
# 3. threshold harvesting from the 12 literature tabs
# ===========================================================================
sheets = pd.read_csv(os.path.join(OUT, "sheets_long.csv"))
sheets["compound_key"] = sheets["compound_raw"].map(cl.norm_key)

UNIT_RE_ANY = re.compile(r"[μu]g\s*/?\s*[Ll]|mg\s*/?\s*[Ll]|g\s*/?\s*[Ll]|mg\s*/\s*100\s*m[lL]", re.I)


def unit_of(text: str) -> str:
    m = UNIT_RE_ANY.search(cl.s(text))
    if not m:
        return ""
    return cl.norm_unit(m.group())


# block-level modal unit (used when the column header carries none)
blk_unit = (
    sheets.assign(u=sheets["column_header"].map(unit_of))
    .query("u != ''")
    .groupby(["sheet_tab", "block_no"])["u"]
    .agg(lambda x: x.value_counts().idxmax())
    .to_dict()
)

thr = sheets[sheets["role"] == "threshold"].copy()
thr["unit"] = thr["column_header"].map(unit_of)
thr["unit"] = [
    u if u else blk_unit.get((t, b), "")
    for u, t, b in zip(thr["unit"], thr["sheet_tab"], thr["block_no"])
]
thr["thr_ugL"] = [cl.to_ug_per_l(v, u)[0] for v, u in zip(thr["value_mean"], thr["unit"])]

# alias table: literature short names -> master identity keys
ALIAS = {cl.norm_key(k): cl.norm_key(v) for k, v in {
    "hexanole acid": "hexanoic acid", "pentanole acid": "pentanoic acid",
    "isovalenic acid": "isovaleric acid", "ethyl pentanoate": "ethyl valerate",
    "ethyl butanoate": "ethyl butyrate", "ethyl octanoate": "ethyl caprylate",
    "ethyl heptanoate": "ethyl heptanoate", "ethyl 4-methylpentanoate": "ethyl 4-methylvalerate",
    "ethyl 3-methylbutanoate": "ethyl isovalerate", "ethyl 2-methylpropanoate": "ethyl isobutyrate",
    "3-methylbutyl hexanoate": "isoamyl hexanoate", "isoamyl hexanoate": "isoamyl hexanoate",
    "isopentyl hexanoate": "isoamyl hexanoate", "3-methylbutyl acetate": "isoamyl acetate",
    "isopentyl acetate": "isoamyl acetate", "2-methylpropanol": "isobutanol",
    "2-methyl-1-propanol": "isobutanol", "3-methylbutanol": "3-methyl-1-butanol",
    "isoamyl alcohol": "3-methyl-1-butanol", "phenylethyl alcohol": "2-phenylethanol",
    "2-phenylethanol": "2-phenylethanol", "dimethyl trisulphide": "dimethyl trisulfide",
    "dimethyl disulfide": "dimethyl disulfide", "2-methylpropionic acid": "2-methylpropionic acid",
    "isobutyric acid": "2-methylpropionic acid", "valeric acid": "valeric acid",
    "pentanoic acid": "pentanoic acid", "4-methylpentanoic acid": "4-methylvaleric acid",
    "2-methoxy-4-methylphenol": "2-methoxy-4-methylphenol", "4-ethylguaiacol": "4-ethyl-2-methoxyphenol",
    "4-ethyl-2-methoxyphenol": "4-ethyl-2-methoxyphenol", "guaiacol": "guaiacol",
    "gamma-nonanolactone": "gamma-nonanolactone", "gamma-decalactone": "gamma-decalactone",
    "acetoin": "acetoin", "3-hydroxy-2-butanone": "acetoin", "2-heptanone": "2-heptanone",
    "furfural": "furfural", "furfuryl alcohol": "furfuryl alcohol",
    "phenylacetaldehyde": "phenylacetaldehyde", "benzeneacetaldehyde": "phenylacetaldehyde",
    "trimethylpyrazine": "trimethylpyrazine", "2,3,5-trimethylpyrazine": "trimethylpyrazine",
    "2,6-dimethylpyrazine": "2,6-dimethylpyrazine", "acetaldehyde": "acetaldehyde",
    "acetal": "acetal", "1,1-diethoxyethane": "acetal", "hexanal": "hexanal",
    "isovaleraldehyde": "isovaleraldehyde", "3-methylbutanal": "isovaleraldehyde",
    "p-cresol": "p-cresol", "4-methylphenol": "p-cresol", "phenol": "phenol",
    "butyl acetate": "butyl acetate", "hexyl acetate": "hexyl acetate",
    "ethyl decanoate": "ethyl decanoate", "ethyl nonanoate": "ethyl nonanoate",
    "hexyl butanoate": "hexyl butanoate", "ethyl lactate": "ethyl lactate",
    "hexyl hexanoate": "hexyl hexanoate", "butyl hexanoate": "butyl hexanoate",
    "ethyl phenylacetate": "ethyl phenylacetate", "phenethyl acetate": "phenethyl acetate",
    "ethyl palmitate": "ethyl palmitate", "ethyl isobutyrate": "ethyl isobutyrate",
    "ethyl 2-methylbutanoate": "ethyl 2-methylbutanoate", "ethyl hexanoate": "ethyl hexanoate",
    "ethyl acetate": "ethyl acetate", "ethyl butyrate": "ethyl butyrate",
    "ethyl valerate": "ethyl valerate", "ethyl caprylate": "ethyl caprylate",
    "1-butanol": "1-butanol", "1-hexanol": "1-hexanol", "1-octanol": "1-octanol",
    "1-propanol": "1-propanol", "1-octen-3-ol": "1-octen-3-ol",
    "acetic acid": "acetic acid", "butyric acid": "butyric acid",
    "butanoic acid": "butyric acid", "hexanoic acid": "hexanoic acid",
    "caproic acid": "hexanoic acid", "octanoic acid": "octanoic acid",
    "caprylic acid": "octanoic acid", "heptanoic acid": "heptanoic acid",
    "propionic acid": "propionic acid", "propanoic acid": "propionic acid",
    "3-phenylpropionic acid": "3-phenylpropionic acid",
    "2-(ethoxymethyl)furan": "2-(ethoxymethyl)furan", "e-2-octenal": "e-2-octenal",
}.items()}

master_keys = set(comp_master["norm_key"])
thr["master_key"] = thr["compound_key"].map(lambda k: ALIAS.get(k, k))
thr["matched"] = thr["master_key"].isin(master_keys)

matched = thr[thr["matched"] & thr["thr_ugL"].notna()]
thr_consensus = (
    matched.groupby("master_key")
    .agg(threshold_ugL_median=("thr_ugL", "median"),
         threshold_ugL_min=("thr_ugL", "min"),
         threshold_ugL_max=("thr_ugL", "max"),
         n_threshold_sources=("thr_ugL", "size"),
         source_tabs=("sheet_tab", lambda x: ";".join(sorted(set(x))[:3])))
    .reset_index()
)
n_unmatched = int((~thr["matched"]).sum())
issue("threshold_harvest", "medium", "12 literature tabs",
      f"{len(thr)} threshold cells harvested for {thr['compound_key'].nunique()} literature names; "
      f"{n_unmatched} cells ({thr.loc[~thr['matched'], 'compound_key'].nunique()} names) could not be "
      f"mapped onto a master compound",
      f"{len(thr_consensus)} master compounds received a threshold (median of sources)")
thr.to_csv(os.path.join(OUT, "thresholds_raw.csv"), index=False, encoding="utf-8-sig")
thr_consensus.to_csv(os.path.join(OUT, "thresholds_consensus.csv"), index=False, encoding="utf-8-sig")

comp_master = comp_master.merge(thr_consensus, left_on="norm_key", right_on="master_key",
                                how="left").drop(columns=["master_key"])
comp_master.to_csv(os.path.join(OUT, "compound_master.csv"), index=False, encoding="utf-8-sig")
print(f"  thresholds: {len(thr)} cells -> {len(thr_consensus)} compounds matched")

# ===========================================================================
# 4. column registry (study / sample / unit)
# ===========================================================================
STUDY_LABEL = {
    1: "LZ-2016 SAB / GJ-1573 基础酒对比",
    2: "Y1/Y3/Y5/Y8/Y11 陈酿年份序列",
    3: "LZLJ-M7 / LZLJ-T7",
    4: "LS / FS 液液萃取",
    5: "脉冲电场处理 PEF (S1/S2/S3/F1/F3)",
    6: "JH / SC 产区样品",
    7: "CB / FB / SB",
    8: "(未标注) 第 8 组",
    9: "分级基酒 B1-B5 (H/L)",
    10: "风味重组样品 1-8",
    11: "优级/一级/二级/丢糟 等级",
    12: "高粱营养品质 JZG/JZ12/CZ5/JZB/LZ1/LZ2",
    13: "四川不同产区 (g/L)",
    14: "GCxGC-MS 含量 A/B/C",
    15: "全二维 GC-TOFMS L1/L2",
    16: "5 种品牌浓香型白酒",
    17: "北派年份标记物 质量浓度 A/B/C",
    18: "不同贮存年份五粮浓香 X0-X8",
    19: "浓香型 LZ",
    20: "三种香型 NX 平均含量",
    21: "浓香型等级评判 NX 平均含量",
    22: "乙醇代谢 SC1-SC3 / JS",
    23: "2/3/5 年陈",
    24: "典型 5 产区浓香型 (JNC/LZLJ/WLY/GJG/JSY)",
    25: "山东沂蒙老区成品酒 / 新老原酒",
    26: "一级好酒/一级差酒/二级好酒/二级差酒/三级酒",
    27: "GC-QTOF MS NX1-NX10",
    28: "酱香型 vs 浓香型 (n-c / n-g)",
    29: "两种原粮酿造 G1/G2",
    30: "洋河绵柔型白酒 (41.6%HZL/41%TZL/46%TZL/52%TZL/42.6%MZL)",
    31: "洋河天之蓝 vs 二锅头 46%/52%",
    32: "基酒味觉特征分组（均衡/微涩/较涩/涩味/苦味）",
    33: "宜宾产区 S-Y*/S-L*/A-GJG/G-J1/J-Y1",
}

# unit overrides where the master header does not declare one
# (inferred from the matching literature tab; see report for evidence)
UNIT_OVERRIDE = {
    1: "ug/l", 2: "ug/l", 4: "ug/l", 6: "ug/l", 7: "ug/l", 9: "ug/l",
    10: "ug/l", 12: "ug/l", 14: "mg/l", 15: "mg/l", 16: "mg/l",
    17: "ug/l", 18: "mg/l", 19: "mg/l", 20: "mg/l", 21: "mg/l",
    22: "ug/l", 23: "mg/l", 24: "ug/l", 25: "ug/l", 26: "mg/100ml",
    27: "mg/l", 28: "ug/l", 29: "mg/ml", 31: "ug/l", 32: "mg/l",
    33: "ug/l", 3: "ug/l", 11: "mg/l", 8: "",
}
# samples that are OAV (dimensionless) rather than a concentration
OAV_ONLY_COLS: set[int] = set()
# study 31/30 columns giving OAV explicitly
for ci, h in enumerate(DATA_HEADERS):
    if h and "oav" in str(h).lower():
        OAV_ONLY_COLS.add(ci)

# a few column-specific overrides (col index within DATA_HEADERS)
COL_UNIT_OVERRIDE: dict[int, str] = {}

# ---- curated column-level study / unit overrides (see report for evidence)
COL_STUDY_OVERRIDE = {}
for _ci in range(0, 2):            # 'LZ-2016 base SAB', 'GJ-1573'
    COL_STUDY_OVERRIDE[_ci] = 1
for _ci in range(2, 7):            # 'Y1'..'Y11'  (study 2; number lost in the master header)
    COL_STUDY_OVERRIDE[_ci] = 2
for _ci in range(96, 101):         # 典型5浓香型 JNC/LZLJ/WLY/GJG/JSY
    COL_STUDY_OVERRIDE[_ci] = 24
for _ci in range(101, 103):        # 沂蒙老区新老原酒 新酒/老酒浓度
    COL_STUDY_OVERRIDE[_ci] = 25
for _ci in range(124, 129):        # 3 41.6%HZL .. 42.6%MZL  (paper 30)
    COL_STUDY_OVERRIDE[_ci] = 30

UNIT_OVERRIDE.setdefault(1, "ug/l")
UNIT_OVERRIDE.setdefault(24, "ug/l")
UNIT_OVERRIDE.setdefault(30, "mg/l")
UNIT_OVERRIDE.setdefault(32, "g/l")

# Evidence-based unit corrections for whole study groups whose *declared* unit in
# the master header contradicts the sibling workbook / the OAV identity (see report):
#   study 2  'Y1..Y11'      master says μg/L, data.xlsx says μg/ml (= mg/L)   -> x1000
#   study 6  'JH1..SC6'     master says μg/L, implied OAV = conc/thr matches
#                           data.xlsx's OAV column only if conc is in mg/L   -> x1000
GROUP_UNIT_CORRECTION = {2: ("mg/l", "μg/mL(=mg/L) per data.xlsx header + OAV identity"),
                         6: ("mg/l", "mg/L inferred from the OAV identity vs data.xlsx")}

created_headers = []
cur = dict(study=np.nan, unit="", conf="", label="")
for ci, raw in enumerate(DATA_HEADERS):
    h = cl.s(raw)
    if h == "":
        created_headers.append(None)
        continue
    study, sample, unit_decl, _ = cl.parse_data_column(h)
    # master-header typos: '2 NX ...' is study 20, '3 41.6% ...' is study 30
    if h.startswith("2 NX 平均含量"):
        study = 20
    if ci in COL_STUDY_OVERRIDE:
        study = COL_STUDY_OVERRIDE[ci]

    unit = cl.norm_unit(unit_decl) if unit_decl else ""
    conf = "declared" if unit else ""

    if study == study:                       # this header starts a new group
        cur["study"] = int(study)
        cur["label"] = STUDY_LABEL.get(int(study), "")
    if unit:
        cur["unit"], cur["conf"] = unit, conf
    elif not unit and not unit_decl:
        # inherit the group's unit; a new study switches to its default
        if study == study:
            u = UNIT_OVERRIDE.get(int(study), "")
            cur["unit"], cur["conf"] = u, ("inferred_study" if u else "")
        # else keep inheriting
    if ci in COL_UNIT_OVERRIDE:
        cur["unit"], cur["conf"] = COL_UNIT_OVERRIDE[ci], "curated_column"
    if not cur["unit"] and "年陈" in h:
        cur["unit"], cur["conf"] = "mg/l", "curated_column"
    unit_pre = cur["unit"]
    if cur["study"] in GROUP_UNIT_CORRECTION and ci not in COL_UNIT_OVERRIDE:
        newu, why = GROUP_UNIT_CORRECTION[cur["study"]]
        if cl.norm_unit(cur["unit"]) != cl.norm_unit(newu):
            issue("unit_correction", "high",
                  f"study {int(cur['study'])} column '{h}'",
                  f"declared unit {cur['unit']!r} contradicts the sibling workbook / "
                  f"OAV identity (off by x1000); {why}",
                  f"corrected to {newu!r}")
            cur["unit"], cur["conf"] = newu, "corrected_declared"

    role = "oav" if ci in OAV_ONLY_COLS else "concentration"
    created_headers.append(dict(
        col_index=ci, header_raw=h, study_no=cur["study"],
        study_label=cur["label"], sample_label=sample,
        unit_declared=unit_decl, unit=cur["unit"], unit_confidence=cur["conf"],
        unit_pre_correction=unit_pre,
        col_role=role,
        unit_factor=(cl.UNIT_FACTORS.get(cl.norm_unit(cur["unit"]), np.nan)
                     if cur["unit"] else np.nan),
    ))

cols = pd.DataFrame([c for c in created_headers if c])
cols.to_csv(os.path.join(OUT, "column_registry.csv"), index=False, encoding="utf-8-sig")
n_no_unit = int((cols["unit"] == "").sum())
issue("unit", "high", "master matrix columns",
      f"{n_no_unit} of {len(cols)} data columns carry no decodable unit "
      f"(header gives no unit and the study default is unknown)",
      "kept as unit-unknown; used only for rank-based (scale-free) analysis")
issue("unit", "medium", "master matrix columns",
      f"{int((cols['unit_confidence'] == 'inferred_study').sum())} columns use a study-level unit "
      f"inferred from the matching literature tab rather than a declared unit",
      "flagged unit_confidence='inferred_study'")
print(f"  columns : {len(cols)} numeric columns, {n_no_unit} without a unit")
print(f"            unit confidence: {cols['unit_confidence'].value_counts().to_dict()}")

# ---- 5d. cross-workbook value repair (the "deleted zero" signature)
# The master library lost every '0' digit in a number of cells ('738,302' -> '738,32',
# '4,021,850' -> '4,21,85').  data.xlsx kept the original strings, so a cell can be
# repaired exactly when stripping every '0' from both strings yields the same residue.
def label_key(h: str) -> str:
    t = cl.norm_dash(cl.s(h)).lower()
    t = re.sub(r"^(\d{1,2})\b(?![\d%.,])", " ", t)
    t = re.sub(r"[（(][^）)]*[)）]", " ", t)
    t = re.sub(r"(?i)\b[μu]g\s*/\s*ml|[μu]g\s*/\s*l|mg\s*/\s*ml|mg\s*/\s*l|g\s*/\s*l"
               r"|mg\s*/\s*100\s*ml\b", " ", t)
    t = re.sub(r"\boav\b", " ", t)
    t = re.sub(r"[^a-z0-9%]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def zero_residue(x: str) -> str:
    return re.sub(r"\D", "", cl.s(x)).replace("0", "")


sib_lookup: dict[tuple[str, str], list] = {}
for r in s_body:
    key = cl.norm_key(r[2]) or cl.norm_key(r[3])
    if not key:
        continue
    for ci, raw in enumerate(r[META_COLS:], start=META_COLS):
        if cl.s(raw) == "" or ci >= len(s_hdr) or s_hdr[ci] is None:
            continue
        sib_lookup.setdefault((key, label_key(s_hdr[ci])), []).append(cl.s(raw))

repaired = 0
for i, r in enumerate(m_body):
    key = comp["norm_key"].iloc[i]
    for ci, raw in enumerate(DATA_HEADERS):
        cell = cl.s(r[META_COLS + ci])
        if cell == "":
            continue
        cands = sib_lookup.get((key, label_key(raw)))
        if not cands:
            continue
        best = None
        for c in cands:
            if zero_residue(c) == zero_residue(cell) and cl.s(c) != cell:
                m1, *_ = cl.parse_measure(cell)
                m2, *_ = cl.parse_measure(c)
                if np.isfinite(m2) and (not np.isfinite(m1) or m1 != m2):
                    best = (c, m1, m2)
                    break
        if best:
            r[META_COLS + ci] = best[0]
            repaired += 1
            issue("value_repair", "high", f"{comp['name_en'].iloc[i]} / {cl.s(raw)}",
                  f"master value {cell!r} lost digit(s) (deleted-zero corruption)",
                  f"restored {cl.s(best[0])!r} from data.xlsx")
print(f"  value repair: {repaired} cells restored from data.xlsx (deleted-zero signature)")

# ===========================================================================
# 5. long-format value table with unit harmonisation
# ===========================================================================
comp_lookup = comp_master.set_index("compound_uid")
row_uid = [comp["compound_uid"].iloc[i] for i in range(len(comp))]

records = []
for ri, r in enumerate(m_body):
    uid = comp["compound_uid"].iloc[ri]
    meta = comp_lookup.loc[uid]
    for ci, raw in enumerate(DATA_HEADERS):
        h = cl.s(raw)
        if h == "":
            continue
        cell = r[META_COLS + ci]
        txt = cl.s(cell)
        if txt == "":
            continue
        mean, sd, lo, hi, usuf, flags = cl.parse_measure(cell)
        rec = created_headers[ci]
        unit = rec["unit"]
        if usuf:
            unit = cl.norm_unit(usuf)
        val_ugL, ok = cl.to_ug_per_l(mean, unit) if unit else (np.nan, False)
        records.append(dict(
            compound_uid=uid, name_en=meta["name_en"], name_zh=meta["name_zh"],
            cas=meta["cas"], chem_class=meta["chem_class"],
            col_index=ci, header_raw=h, study_no=rec["study_no"],
            study_label=rec["study_label"], sample_label=rec["sample_label"],
            col_role=rec["col_role"], unit=unit,
            unit_confidence=rec["unit_confidence"] if not usuf else "declared_cell",
            value_raw=txt, value_mean=mean, value_sd=sd, value_lo=lo, value_hi=hi,
            value_ugL=val_ugL, converted=ok, flags="|".join(sorted(flags)),
            threshold_ugL=meta.get("threshold_ugL_median", np.nan),
        ))

long = pd.DataFrame(records)
long["oav"] = np.where(long["converted"], long["value_ugL"] / long["threshold_ugL"], np.nan)
long.to_csv(os.path.join(OUT, "master_long.csv"), index=False, encoding="utf-8-sig")
print(f"  long table: {len(long)} cells "
      f"({int(long['converted'].sum())} converted to μg/L)")

# ---- 5b. 己酸乙酯 (ethyl hexanoate) marker-based unit plausibility check
# 己酸乙酯 is the defining congener of 浓香型白酒: literature reports it at
# 0.5–4 g/L (5e5–4e6 μg/L) in base and commercial liquor.  It is reported by
# nearly every study in this library, which makes it a reliable scale marker.
MARKER = "ethyl hexanoate"
MARKER_WINDOW = (1.0e4, 1.0e7)      # μg/L — deliberately wide (includes diluted/GC-MS semi-quant)
long["_key"] = long["name_en"].map(cl.norm_key)
ref_rows = []
REF_COMPOUNDS = {
    "ethyl hexanoate": (5.0e4, 5.0e6),
    "ethyl acetate": (1.0e5, 4.0e6),
    "ethyl lactate": (5.0e4, 3.0e6),
    "ethyl butyrate": (1.0e4, 1.0e6),
    "hexanoic acid": (1.0e4, 1.2e6),
    "acetic acid": (1.0e4, 1.5e6),
    "1-butanol": (1.0e3, 5.0e5),
    "3-methyl-1-butanol": (1.0e4, 1.0e6),
}
for ck, g in long[long["converted"]].groupby("col_index"):
    marker = g.loc[g["_key"] == MARKER, "value_ugL"]
    mv = float(marker.iloc[0]) if len(marker) and np.isfinite(marker.iloc[0]) else np.nan
    hits = tot = 0
    for k, (lo, hi) in REF_COMPOUNDS.items():
        v = g.loc[g["_key"] == k, "value_ugL"]
        if len(v) == 0 or not np.isfinite(v.iloc[0]) or v.iloc[0] <= 0:
            continue
        tot += 1
        hits += int(lo <= v.iloc[0] <= hi)
    ref_rows.append(dict(
        col_index=ck, header=g["header_raw"].iloc[0],
        unit=g["unit"].iloc[0], unit_confidence=g["unit_confidence"].iloc[0],
        marker_ugL=mv, marker_in_window=(MARKER_WINDOW[0] <= mv <= MARKER_WINDOW[1]) if np.isfinite(mv) else np.nan,
        n_reference=tot, n_plausible=hits,
        frac_plausible=(hits / tot) if tot else np.nan,
    ))
plaus = pd.DataFrame(ref_rows)
plaus.to_csv(os.path.join(OUT, "unit_plausibility.csv"), index=False, encoding="utf-8-sig")
suspect = plaus[plaus["marker_in_window"] == False]  # noqa: E712
for _, r in suspect.iterrows():
    issue("unit_plausibility", "medium", f"column '{r['header']}' (col {r['col_index']})",
          f"己酸乙酯 = {r['marker_ugL']:.4g} μg/L after conversion, outside the wide "
          f"plausible window {MARKER_WINDOW[0]:.0e}-{MARKER_WINDOW[1]:.0e} μg/L "
          f"({r['n_plausible']}/{r['n_reference']} reference congeners in range)",
          "flagged for manual unit review; retained at the corrected unit")
print(f"  plausibility: {len(suspect)} of {len(plaus)} columns remain outside the "
      f"己酸乙酯 window after correction")

plaus["unit_verdict"] = np.select(
    [plaus["marker_in_window"] == True, plaus["marker_in_window"] == False],  # noqa: E712
    ["ok", "implausible"], default="unverified",
)
cols = cols.merge(
    plaus[["col_index", "marker_ugL", "n_reference", "n_plausible", "unit_verdict"]],
    on="col_index", how="left",
)
cols["usable_absolute"] = cols["unit_verdict"].eq("ok")
cols.to_csv(os.path.join(OUT, "column_registry.csv"), index=False, encoding="utf-8-sig")
long = long.merge(plaus[["col_index", "unit_verdict"]], on="col_index", how="left")
long["usable_absolute"] = long["unit_verdict"].eq("ok")
long.to_csv(os.path.join(OUT, "master_long.csv"), index=False, encoding="utf-8-sig")
n_ok = int(cols["usable_absolute"].sum())
print(f"  unit verdict: ok={n_ok}, implausible={int((cols['unit_verdict'] == 'implausible').sum())}, "
      f"unverified={int((cols['unit_verdict'] == 'unverified').sum())}")

# ===========================================================================
# 6. wide matrices
# ===========================================================================
long["col_key"] = long["header_raw"]
wide_ugL = long.pivot_table(index=["compound_uid", "name_en", "name_zh", "cas", "chem_class"],
                            columns="col_key", values="value_ugL", aggfunc="first")
wide_raw = long.pivot_table(index=["compound_uid", "name_en", "name_zh", "cas", "chem_class"],
                            columns="col_key", values="value_mean", aggfunc="first")
wide_ugL.to_csv(os.path.join(OUT, "master_wide_ugL.csv"), encoding="utf-8-sig")
wide_raw.to_csv(os.path.join(OUT, "master_wide_raw.csv"), encoding="utf-8-sig")

# rank-based (scale-free) matrix: within-column percentile rank, 0-1
wide_rank = wide_raw.rank(pct=True, na_option="keep")
wide_rank.to_csv(os.path.join(OUT, "master_wide_rank.csv"), encoding="utf-8-sig")

# ===========================================================================
# 7. OAV summary
# ===========================================================================
oav_cells = long[long["oav"].notna() & long["usable_absolute"]].copy()
oav_sum = (
    oav_cells.groupby(["compound_uid", "name_en", "name_zh", "cas", "chem_class",
                       "threshold_ugL"], dropna=False)
    .agg(n_measurements=("oav", "size"), oav_median=("oav", "median"),
         oav_max=("oav", "max"), oav_min=("oav", "min"),
         n_oav_gt1=("oav", lambda x: int((x > 1).sum())),
         frac_oav_gt1=("oav", lambda x: float((x > 1).mean())))
    .reset_index()
    .sort_values("oav_median", ascending=False)
)
oav_sum.to_csv(os.path.join(OUT, "oav_summary.csv"), index=False, encoding="utf-8-sig")

# also fold in the OAV columns that the literature tabs already report
oav_lit = sheets[sheets["role"] == "oav"].copy()
oav_lit["key"] = oav_lit["compound_raw"].map(cl.norm_key).map(lambda k: ALIAS.get(k, k))
oav_lit = oav_lit[oav_lit["key"].isin(master_keys)]
oav_lit_sum = (
    oav_lit.groupby("key")["value_mean"]
    .agg(n_lit_oav="size", oav_lit_median="median", oav_lit_max="max").reset_index()
)
oav_sum = oav_sum.merge(oav_lit_sum, left_on="name_en", right_on="key", how="left").drop(columns=["key"])
oav_sum.to_csv(os.path.join(OUT, "oav_summary.csv"), index=False, encoding="utf-8-sig")
print(f"  OAV: {len(oav_cells)} computable cells, "
      f"{int((oav_sum['oav_median'] > 1).sum())} compounds with median OAV > 1")

issues_df = pd.DataFrame(ISSUES)
issues_df.to_csv(os.path.join(OUT, "issues_log.csv"), index=False, encoding="utf-8-sig")

# ===========================================================================
# 8. quality report
# ===========================================================================
lines = []
A = lines.append
A("# 数据质量报告 — data总库.xlsx")
A("")
A("本报告由 `new/20_clean_master.py` 自动生成；源文件只读，未被修改。")
A("")
A("## 1. 数据规模")
A("")
A(f"| 项目 | 数量 |")
A(f"|---|---|")
A(f"| 主表原始行（含表头） | {len(m_body) + 1} |")
A(f"| 主表原始列 | {len(m_hdr)} |")
A(f"| 元数据列 | {META_COLS} |")
A(f"| 数值列（文献/样品） | {len(DATA_HEADERS)} |")
A(f"| 非空数值列 | {len(cols)} |")
A(f"| 化合物原始行 | {len(comp)} |")
A(f"| 去重后化合物 | {len(comp_master)} |")
A(f"| 文献工作表（sheet tab） | 12 |")
A(f"| 解析出的数值单元 | {len(long)} |")
A(f"| 可换算为 μg/L 的单元 | {int(long['converted'].sum())} |")
A("")
A("## 2. 清洗动作清单")
A("")
A("### 2.1 CAS 号修复")
A("")
st = comp["cas_status"].value_counts()
A("| 状态 | 行数 | 含义 |")
A("|---|---|---|")
meanings = {
    "ok": "原始值即通过 CAS 校验位",
    "repaired_sibling": "由 data.xlsx（按 SMILES 连接）取回正确值",
    "repaired_checksum": "删除的 0 被算法重新插回并通过校验位",
    "unverified": "仅保留数字、仍无法通过校验位（保留供人工核对）",
}
for k, v in st.items():
    A(f"| {k} | {v} | {meanings.get(k, '')} |")
A("")
A("主要损坏模式（详见 `issues_log.csv`）：")
A("")
A("- **缺失的 0 被 Excel 删除**：`18-64-5` → `108-64-5`、`15-54-4` → `105-54-4`、`17-92-6` → `107-92-6`")
A("- **被 Excel 识别为日期**：`3658-80-8` → `3658-08-08 00:00:00`；`106-30-9` → `216/3/9`；`106-70-7` → `216/7/7`")
A("- **破折号混用**：`16–32–1`（en dash）应为 `106-32-1`")
A("- **前导数字丢失**：`221-28-5`（无效）应为 `2021-28-5`；`51-52-` 应为 `501-52-0`")
A("")
A("### 2.2 化合物名称规范化")
A("")
A("| 原始名 | 规范名 | 说明 |")
A("|---|---|---|")
for k, (v, _) in NAME_REPAIR.items():
    A(f"| `{k}` | `{v}` | 拼写/同义词纠正 |")
A("")
A(f"检测到 **{len(dups)} 行** 重复化合物（同一身份键），已合并：")
A("")
A("| 化合物 | 原始 Order ID |")
A("|---|---|")
for k, g in dups.groupby("norm_key"):
    A(f"| {g['name_en'].iloc[0]} | {', '.join(map(str, g['order_id']))} |")
A("")
A("### 2.3 单位统一")
A("")
A("所有浓度按列单位换算为 μg/L：")
A("")
A("| 单位 | 换算系数 → μg/L |")
A("|---|---|")
for u, f in cl.UNIT_FACTORS.items():
    if not (isinstance(f, float) and np.isnan(f)):
        A(f"| {u} | ×{f:g} |")
A("")
A(f"- 表头显式声明单位：**{int((cols['unit_confidence'] == 'declared').sum())}** 列")
A(f"- 由对应文献工作表推断：**{int((cols['unit_confidence'] == 'inferred_study').sum())}** 列")
A(f"- 单元格内自带单位：**{int((long['unit_confidence'] == 'declared_cell').sum())}** 个单元")
A(f"- 单位未知：**{n_no_unit}** 列（仅参与秩相关等无量纲分析）")
A("")
A("### 2.4 缺失值与非数值编码")
A("")
flagc = long["flags"].fillna("").str.split("|").explode().value_counts()
A("| 标记 | 单元数 | 含义与处理 |")
A("|---|---|---|")
flag_mean = {
    "": "正常解析",
    "missing_code": "NF / ND / — / \\ / (空) / N/D 等占位符 → 置为缺失",
    "signif_letter": "Duncan 显著性字母（a/b/c…）→ 剥离后取均值",
    "lt": "低于检出限（<1）→ 按 1 保留并加标记",
    "gt": "高于上限（>N）→ 按 N 保留并加标记",
    "range": "区间值（如 200-316）→ 取中点，半宽记为 SD",
    "corrupt_thousands_sep": "千分位被破坏 → 仅保留首个分组并标红",
    "unparsed": "无法解析 → 置为缺失",
    "empty": "空单元格 → 缺失",
}
for k, v in flagc.items():
    A(f"| `{k or 'clean'}` | {v} | {flag_mean.get(k, '')} |")
A("")
A("### 2.5 阈值补全与 OAV")
A("")
A(f"主表 `Threshold` 与 `Concentration（μg/L）` 两列在源文件中**完全为空**。")
A(f"本次从 12 个文献工作表中抽取了 **{len(thr)}** 个阈值单元，覆盖 "
  f"{thr['compound_raw'].nunique()} 个文献名，成功匹配 **{len(thr_consensus)}** 个主表化合物。")
A("")
A("| 项目 | 数量 |")
A("|---|---|")
A(f"| 阈值单元 | {len(thr)} |")
A(f"| 匹配到主表化合物 | {len(thr_consensus)} |")
A(f"| 未匹配（文献独有化合物/拼写差异） | {n_unmatched} |")
A(f"| 可计算 OAV 的浓度单元 | {len(oav_cells)} |")
A(f"| 中位 OAV > 1 的化合物 | {int((oav_sum['oav_median'] > 1).sum())} |")
A("")
A("## 3. 问题清单（按严重度）")
A("")
sev = issues_df["severity"].value_counts().to_dict() if len(issues_df) else {}
A(f"严重 high: {sev.get('high', 0)} 项；中等 medium: {sev.get('medium', 0)} 项；"
  f"轻微 low: {sev.get('low', 0)} 项。完整清单见 `issues_log.csv`。")
A("")
A("## 4. 产出文件")
A("")
A("| 文件 | 内容 |")
A("|---|---|")
for f, d in [
    ("sheets_long.csv", "12 个文献工作表的整洁长表（复现 10_extract_sources.py 的结果）"),
    ("compound_registry.csv", "化合物逐行登记（含 CAS 修复状态与来源）"),
    ("compound_master.csv", "去重后的化合物主表（含化学类别与阈值）"),
    ("column_registry.csv", "列登记表：研究编号 / 样品 / 单位 / 单位置信度"),
    ("master_long.csv", "全库整洁长表：每个浓度单元一行，含 μg/L 换算值与 OAV"),
    ("master_wide_raw.csv", "宽表（原始数值）"),
    ("master_wide_ugL.csv", "宽表（统一为 μg/L）"),
    ("master_wide_rank.csv", "宽表（列内百分位秩，无量纲，用于跨单位相关分析）"),
    ("thresholds_raw.csv", "从文献表抽取的全部阈值单元"),
    ("thresholds_consensus.csv", "化合物阈值共识值（取多来源中位数）"),
    ("oav_summary.csv", "OAV 汇总：中位/最大 OAV、OAV>1 样品比例"),
    ("issues_log.csv", "问题日志（类型/严重度/范围/细节/处理）"),
]:
    A(f"| `{f}` | {d} |")

with open(os.path.join(OUT, "data_quality_report.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print(f"\n-> {OUT}\\data_quality_report.md")
print(f"-> issues: {len(ISSUES)}")
