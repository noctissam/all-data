# -*- coding: utf-8 -*-
"""
10_extract_sources.py
=====================
Step 1 of the cleaning pipeline.

Reads `data总库.xlsx` (the master library, READ ONLY) and flattens every
worksheet into a tidy long table:

    sheet_tab | row_no | block | item_no | compound_raw | cas_raw | unit_hint |
    threshold_raw | sample_label | value_raw

The sheet tabs of the master library are messy literature extractions: several
of them hold *two or three independent tables side by side* (separated by blank
columns) with their own headers, sometimes a second header row.  We therefore
detect repeated header rows and blank-column separators and split each physical
sheet into logical "blocks".

Nothing is written back to the source workbook.  All artefacts land in ./output.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

import numpy as np
import pandas as pd
import openpyxl

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "output")
TIDY = os.path.join(OUT, "tidy")
os.makedirs(TIDY, exist_ok=True)

MASTER = os.path.join(SRC, "data总库.xlsx")
SIBLING = os.path.join(SRC, "data.xlsx")
SKIP_TABS = {"all data", "Sheet9"}

# --------------------------------------------------------------------------
# generic helpers
# --------------------------------------------------------------------------
DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"), "-")


def norm_dash(s: str) -> str:
    return s.translate(DASHES)


def s(x) -> str:
    """Cell -> clean string ('' for None)."""
    if x is None:
        return ""
    if isinstance(x, float) and np.isnan(x):
        return ""
    if isinstance(x, (pd.Timestamp,)):
        return x.isoformat(sep=" ")
    return norm_dash(str(x)).replace("\u200b", "").replace("\xa0", " ").strip()


def looks_numeric(tok: str) -> bool:
    t = tok.replace(",", "").replace(" ", "")
    return bool(re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", t))


NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?")

# tokens that mark "not quantified"
MISSING_TOKENS = {
    "nf", "nd", "n.d", "n.d.", "n/d", "-", "--", "---", "—", "–", "\\", "/", "(空)",
    "空", "", "na", "n/a", "nan", "none", "未检出", "未测", "tr", "trace", "·",
}


def token_is_missing(tok: str) -> bool:
    return tok.strip().lower().replace(" ", "") in MISSING_TOKENS


def parse_measure(raw):
    """
    Parse one literature cell into numeric mean / sd plus quality flags.

    Handles:  1234 | 1234.5 | "7,606,936 ± 17,161" | "5320.56 ± 47.54b"
              "200-316a" | "824.84 ~ 1237.73" | "<1" | ">2" | "NF" | "ND"
              "—" | "\\" | "(空)" | "873,258 ± 9159 μg/l"
    Returns (mean, sd, lo, hi, unit_suffix, flags:set)
    """
    flags = set()
    t = s(raw)
    if t == "":
        return (np.nan, np.nan, np.nan, np.nan, "", {"empty"})
    if token_is_missing(t):
        return (np.nan, np.nan, np.nan, np.nan, "", {"missing_code"})

    # split off a trailing unit like ug/l, μg/L, mg/L
    unit_suffix = ""
    m = re.search(r"([μu]g\s*/?\s*[lL]|mg\s*/?\s*[lL]|g\s*/?\s*[lL])\s*$", t)
    if m:
        unit_suffix = m.group(1)
        t = t[: m.start()].strip()

    # inequality
    if t.startswith("<") or t.startswith(">"):
        num = NUM_RE.search(t)
        val = float(num.group().replace(",", "")) if num else np.nan
        flags.add("lt" if t.startswith("<") else "gt")
        return (val, np.nan, np.nan, val if t.startswith("<") else np.nan, unit_suffix, flags)

    # range forms:  200-316  /  824.84 ~ 1237.73  /  4.24-5.2-13.67
    range_m = re.fullmatch(
        r"([\d,]*\.?\d+)\s*(?:-|–|~|—|to)\s*([\d,]*\.?\d+)\s*[a-zA-Z]?", t
    )
    if range_m:
        lo = float(range_m.group(1).replace(",", ""))
        hi = float(range_m.group(2).replace(",", ""))
        flags.add("range")
        return ((lo + hi) / 2.0, (hi - lo) / 2.0, lo, hi, unit_suffix, flags)

    # mean ± sd  (also "±.62", "± 0. 2")
    if "±" in t or "+-" in t:
        parts = re.split(r"±|\+-", t, maxsplit=1)
        mean_s = parts[0].strip()
        sd_s = parts[1].strip() if len(parts) > 1 else ""
        # strip significance letters / trailing junk
        mean_s = re.sub(r"[a-zA-Z\u2070-\u209f\u1d43-\u1dbf]+$", "", mean_s).strip()
        sd_s = re.sub(r"[a-zA-Z\u2070-\u209f\u1d43-\u1dbf]+$", "", sd_s).strip()
        mean = _num(mean_s, flags)
        sd = _num(sd_s, flags)
        if t != mean_s and re.search(r"[a-zA-Z]", t):
            flags.add("signif_letter")
        return (mean, sd, np.nan, np.nan, unit_suffix, flags)

    mean = _num(t, flags)
    return (mean, np.nan, np.nan, np.nan, unit_suffix, flags)


def _num(t: str, flags: set) -> float:
    """Single number, guarding against the destroyed-thousands-separator bug."""
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
        # a thousands-separated integer must have 3-digit groups after the first
        if any(len(g) != 3 for g in groups[1:]):
            flags.add("corrupt_thousands_sep")
            raw = groups[0]
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        flags.add("unparsed")
        return np.nan


# --------------------------------------------------------------------------
# header detection / block splitting
# --------------------------------------------------------------------------
# substring hints (a column label containing one of these is a label, not data)
SUB_HINTS = (
    "compound", "compounds", "化合物", "物质", "名称", "cas", "风味", "香气", "odorant",
    "flavor", "flavour", "component", "zone", "category", "种类", "样品", "analyte",
    "阈值", "threshold", "content", "含量", "浓度", "concentration", "quantif",
    "描述", "特征", "鉴定依据", "内标", "标准顺序", "编号", "region", "产区", "等级",
    "年陈", "酒", "组", "样品名", "名称（", "峰",
)
# exact-match hints
EXACT_HINTS = {
    "no.", "no", "no.⁺", "id", "ri", "code", "#", "name", "sample", "item",
    "序号", "编号", "序号⁺", "化合物", "物质", "风味物质",
}

# a *measurement* cell: optional inequality, number, optional ± sd, optional unit,
# optional significance letter(s), optionally a range.
MEAS_RE = re.compile(
    r"^\s*[<>]?\s*\d[\d,]*(?:\.\d+)?\s*"
    r"(?:[-–~]\s*\d[\d,]*(?:\.\d+)?\s*[a-zA-Z\u2070-\u209f]*)?\s*"
    r"(?:[±]\s*\d*\.?\d*\s*[a-zA-Z\u2070-\u209f]*)?\s*"
    r"(?:[μu]g|[mM]g|[gG])?\s*/?\s*(?:[lL]|mL|100mL)?\s*[a-zA-Z\u2070-\u209f]*\s*$"
)


def is_measurement(txt: str) -> bool:
    """True when a cell holds a number/measurement rather than a label."""
    t = txt.strip()
    if t == "":
        return False
    if not any(ch.isdigit() for ch in t):
        return False
    if re.fullmatch(r"\d+\s+\d+", t):  # e.g. the column label '10  2'
        return False
    if re.fullmatch(r"\d+\s*[a-zA-Z]", t):  # e.g. '4 年陈' style short labels
        return False
    return bool(MEAS_RE.match(t))


def is_header_row(row) -> bool:
    vals = [s(c) for c in row]
    nonempty = [v for v in vals if v]
    if len(nonempty) < 2:
        return False
    return not any(is_measurement(v) for v in nonempty)


def n_measurements(row) -> int:
    return sum(1 for c in row if is_measurement(s(c)))


def header_hits(row) -> int:
    vals = [s(c) for c in row if s(c)]
    n = 0
    for v in vals:
        low = v.lower()
        if low in EXACT_HINTS or any(h in low for h in SUB_HINTS):
            n += 1
    return n


def find_blocks(ws):
    """Split a worksheet into (header_rows, data_rows, col_slice) blocks."""
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    if not rows:
        return []
    width = max((len(r) for r in rows), default=0)
    for r in rows:
        r.extend([None] * (width - len(r)))

    used_cols = [c for c in range(width) if any(s(r[c]) for r in rows)]
    if not used_cols:
        return []
    # a column is a "separator" if it is empty in every row
    sep = [c for c in range(width) if c not in used_cols]

    # contiguous runs of used columns, cut at separator columns
    runs, start = [], used_cols[0]
    for a, b in zip(used_cols, used_cols[1:]):
        if b != a + 1:
            runs.append((start, a))
            start = b
    runs.append((start, used_cols[-1]))

    blocks = []
    for c0, c1 in runs:
        sub = [r[c0 : c1 + 1] for r in rows]
        # candidate header rows: label-like row immediately followed by data
        hdr_idx = []
        for i in range(len(sub) - 1):
            if not is_header_row(sub[i]):
                continue
            if n_measurements(sub[i + 1]) >= 2 and header_hits(sub[i]) >= 1:
                hdr_idx.append(i)
            elif is_header_row(sub[i + 1]) and header_hits(sub[i]) >= 1 \
                    and i + 2 < len(sub) and n_measurements(sub[i + 2]) >= 2:
                hdr_idx.append(i)  # two-row header
        if not hdr_idx:
            continue
        for k, hi in enumerate(hdr_idx):
            nxt = hdr_idx[k + 1] if k + 1 < len(hdr_idx) else len(sub)
            hdr_rows = [hi]
            # fold a second header row (sub-labels such as A / B / C)
            if hi + 1 < nxt and is_header_row(sub[hi + 1]) and n_measurements(sub[hi + 1]) == 0 \
                    and any(s(c) for c in sub[hi + 1]):
                hdr_rows.append(hi + 1)
            data_start = hdr_rows[-1] + 1
            data = [sub[i] for i in range(data_start, nxt) if any(s(c) for c in sub[i])]
            if data:
                blocks.append(
                    {
                        "cols": (c0, c1),
                        "header_rows": [sub[i] for i in hdr_rows],
                        "data": data,
                        "header_row_no": [i + 1 for i in hdr_rows],
                    }
                )
    return blocks


# --------------------------------------------------------------------------
# block -> tidy frame
# --------------------------------------------------------------------------
NAME_KEYS = ("compound", "compounds", "化合物", "物质", "名称", "odorant", "flavor", "风味物质", "香气物质", "香气")
CAS_KEYS = ("cas",)
ID_KEYS = ("no.", "序号", "id", "code", "编号")
THR_KEYS = ("threshold", "阈值", "odour threshold", "odor threshold", "outer threshold")
UNIT_KEYS = ("mg/l", "μg/l", "ug/l", "mg/ml", "g/l", "mg/100ml", "mg·l", "μg·l")
CAT_KEYS = ("category", "种类", "类型", "class", "group")
TEXT_KEYS = ("特征", "描述", "鉴定依据", "内标", "quantified ion", "香味", "气味", "参考", "notes", "备注", "标准顺序")


def col_role(header_text: str) -> str:
    h = header_text.lower()
    if any(k in h for k in CAS_KEYS):
        return "cas"
    if "oav" in h:
        return "oav"
    if any(k in h for k in THR_KEYS):
        return "threshold"
    if any(k in h for k in TEXT_KEYS):
        return "text"
    if any(k in h for k in CAT_KEYS):
        return "category"
    if any(k in h for k in NAME_KEYS):
        return "compound"
    if any(k in h for k in ID_KEYS):
        return "item_no"
    # a header that is *only* a unit, e.g. '(μg/L)', is a threshold column
    stripped = re.sub(
        r"[（(]?\s*[μu]?[mM]?[gG]\s*[/·]?\s*(?:mL|ml|L|l|100mL|100ml)\s*[)）]?",
        "", h,
    )
    if stripped.strip(" .-–—_") == "" and h.strip():
        return "threshold"
    return "value"


def flatten_block(block, sheet_name, block_no):
    hdr = block["header_rows"]
    ncol = len(hdr[0])
    # build a combined header label per column
    labels = []
    for c in range(ncol):
        parts = [s(h[c]) for h in hdr if c < len(h)]
        parts = [p for p in parts if p]
        labels.append(" ".join(dict.fromkeys(parts)))
    roles = [col_role(l) for l in labels]
    # if a column looks like a name column but holds only a category word, keep as-is

    recs = []
    last_name, last_cas = "", ""
    for ri, row in enumerate(block["data"]):
        name_val, cas_val = "", ""
        for c in range(ncol):
            if roles[c] == "compound" and not name_val:
                name_val = s(row[c])
            if roles[c] == "cas" and not cas_val:
                cas_val = s(row[c])
        # forward-fill merged compound cells, then drop rows with no compound
        if name_val:
            last_name, last_cas = name_val, cas_val or last_cas
        else:
            name_val = last_name
            cas_val = cas_val or last_cas
        if not name_val or name_val.lower() in {"nan", "none"}:
            continue
        for c in range(ncol):
            if roles[c] not in ("value", "threshold", "oav"):
                continue
            raw = s(row[c])
            if raw == "":
                continue
            if not any(ch.isdigit() for ch in raw) and not token_is_missing(raw):
                continue  # stray label such as A / B / C in a sub-header row
            mean, sd, lo, hi, usuf, flags = parse_measure(raw)
            recs.append(
                {
                    "source_workbook": "data总库.xlsx",
                    "sheet_tab": sheet_name,
                    "block_no": block_no,
                    "col_index": block["cols"][0] + c,
                    "column_header": labels[c],
                    "role": roles[c],
                    "compound_raw": name_val,
                    "cas_raw": cas_val,
                    "item_no": next(
                        (s(row[i]) for i in range(ncol) if roles[i] == "item_no"), ""
                    ),
                    "category_raw": next(
                        (s(row[i]) for i in range(ncol) if roles[i] == "category"), ""
                    ),
                    "value_raw": raw,
                    "value_mean": mean,
                    "value_sd": sd,
                    "value_lo": lo,
                    "value_hi": hi,
                    "unit_suffix": usuf,
                    "flags": "|".join(sorted(flags)),
                    "row_no_in_block": ri + 1,
                }
            )
    return recs


def main():
    wb = openpyxl.load_workbook(MASTER, read_only=True, data_only=True)
    all_recs = []
    summary = []
    tabs = list(wb.sheetnames)
    for tab in tabs:
        ws = wb[tab]
        if tab in SKIP_TABS or (ws.max_row <= 1 and ws.max_column <= 1):
            summary.append((tab, 0, 0))
            continue
        blocks = find_blocks(ws)
        n = 0
        for bi, blk in enumerate(blocks, start=1):
            recs = flatten_block(blk, tab, bi)
            all_recs.extend(recs)
            n += len(recs)
            pd.DataFrame(blk["data"]).to_csv(
                os.path.join(TIDY, f"raw__{re.sub(r'[^0-9A-Za-z]+', '_', tab)[:40]}__b{bi}.csv"),
                index=False, header=False, encoding="utf-8-sig",
            )
        summary.append((tab, len(blocks), n))
    wb.close()

    long = pd.DataFrame(all_recs)
    long.to_csv(os.path.join(OUT, "sheets_long.csv"), index=False, encoding="utf-8-sig")

    rep = ["# data总库.xlsx — sheet tab block extraction", ""]
    rep.append(f"{'sheet tab':<42} {'blocks':>6} {'value cells':>12}")
    for tab, nb, n in summary:
        rep.append(f"{tab:<42} {nb:>6} {n:>12}")
    rep.append("")
    rep.append(f"TOTAL logical tables (blocks): {sum(x[1] for x in summary)}")
    rep.append(f"TOTAL parsed value cells     : {len(long)}")
    rep.append("")
    rep.append("## flag frequency")
    for f, c in long["flags"].str.split("|").explode().value_counts().items():
        rep.append(f"  {(f or '<parsed clean>'):<26} {c}")
    rep.append("")
    rep.append("## blocks detected per sheet")
    for tab in sorted(set(long["sheet_tab"])):
        sub = long[long["sheet_tab"] == tab]
        for b in sorted(sub["block_no"].unique()):
            sb = sub[sub["block_no"] == b]
            rep.append(
                f"  {tab:<40} block {b}: {sb['compound_raw'].nunique():>3} compounds, "
                f"{sb['column_header'].nunique():>3} value columns, {len(sb):>4} cells"
            )
    with open(os.path.join(OUT, "report_sheets_extraction.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(rep))
    print("\n".join(rep))
    print(f"\n-> {OUT}\\sheets_long.csv  ({len(long)} rows)")


if __name__ == "__main__":
    main()
