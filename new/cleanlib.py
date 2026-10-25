# -*- coding: utf-8 -*-
"""
cleanlib.py — shared cleaning primitives for the 浓香型白酒 flavour database.

Used by 10_extract_sources.py and 20_clean_master.py.
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np

# ---------------------------------------------------------------------------
# text normalisation
# ---------------------------------------------------------------------------
DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"), "-")


def norm_dash(x: str) -> str:
    return x.translate(DASHES)


def s(x) -> str:
    """Cell -> clean string ('' for None/NaN)."""
    if x is None:
        return ""
    if isinstance(x, float) and np.isnan(x):
        return ""
    return (
        norm_dash(str(x))
        .replace("\u200b", "")
        .replace("\xa0", " ")
        .replace("\ufeff", "")
        .strip()
    )


def norm_key(x) -> str:
    """Aggressive key for joining compound names across messy sources."""
    t = s(x).lower()
    t = unicodedata.normalize("NFKC", t)
    t = norm_dash(t)
    t = re.sub(r"\(.*?\)|（.*?）", " ", t)          # drop parentheticals
    t = re.sub(r"[\u4e00-\u9fff]+", " ", t)         # drop CJK
    t = t.replace("γ", "gamma").replace("α", "alpha").replace("β", "beta")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\b(dl|cas|no|n)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# numeric cell parsing
# ---------------------------------------------------------------------------
NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?")

MISSING_TOKENS = {
    "nf", "nd", "n.d", "n.d.", "n/d", "-", "--", "---", "—", "–", "\\", "/", "(空)",
    "空", "", "na", "n/a", "nan", "none", "未检出", "未测", "tr", "trace", "·",
    "value", "n.a.",
}


def token_is_missing(tok: str) -> bool:
    return tok.strip().lower().replace(" ", "") in MISSING_TOKENS


def _num(t: str, flags: set) -> float:
    t = t.strip()
    if t == "":
        return np.nan
    m = NUM_RE.search(t)
    if not m:
        flags.add("unparsed")
        return np.nan
    raw = m.group()
    if "," in raw:
        groups = raw.split(",")
        if any(len(g) != 3 for g in groups[1:]):
            flags.add("corrupt_thousands_sep")
            raw = groups[0]
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        flags.add("unparsed")
        return np.nan


def parse_measure(raw):
    """
    One literature cell -> (mean, sd, lo, hi, unit_suffix, flags:set).

    Handles '1234', '7,606,936 ± 17,161', '5320.56 ± 47.54b', '200-316a',
    '824.84 ~ 1237.73', '<1', '>2', 'NF', 'ND', '—', '\\', '(空)',
    '873,258 ± 9159 μg/l'.
    """
    flags = set()
    t = s(raw)
    if t == "":
        return (np.nan, np.nan, np.nan, np.nan, "", {"empty"})
    if token_is_missing(t):
        return (np.nan, np.nan, np.nan, np.nan, "", {"missing_code"})

    unit_suffix = ""
    m = re.search(r"([μu]g\s*/?\s*[lL]|mg\s*/?\s*[lL]|g\s*/?\s*[lL])\s*$", t)
    if m:
        unit_suffix = m.group(1)
        t = t[: m.start()].strip()

    if t.startswith("<") or t.startswith(">"):
        num = NUM_RE.search(t)
        val = float(num.group().replace(",", "")) if num else np.nan
        flags.add("lt" if t.startswith("<") else "gt")
        return (val, np.nan, np.nan, val if t.startswith("<") else np.nan, unit_suffix, flags)

    range_m = re.fullmatch(r"([\d,]*\.?\d+)\s*(?:-|–|~|—|to)\s*([\d,]*\.?\d+)\s*[a-zA-Z]?", t)
    if range_m:
        lo = float(range_m.group(1).replace(",", ""))
        hi = float(range_m.group(2).replace(",", ""))
        flags.add("range")
        return ((lo + hi) / 2.0, (hi - lo) / 2.0, lo, hi, unit_suffix, flags)

    if "±" in t or "+-" in t:
        parts = re.split(r"±|\+-", t, maxsplit=1)
        mean_s = parts[0].strip()
        sd_s = parts[1].strip() if len(parts) > 1 else ""
        sup = r"[a-zA-Z\u2070-\u209f\u1d43-\u1dbf]+$"
        if re.search(r"[a-zA-Z\u2070-\u209f]", t):
            flags.add("signif_letter")
        mean_s = re.sub(sup, "", mean_s).strip()
        sd_s = re.sub(sup, "", sd_s).strip()
        return (_num(mean_s, flags), _num(sd_s, flags), np.nan, np.nan, unit_suffix, flags)

    if re.search(r"[a-zA-Z\u2070-\u209f]", t.rstrip("0123456789.")):
        flags.add("signif_letter")
    t2 = re.sub(r"[a-zA-Z\u2070-\u209f\u1d43-\u1dbf]+$", "", t).strip()
    return (_num(t2 or t, flags), np.nan, np.nan, np.nan, unit_suffix, flags)


# ---------------------------------------------------------------------------
# unit handling — everything is converted to μg/L
# ---------------------------------------------------------------------------
UNIT_FACTORS = {          # multiply value by factor -> μg/L
    "ug/l": 1.0,
    "μg/l": 1.0,
    "ug/ml": 1e3,
    "μg/ml": 1e3,
    "ug/ml_": 1e3,
    "mg/l": 1e3,
    "mg/ml": 1e6,
    "g/l": 1e6,
    "mg/100ml": 1e4,
    "mg/100g": 1e4,
    "%(v/v)": np.nan,
}


def norm_unit(u: str) -> str:
    t = s(u).lower()
    t = t.replace("μ", "u").replace("µ", "u").replace("·", "/").replace(" ", "")
    t = t.replace("ug/l", "ug/l").replace("mg/100ml", "mg/100ml")
    t = t.replace("mg/l", "mg/l").replace("mg/ml", "mg/ml").replace("g/l", "g/l")
    t = t.replace("g/100ml", "mg/100ml")
    t = t.replace("mgl-1", "mg/l").replace("ugl-1", "ug/l")
    t = t.replace("mgl⁻¹", "mg/l").replace("ugl⁻¹", "ug/l")
    t = t.replace("/(", "/").replace(")", "")
    return t.strip("/")


def to_ug_per_l(value: float, unit: str):
    """Convert a concentration to μg/L.  Returns (value, ok)."""
    f = UNIT_FACTORS.get(norm_unit(unit))
    if f is None or (isinstance(f, float) and np.isnan(f)) or value is None or (
        isinstance(value, float) and np.isnan(value)
    ):
        return (np.nan, False)
    return (float(value) * f, True)


# ---------------------------------------------------------------------------
# CAS registry-number utilities
# ---------------------------------------------------------------------------
def cas_digits(cas: str) -> str:
    return re.sub(r"\D", "", s(cas))


def cas_ok(cas: str) -> bool:
    """Validate the CAS check digit."""
    d = cas_digits(cas)
    if not (5 <= len(d) <= 10):
        return False
    body, chk = d[:-1], int(d[-1])
    total = sum(int(x) * (len(body) - i) for i, x in enumerate(body))
    return total % 10 == chk


def cas_format(digits: str) -> str:
    d = re.sub(r"\D", "", s(digits))
    if len(d) < 5:
        return d
    return f"{d[:-3]}-{d[-3:-1]}-{d[-1]}"


def cas_candidates(cas: str, max_insert: int = 3, max_len: int = 10):
    """
    Generate checksum-valid candidate repairs for a corrupted CAS.

    The dominant corruption in this workbook is *deleted zeros* (and Excel
    date coercion), so we search over re-insertion of '0' at every position,
    plus simple digit-prefix additions.
    """
    base = cas_digits(cas)
    out = []
    # 1) insert zeros
    frontier = {base}
    for _ in range(max_insert):
        nxt = set()
        for t in frontier:
            for i in range(len(t) + 1):
                nxt.add(t[:i] + "0" + t[i:])
        frontier = nxt
        for t in frontier:
            if len(t) <= max_len and cas_ok(t):
                out.append(cas_format(t))
    # 2) prepend digits (lost leading digits)
    for p in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"):
        t = p + base
        if len(t) <= max_len and cas_ok(t):
            out.append(cas_format(t))
    # 3) replace separators with dash and retry the zero search already covered
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


# ---------------------------------------------------------------------------
# chemical class assignment
# ---------------------------------------------------------------------------
CLASS_RULES = [
    ("硫化物 Sulfur", lambda n, sm: ("sulfid" in n or "disulfide" in n or "trisulfide" in n
                                     or "methional" in n or "thiazole" in n or "thiol" in n)),
    ("吡嗪 Pyrazine", lambda n, sm: "pyrazine" in n),
    ("酚类 Phenol", lambda n, sm: "phenol" in n or "cresol" in n or "guaiacol" in n),
    ("内酯 Lactone", lambda n, sm: "lactone" in n),
    ("呋喃 Furan", lambda n, sm: "furan" in n or "furfural" in n or "furfuryl" in n),
    ("酸类 Acid", lambda n, sm: "acid" in n or re.search(r"C\(=O\)O[H]$", sm or "") is not None),
    ("酯类 Ester", lambda n, sm: "ate" in n.split()[-1] if n.split() else False),
    ("酯类 Ester", lambda n, sm: re.search(r"C\(=O\)O[^H]", sm or "") is not None),
    ("醇类 Alcohol", lambda n, sm: "ol" in n.split()[-1] if n.split() else False),
    ("醇类 Alcohol", lambda n, sm: re.search(r"(?<![=O])O[H]$", sm or "") is not None),
    ("醛类 Aldehyde", lambda n, sm: "aldehyde" in n or "al" in n.split()[-1] if n.split() else False),
    ("醛类 Aldehyde", lambda n, sm: re.search(r"[^O]=O$", sm or "") is not None and "C=O" in (sm or "")),
    ("酮类 Ketone", lambda n, sm: "one" in n.split()[-1] if n.split() else False),
    ("酮类 Ketone", lambda n, sm: re.search(r"C\(=O\)C", sm or "") is not None),
]

# manual overrides — authoritative for the master library's 62 compounds
CLASS_OVERRIDE = {
    "ethyl hexanoate": "酯类 Ester", "ethyl isovalerate": "酯类 Ester",
    "ethyl butyrate": "酯类 Ester", "ethyl acetate": "酯类 Ester",
    "ethyl caprylate": "酯类 Ester", "ethyl valerate": "酯类 Ester",
    "ethyl heptanoate": "酯类 Ester", "ethyl lactate": "酯类 Ester",
    "ethyl 2-hydroxy-4-methylvalerate": "酯类 Ester",
    "ethyl 4-methylvalerate": "酯类 Ester", "(e)-2-octenal": "醛类 Aldehyde",
    "isoamyl hexanoate": "酯类 Ester", "methyl hexanoate": "酯类 Ester",
    "hexyl hexanoate": "酯类 Ester", "butyl hexanoate": "酯类 Ester",
    "ethyl 3-phenylpropionate": "酯类 Ester", "ethyl phenylacetate": "酯类 Ester",
    "isoamyl acetate": "酯类 Ester", "ethyl palmitate": "酯类 Ester",
    "isoamyl butyrate": "酯类 Ester", "1-butanol": "醇类 Alcohol",
    "1-hexanol": "醇类 Alcohol", "3-methyl-1-butanol": "醇类 Alcohol",
    "1-octen-3-ol": "醇类 Alcohol", "1-octanol": "醇类 Alcohol",
    "1-propanol": "醇类 Alcohol", "isobutanol": "醇类 Alcohol",
    "hexanoic acid": "酸类 Acid", "2-methylpropionic acid": "酸类 Acid",
    "valeric acid": "酸类 Acid", "octanoic acid": "酸类 Acid",
    "heptanoic acid": "酸类 Acid", "butyric acid": "酸类 Acid",
    "acetic acid": "酸类 Acid", "4-methylvaleric acid": "酸类 Acid",
    "isovaleric acid": "酸类 Acid", "phenylacetaldehyde": "醛类 Aldehyde",
    "acetaldehyde": "醛类 Aldehyde", "furfural": "醛类 Aldehyde",
    "acetal": "醛类 Aldehyde", "acetoin": "酮类 Ketone", "2-heptanone": "酮类 Ketone",
    "dimethyl trisulfide": "硫化物 Sulfur", "2-(ethoxymethyl)furan": "呋喃 Furan",
    "4-ethyl-2-methoxyphenol": "酚类 Phenol", "2-methoxy-4-methylphenol": "酚类 Phenol",
    "gamma-nonanolactone": "内酯 Lactone", "furfuryl alcohol": "呋喃 Furan",
    "butyl acetate": "酯类 Ester", "ethyl isobutyrate": "酯类 Ester",
    "ethyl 2-methylbutanoate": "酯类 Ester", "p-cresol": "酚类 Phenol",
    "phenethyl acetate": "酯类 Ester", "3-phenylpropionic acid": "酸类 Acid",
    "propionic acid": "酸类 Acid", "isovaleraldehyde": "醛类 Aldehyde",
    "hexanal": "醛类 Aldehyde", "trimethylpyrazine": "吡嗪 Pyrazine",
    "hexyl acetate": "酯类 Ester", "ethyl decanoate": "酯类 Ester",
    "ethyl nonanoate": "酯类 Ester", "hexyl butanoate": "酯类 Ester",
}


def chem_class(name_en: str, smiles: str = "") -> str:
    key = norm_key(name_en)
    if key in CLASS_OVERRIDE:
        return CLASS_OVERRIDE[key]
    for label, fn in CLASS_RULES:
        try:
            if fn(key, s(smiles)):
                return label
        except Exception:
            continue
    return "其他 Other"


# ---------------------------------------------------------------------------
# master-library column-header parsing
# ---------------------------------------------------------------------------
PAPER_NO_RE = re.compile(r"^\s*(\d{1,2})\b(?![\d%.,])")


def parse_data_column(header: str):
    """
    '5  S1 (mg/L)'            -> (5, 'S1', 'mg/L', 'S1')
    'LZ-2016 base SAB (Mean ± SD)' -> (nan, 'LZ-2016 base SAB', '', ...)
    'Y1（μg/L）'               -> (nan, 'Y1', 'μg/L', ...)
    '12 JZG-1 μg/L'           -> (12, 'JZG-1', 'μg/L', ...)
    '41% TZL'                 -> (nan, '% TZL', '', ...)   (not study 41)
    """
    h = s(header)
    # unit
    unit = ""
    um = re.search(
        r"[（(]\s*([μu]g|[mM]g|[gG])\s*[/·]?\s*(mL|ml|L|l|100mL|100ml)\s*[)）]", h
    )
    if um:
        unit = f"{um.group(1)}/{um.group(2)}"
    else:
        um2 = re.search(r"([μu]g/mL|[μu]g/L|[mM]g/mL|[mM]g/L|[gG]/L|mg/100mL|mg/100ml)", h)
        if um2:
            unit = um2.group(1)
    # paper number
    pm = PAPER_NO_RE.match(h)
    paper = int(pm.group(1)) if pm and int(pm.group(1)) <= 33 else np.nan
    # labels such as '3 年陈' are sample names, not study numbers
    if paper == paper and re.fullmatch(r"\d{1,2}\s*年陈", h):
        paper = np.nan
    rest = h[pm.end():] if (pm and paper == paper) else h
    rest = re.sub(r"[（(][^）)]*[)）]", " ", rest)       # drop parenthetical unit
    rest = re.sub(r"(?i)\b[μu]g/mL|[μu]g/L|mg/mL|mg/L|g/L|mg/100mL|mg/100ml\b", " ", rest)
    rest = re.sub(r"^(Mean\s*±\s*SD)\s*", "", rest.strip())
    rest = re.sub(r"\s+", " ", rest).strip(" -_")
    return paper, rest, unit, h
