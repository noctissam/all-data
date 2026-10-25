# -*- coding: utf-8 -*-
"""
Step 6 - compound-centric dataset: the priority-1 deliverable.

Turns the reconstructed tables into one row per compound per sample with

    priority 1   compound name   CAS number   concentration (explicit unit)
    priority 2   odor threshold (explicit unit)

plus three independent checks:

  1. unit / arithmetic check   OAV = concentration / threshold must reproduce the
                               printed OAV. A wrong unit is off by 1000x, so this
                               validates the unit, the concentration and the threshold
                               at once - and it is independent of OCR, because it
                               compares numbers with each other rather than with a
                               second pass that shares the same misreadings.

  2. CAS resolution            name -> PubChem CID -> synonyms -> CAS number.

  3. name <-> CAS round trip   CAS -> CID again, plus CID -> canonical title, and
                               compare against the name printed in the paper. This is
                               the "CAS and name cross-check" - it is what catches a
                               mis-aligned row or a garbled compound name, which a
                               confidence score cannot.

Table screening (only some of the six tables carry compound-level quantitative data):
    T01  kept      16 base-SAB samples, concentration + OAV of one analyte
    T02  kept      LOD per compound - method validation, NOT an odor threshold
    T03  kept      60 compounds x threshold + 2 concentrations + 2 OAV   <- core
    T04  kept      18 compounds x FD factor + OAV + OAV ratio
    T05  DROPPED   omission analysis, significance letters only, no quantitative data
    T06  kept      4 mixtures x spiking level, qualitative aroma description

Usage:
    python src/s6_compound_dataset.py [--conf-ua] [--sleep 0.25]
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import GRID_DIR, LOG_DIR, OUT, ensure_dirs, load_json, load_tables, log  # noqa: E402

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CAS_RE = re.compile(r"^(\d{2,7}-\d{2}-\d)$")
FOOTNOTE = re.compile(r"^(.*?)\s*([a-z]{1,2})$")
DASHES = "−–—‒‐"


# --------------------------------------------------------------------------- numbers
def strip_footnote(s):
    """"55.3c" -> ("55.3", "c"); "p-cresol" keeps its letters because it has digits."""
    s = (s or "").strip()
    for d in DASHES:
        s = s.replace(d, "-")
    m = FOOTNOTE.match(s)
    if m and re.search(r"\d", m.group(1)):
        return m.group(1).strip(), m.group(2)
    return s, ""


def parse_mean_sd(s):
    """"7,606,936 +- 17,161" -> (7606936.0, 17161.0)"""
    base, _fn = strip_footnote(s)
    t = base.replace(",", "").replace(" ", "").replace("−", "-")
    m = re.match(r"^(-?\d+(?:\.\d+)?)(?:[±+*](\d+(?:\.\d+)?))?$", t)
    if not m:
        return None, None
    return float(m.group(1)), (float(m.group(2)) if m.group(2) else None)


def parse_num(s):
    v, _ = parse_mean_sd(s)
    return v


def fmt(v, nd=None):
    if v is None:
        return ""
    if nd is not None:
        return ("%%.%df" % nd) % v
    return ("%.6f" % v).rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- PubChem
_cache = {}


def _get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "compound-dataset/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def name_to_cid(name, sleep):
    key = ("cid", name)
    if key in _cache:
        return _cache[key]
    url = "%s/compound/name/%s/cids/JSON" % (PUG, urllib.parse.quote(name))
    j = _get(url)
    cids = (j or {}).get("IdentifierList", {}).get("CID") or []
    time.sleep(sleep)
    _cache[key] = cids[0] if cids else None
    return _cache[key]


def cid_to_cas(cid, sleep):
    key = ("cas", cid)
    if key in _cache:
        return _cache[key]
    url = "%s/compound/cid/%d/synonyms/JSON" % (PUG, cid)
    j = _get(url)
    time.sleep(sleep)
    syn = ((j or {}).get("InformationList", {})
           .get("Information", [{}])[0].get("Synonym") or [])
    cas = None
    for s in syn:
        s = s.strip()
        if CAS_RE.match(s):
            cas = s
            break
    _cache[key] = cas
    return cas


def cid_title(cid, sleep):
    key = ("title", cid)
    if key in _cache:
        return _cache[key]
    url = "%s/compound/cid/%d/property/Title,IUPACName/JSON" % (PUG, cid)
    j = _get(url)
    time.sleep(sleep)
    props = ((j or {}).get("PropertyTable", {}).get("Properties") or [{}])[0]
    _cache[key] = props.get("Title") or props.get("IUPACName")
    return _cache[key]


def cas_to_cid(cas, sleep):
    """Independent lookup: does the CAS number we found point back at the same CID?"""
    key = ("cas2cid", cas)
    if key in _cache:
        return _cache[key]
    url = "%s/compound/name/%s/cids/JSON" % (PUG, urllib.parse.quote(cas))
    j = _get(url)
    time.sleep(sleep)
    cids = (j or {}).get("IdentifierList", {}).get("CID") or []
    _cache[key] = cids[0] if cids else None
    return _cache[key]


def norm_name(s):
    s = (s or "").lower().strip()
    s = s.replace("γ", "gamma").replace("α", "alpha").replace("β", "beta")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def resolve_cas(paper_name, sleep, do_roundtrip=True):
    """
    name -> CID -> CAS, then verify by going back: CAS -> CID, and CID -> canonical
    title compared with the name the paper printed.
    Returns dict(cas, cid, cid_back, title, name_ok, status).
    """
    nm, _fn = strip_footnote(paper_name)
    cid = name_to_cid(nm, sleep) if nm else None
    if not cid:
        return dict(cas="", cid="", cid_back="", title="", name_ok="", status="no_cid")
    cas = cid_to_cas(cid, sleep)
    if not cas:
        return dict(cas="", cid=cid, cid_back="", title="", name_ok="", status="no_cas")
    title = cid_title(cid, sleep)
    a = norm_name(nm)
    b = norm_name(title)
    name_ok = ""
    if a and b:
        name_ok = "yes" if (a == b or a in b or b in a) else "no"
    back = cas_to_cid(cas, sleep) if do_roundtrip else None
    if back is None:
        status = "cas_only"
    elif back == cid:
        status = "verified"
    else:
        status = "cas_cid_mismatch"
    return dict(cas=cas, cid=cid, cid_back=back or "", title=title or "",
                name_ok=name_ok, status=status)


# --------------------------------------------------------------------------- OAV check
def oav_status(conc, thr, reported):
    """'' when not checkable; 'ok'; 'paper_inconsistent'; 'unit_suspect'."""
    if not conc or not thr or thr == 0 or not reported:
        return ""
    calc = conc / thr
    r = calc / reported
    if 0.98 <= r <= 1.02:
        return "ok"
    if abs(calc - reported) <= 0.5 or abs(calc - reported) / max(reported, 1e-9) <= 0.005:
        return "ok"
    # a unit slip shows up as a clean power of ten / thousand
    for k, lab in ((0.001, "unit_suspect x1/1000"), (1000.0, "unit_suspect x1000"),
                   (0.001 / 60, "unit_suspect mg/L"), (60.0, "unit_suspect x60"),
                   (1 / 0.85, "unit_suspect x0.85")):
        if abs(r * k - 1.0) < 0.02:
            return lab
    return "paper_inconsistent"


# --------------------------------------------------------------------------- tables
def unit_from_header(g, col, keyword):
    """
    Find the unit for a column by walking the merged header rows and collecting the
    text that spans this column. "(ug/L)" sitting under "Odor threshold" wins over the
    "Concentrations (ug/L)" group label that spans several columns.
    """
    got = []
    for row in g["header"]:
        c = 0
        for cell in row:
            span = cell["span"]
            if span >= 0:
                if c <= col < c + max(span, 1):
                    got.append(cell["text"])
                c += 1
    txt = " ".join(x for x in got if x)
    m = re.findall(r"\(([^)]*)\)", txt)
    for cand in m:
        if keyword.lower() in cand.lower():
            return cand.strip()
    for cand in m:
        if re.search(r"[μugmg]", cand, re.I) and "/" in cand:
            return cand.strip()
    return ""


def row_cells(g, row):
    out = []
    for cell in row:
        if cell["span"] >= 0:
            out.append(cell["text"])
    return out


def load(name):
    p = os.path.join(GRID_DIR, "%s_grid.json" % name)
    return load_json(p) if os.path.exists(p) else None


# --------------------------------------------------------------------------- builders
def build_T03(g, sleep, roundtrip):
    thr_unit = unit_from_header(g, 2, "threshold") or unit_from_header(g, 2, "")
    con_unit = unit_from_header(g, 3, "concentration") or unit_from_header(g, 3, "")
    rows = []
    for i, r in enumerate(g["body"]):
        c = row_cells(g, r)
        if len(c) < 7:
            continue
        raw_name = c[1]
        name, fn = strip_footnote(raw_name)
        thr_raw, thr_fn = strip_footnote(c[2])
        thr, thr_sd = parse_mean_sd(c[2])
        c_lz, sd_lz = parse_mean_sd(c[3])
        c_gj, sd_gj = parse_mean_sd(c[4])
        o_lz = parse_num(c[5])
        o_gj = parse_num(c[6])
        cas = resolve_cas(name, sleep, roundtrip)
        rows.append(dict(
            table=g["id"], page=g["page"], row=i + 1,
            compound=name, footnote=fn,
            cas=cas["cas"], pubchem_cid=cas["cid"], cas_roundtrip_cid=cas["cid_back"],
            pubchem_title=cas["title"], cas_status=cas["status"], name_matches_cas=cas["name_ok"],
            odor_threshold=fmt(thr), threshold_unit=thr_unit,
            conc_LZ2016=fmt(c_lz), sd_LZ2016=fmt(sd_lz),
            conc_GJ1573=fmt(c_gj), sd_GJ1573=fmt(sd_gj),
            conc_unit=con_unit,
            oav_LZ2016_paper=fmt(o_lz), oav_GJ1573_paper=fmt(o_gj),
            oav_LZ2016_calc=fmt(c_lz / thr) if (c_lz and thr) else "",
            oav_check=oav_status(c_lz, thr, o_lz),
            oav_check_GJ=oav_status(c_gj, thr, o_gj),
            threshold_source="paper table (ref %s)" % (thr_fn or "?"),
        ))
    return rows


def build_T04(g, sleep, roundtrip):
    rows = []
    for i, r in enumerate(g["body"]):
        c = row_cells(g, r)
        if len(c) < 7:
            continue
        name, fn = strip_footnote(c[1])
        cas = resolve_cas(name, sleep, roundtrip)
        rows.append(dict(
            table=g["id"], page=g["page"], row=i + 1, compound=name, footnote=fn,
            cas=cas["cas"], pubchem_cid=cas["cid"], cas_roundtrip_cid=cas["cid_back"],
            pubchem_title=cas["title"], cas_status=cas["status"],
            name_matches_cas=cas["name_ok"],
            fd_factor=c[2],
            oav_LZ2016=c[3], oav_GJ1573=c[4],
            oav_LZ2016_gj_lt1=c[5], oav_ratio_LZ_over_GJ=c[6],
            note="T04 reports OAV only; no raw concentration column",
        ))
    return rows


def build_T01(g, sleep, roundtrip):
    """One analyte quantified across 16 base-SAB samples; the analyte is in the caption."""
    analyte = "3-(methylthio)propanal"
    cas = resolve_cas(analyte, sleep, roundtrip)
    conc_unit = unit_from_header(g, 4, "concentration") or "μg/L"
    rows = []
    for i, r in enumerate(g["body"]):
        c = row_cells(g, r)
        if len(c) < 6:
            continue
        conc, sd = parse_mean_sd(c[3])
        rows.append(dict(
            table=g["id"], page=g["page"], row=i + 1,
            sample=c[1], distillery=c[2],
            compound=analyte, cas=cas["cas"], pubchem_cid=cas["cid"],
            cas_status=cas["status"], name_matches_cas=cas["name_ok"],
            conc=fmt(conc), sd=fmt(sd), conc_unit=conc_unit,
            rsd_pct=c[4], oav=c[5],
            note="analyte taken from the table caption, not a per-row cell",
        ))
    return rows


def build_T02(g, sleep, roundtrip):
    """LOD per compound - a method detection limit, NOT an odor threshold."""
    lod_unit = unit_from_header(g, 9, "LOD") or "μg/L"
    rows = []
    for i, r in enumerate(g["body"]):
        c = row_cells(g, r)
        if len(c) < 11:
            continue
        if not c[1].strip():
            continue          # group label row ("Lactones", "Furans")
        name, fn = strip_footnote(c[1])
        cas = resolve_cas(name, sleep, roundtrip)
        rows.append(dict(
            table=g["id"], page=g["page"], row=i + 1, compound=name, footnote=fn,
            cas=cas["cas"], pubchem_cid=cas["cid"], cas_status=cas["status"],
            name_matches_cas=cas["name_ok"],
            methods=c[2], quant_ion=c[3], internal_standard=c[4],
            lin_slope=c[5], lin_intercept=c[6], lin_range=c[7], r2=c[8],
            lod=fmt(parse_num(c[9])), lod_unit=lod_unit, recovery_pct=c[10],
            note="LOD = method detection limit, do NOT use as odor threshold",
        ))
    return rows


def build_T06(g, sleep, roundtrip):
    unit = unit_from_header(g, 2, "spiking") or "μg/L"
    rows = []
    for i, r in enumerate(g["body"]):
        c = row_cells(g, r)
        if len(c) < 7:
            continue
        # mixture names list 2-3 components; resolve each
        parts = [p.strip() for p in re.split(r"\+", c[1]) if p.strip()]
        comps = []
        for p in parts:
            cas = resolve_cas(p, sleep, roundtrip)
            comps.append("%s [%s]" % (p, cas["cas"] or "CAS?"))
        rows.append(dict(
            table=g["id"], page=g["page"], row=i + 1,
            mixture=c[1], components=" + ".join(comps),
            spiking_level=fmt(parse_num(c[2])), spiking_unit=unit,
            recovery_pct=c[3], sd=c[4],
            aroma_description=c[5], interaction=c[6],
            note="mixture-level; components share one spiking level",
        ))
    return rows


# --------------------------------------------------------------------------- main
def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.25, help="pause between PubChem calls")
    ap.add_argument("--no-roundtrip", dest="roundtrip", action="store_false",
                    help="skip the CAS -> CID verification call")
    ap.add_argument("--only", default="", help="comma separated table ids")
    a = ap.parse_args()

    ensure_dirs()
    logfile = os.path.join(LOG_DIR, "s6_compounds.log")
    if os.path.exists(logfile):
        os.remove(logfile)
    log("STEP 6 - compound dataset (name / CAS / concentration / threshold)", logfile)

    db = load_tables()
    want = set(x.strip() for x in a.only.split(",") if x.strip())
    cdir = os.path.join(OUT, "compound")
    os.makedirs(cdir, exist_ok=True)

    jobs = [
        ("T03", "build_T03", "01_priority1_T03_化合物-阈值-浓度-OAV.csv",
         "60 compounds x odor threshold + 2 concentrations + 2 OAV  [CORE]"),
        ("T04", "build_T04", "02_T04_OAV与FD.csv",
         "18 compounds x FD factor + OAV + OAV ratio"),
        ("T01", "build_T01", "03_T01_各样品浓度.csv",
         "16 base-SAB samples, concentration + OAV of one analyte"),
        ("T02", "build_T02", "04_T02_LOD与方法学.csv",
         "LOD / linearity / recovery per compound (LOD is NOT an odor threshold)"),
        ("T06", "build_T06", "05_T06_混合物添加试验.csv",
         "4 mixtures x spiking level + aroma description"),
    ]

    summary = []
    for tid, fn, fname, desc in jobs:
        if want and tid not in want:
            continue
        g = load("%s_p%s" % (tid, {"T01": "02", "T02": "04", "T03": "05",
                                    "T04": "10", "T06": "12"}[tid]))
        if not g:
            log("  %s grid missing - skipped" % tid, logfile)
            continue
        rows = globals()[fn](g, a.sleep, a.roundtrip)
        if not rows:
            continue
        fields = list(rows[0].keys())
        write_csv(os.path.join(cdir, fname), rows, fields)

        n_cas = sum(1 for r in rows if r.get("cas"))
        n_ver = sum(1 for r in rows if r.get("cas_status") == "verified")
        n_mis = sum(1 for r in rows if r.get("name_matches_cas") == "no")
        checks = [r.get("oav_check", "") for r in rows if r.get("oav_check")]
        n_ok = sum(1 for c in checks if c == "ok")
        n_bad = sum(1 for c in checks if c not in ("ok", ""))
        summary.append((tid, fname, desc, len(rows), n_cas, n_ver, n_mis, n_ok, n_bad))
        log("  %s  rows=%-4d CAS=%-4d verified=%-4d name_mismatch=%-3d oav_ok=%-3d oav_flag=%-3d  %s"
            % (tid, len(rows), n_cas, n_ver, n_mis, n_ok, n_bad, fname), logfile)

    with open(os.path.join(cdir, "00_screening.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["表号", "PDF页", "是否保留", "理由", "产出文件", "行数",
                    "含优先级1字段(名称/浓度)", "含优先级2字段(阈值)"])
        rows = [
            ["T01", 2, "保留", "16个基酒样品中同一分析物的浓度+OAV；化合物名在表题里，不在行内",
             "03_T01_各样品浓度.csv"],
            ["T02", 4, "保留", "每化合物的LOD/线性/回收率。注意LOD是方法检出限，不能当香气阈值用",
             "04_T02_LOD与方法学.csv"],
            ["T03", 5, "保留(核心)", "60个化合物 x 香气阈值 + 2个样品浓度 + 2个OAV，一级+二级字段齐全",
             "01_priority1_T03_化合物-阈值-浓度-OAV.csv"],
            ["T04", 10, "保留", "18个化合物 x FD因子 + OAV + OAV比值；无原始浓度列(OAV等价于浓度)",
             "02_T04_OAV与FD.csv"],
            ["T05", 11, "丢弃", "省略试验的显著性字母，无任何定量数据",
             "-"],
            ["T06", 12, "保留", "4个混合物的添加水平+香气描述，定量但为混合物层面",
             "05_T06_混合物添加试验.csv"],
        ]
        for r in rows:
            w.writerow(r + ["", ""][:4])
    log("  screening table -> 00_screening.csv", logfile)
    log("compound dataset -> %s" % cdir, logfile)


if __name__ == "__main__":
    main()
