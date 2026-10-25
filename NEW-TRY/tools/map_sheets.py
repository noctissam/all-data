# -*- coding: utf-8 -*-
"""
Map data.xlsx sheets to the PDFs on disk, and profile every PDF.

Sheet order is the contract: sheets 2-12 are the English papers, 13-35 the Chinese
ones numbered continuing from the English count. Nothing is read from the sheets'
contents - only the sheet names, to know WHICH paper each slot means.

Profiling decides the extraction route per paper:
  text_chars   plenty           -> the PDF has a real text layer, parse it
  rules>0      vector drawings  -> three-line tables are detectable geometrically
  raster pages                  -> image pipeline (cn_detect_tables.py)
"""
import os
import re
import sys

import openpyxl
import pymupdf

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EN_DIR = os.path.join(ROOT, "定性定量")
CN_DIR = os.path.join(ROOT, "寒假中文文献")
DATA = os.path.join(ROOT, "data.xlsx")

STOP = set("the of and in a for with on by to from based study analysis using "
           "characterization exploration key aroma compounds volatile".split())


def squash(s):
    """Collapse to a bare comparable string: lowercase, alnum + CJK only."""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", s.lower())


def norm_tokens(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    toks = [t for t in s.split() if t and t not in STOP]
    return toks


def match_score(sheet_title, pdf_stem):
    """
    Sheet names are TRUNCATED versions of the PDF file names, so prefix containment is
    the right test. Token overlap is not: "Characterization of key odor" shares only
    {characterization, key} with the real file but scores higher against
    "Characterization of the cellar mud odor compounds", which is a different paper.
    """
    a, b = squash(sheet_title), squash(pdf_stem)
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    for k in range(n, 7, -1):
        if a[:k] == b[:k]:
            return 0.60 + 0.40 * k / max(len(b), 1)
    return 0.0


def pdf_stem(fn):
    """Strip the leading order number and the author suffix from a PDF file name."""
    base = os.path.splitext(fn)[0]
    base = re.sub(r"^\s*(不可用|\d+)\s+", "", base)
    base = re.sub(r"_\s*[^_]{1,6}\s*$", "", base)      # trailing _张恩 style author
    return base.strip()


def sheet_key(name):
    """Leading order number + the title text of a sheet name."""
    m = re.match(r"^\s*(\d+)\s*(.*)$", name)
    if m:
        return m.group(1), m.group(2).strip()
    return "", name.strip()


def profile(path):
    try:
        d = pymupdf.open(path)
    except Exception as e:
        return dict(pages=0, text=0, rules=0, images=0, route="UNREADABLE", err=str(e)[:60])
    pages, text, rules, imgs = d.page_count, 0, 0, 0
    for p in d:
        text += len(p.get_text().strip())
        rules += sum(1 for x in p.get_drawings() if x["rect"].width > 120 and x["rect"].height < 4)
        imgs += len(p.get_images())
    n = d.page_count
    d.close()
    if text > 200 * n:
        route = "text-layer"
    elif rules > 3 * n:
        route = "vector-tables"
    else:
        route = "raster-tables"
    return dict(pages=n, text=text, rules=rules, images=imgs, route=route)


def main():
    wb = openpyxl.load_workbook(DATA, read_only=True)
    sheets = wb.sheetnames[1:]
    wb.close()

    # keyed by stem, but stems are NOT unique - two files differ only in leading
    # whitespace, and collapsing them silently dropped one of the 17
    en_pdfs, cn_pdfs = {}, {}
    for f in os.listdir(EN_DIR):
        if f.lower().endswith(".pdf"):
            en_pdfs.setdefault(pdf_stem(f), []).append(f)
    for f in os.listdir(CN_DIR):
        if f.lower().endswith(".pdf"):
            cn_pdfs.setdefault(pdf_stem(f), []).append(f)
    en_files = [f for v in en_pdfs.values() for f in v]
    cn_files = [f for v in cn_pdfs.values() for f in v]

    print("data.xlsx 文献表单 %d 个；英文 PDF %d，中文 PDF %d"
          % (len(sheets), len(en_files), len(cn_files)))
    print()

    rows, used = [], set()
    for i, sn in enumerate(sheets, 1):
        num, title = sheet_key(sn)
        is_cn = bool(re.search(r"[\u4e00-\u9fff]", title)) or (not num and i > 12)
        pool = cn_pdfs if is_cn else en_pdfs
        ranked = sorted(((match_score(title, stem), fn)
                         for stem, fns in pool.items() for fn in fns),
                        key=lambda z: -z[0])
        score, best = (ranked[0] if ranked else (0.0, None))
        hit = best if score >= 0.60 else None
        if hit:
            used.add(hit)
        rows.append((i, sn, title, hit, round(score, 2), is_cn))

    print("%-4s %-56s %-8s %s" % ("#", "sheet", "match", "pdf"))
    for i, sn, title, hit, sc, is_cn in rows:
        print("%-4d %-56s %-8s %s" % (i, sn[:56], ("%.2f" % sc) if hit else "--", hit or "*** 未匹配 ***"))

    print()
    unmatched_en = [f for f in en_files if f not in used]
    unmatched_cn = [f for f in cn_files if f not in used]
    print("磁盘上有、表单里没有的 PDF：")
    for f in sorted(unmatched_en):
        print("   [英文] %s" % f)
    for f in sorted(unmatched_cn):
        print("   [中文] %s" % f)

    print()
    print("PDF 形态画像（决定每篇走哪条提取路径）：")
    print("%-4s %-5s %-8s %-6s %-6s %-9s %s"
          % ("#", "页", "字符/页", "横线", "图片", "路径", "文件"))
    n_route = {}
    for i, sn, title, hit, sc, is_cn in rows:
        if not hit:
            continue
        d = CN_DIR if is_cn else EN_DIR
        pf = profile(os.path.join(d, hit))
        n_route[pf["route"]] = n_route.get(pf["route"], 0) + 1
        print("%-4d %-5d %-8.0f %-6d %-6d %-9s %s" % (
            i, pf["pages"], pf["text"] / max(pf["pages"], 1), pf["rules"],
            pf["images"], pf["route"], hit[:48]))
    print()
    print("路径分布：" + "  ".join("%s=%d" % kv for kv in sorted(n_route.items())))

    out = os.path.join(ROOT, "NEW-TRY", "out", "re整理")
    os.makedirs(out, exist_ok=True)
    import json
    rec = []
    for i, sn, title, hit, sc, is_cn in rows:
        d = CN_DIR if is_cn else EN_DIR
        pf = profile(os.path.join(d, hit)) if hit else {}
        rec.append(dict(idx=i, sheet=sn, title=title, lang="cn" if is_cn else "en",
                        pdf=hit, path=os.path.join(d, hit) if hit else None,
                        match=sc, **pf))
    with open(os.path.join(out, "sheet_map.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    print("映射 -> %s" % os.path.join("NEW-TRY", "out", "re整理", "sheet_map.json"))


if __name__ == "__main__":
    main()
