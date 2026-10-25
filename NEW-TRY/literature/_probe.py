# -*- coding: utf-8 -*-
"""Probe one PMC article: what structured data is available (XML tables, supplementary files)."""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

path = sys.argv[1]
x = open(path, encoding="utf-8").read()

print("xml length:", len(x))
print("title:", re.sub(r"<[^>]+>", "", (re.search(r"<article-title>(.*?)</article-title>", x, re.S) or
                                         re.match("", "")).group(1))[:110] if re.search(r"<article-title>", x, re.S) else "?")
print("table-wrap:", x.count("<table-wrap"))
print("supplementary-material:", x.count("<supplementary-material"))

for m in re.finditer(r"<supplementary-material[^>]*>(.*?)</supplementary-material>", x, re.S):
    s = m.group(1)
    hrefs = re.findall(r'xlink:href="([^"]+)"', s)
    txt = re.sub(r"<[^>]+>", " ", " ".join(re.findall(r"<p>(.*?)</p>", s, re.S)))
    print("  SUPP", hrefs)
    print("       ", re.sub(r"\s+", " ", txt).strip()[:150])

print("--- tables ---")
for m in re.finditer(r"<table-wrap([^>]*)>(.*?)</table-wrap>", x, re.S):
    attrs, body = m.group(1), m.group(2)
    tid = re.search(r'id="([^"]+)"', attrs)
    cap = re.search(r"<caption>(.*?)</caption>", body, re.S)
    capt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cap.group(1))).strip() if cap else ""
    nrows = body.count("<tr")
    graphics = body.count("<graphic")
    print("  id=%-14s rows=%-4d graphics=%d  %s" % (tid.group(1) if tid else "?", nrows, graphics, capt[:100]))

print("--- first table, first 6 rows ---")
m = re.search(r"<table-wrap.*?</table-wrap>", x, re.S)
if m:
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S)[:6]:
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        print("   ", cells)
