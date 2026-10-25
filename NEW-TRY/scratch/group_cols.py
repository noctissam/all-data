# -*- coding: utf-8 -*-
"""Group the unitless / text concentration columns by what the column actually is."""
import collections
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
rows = [l.rstrip("\n") for l in open("out/re整理/verify_values.txt", encoding="utf-8")]

PAT = re.compile(r"(?:无单位列|文本值)\s+(?P<sheet>\d{2})\s+\S.*?"
                 r"(?:浓度|阈值|OAV\S*)\s+(?P<col>.+?)\s{2,}(?P<rest>.+)$")

buckets = collections.Counter()
detail = collections.defaultdict(list)

RULES = [
    ("通用列号", re.compile(r"^列\d+$")),
    ("样品代号", re.compile(r"^[A-Za-z]{1,3}[-–]?\d{2,4}$|^n-[a-z]-\d+$|^[A-Z]{1,3}\d?$")),
    ("中文样品名", re.compile(r"[一-鿿]")),
    ("比例/指数类", re.compile(r"[Rr]atio|比例|量比|占比|指数|含量\s*%|贡献率")),
    ("保留指数", re.compile(r"^[LlRr]?[RrIi]\w*$|RI")),
]

for line in rows:
    if "无单位列" not in line and "文本值" not in line:
        continue
    m = PAT.search(line)
    if not m:
        continue
    col = m.group("col").strip()
    kind = "其它"
    for name, rx in RULES:
        if rx.search(col):
            kind = name
            break
    else:
        if re.search(r"[一-鿿]", col):
            kind = "中文样品名"
    n = re.search(r"(\d+)\s*个值", line)
    buckets[kind] += int(n.group(1)) if n else 1
    detail[kind].append("%s | %s" % (m.group("sheet"), col))

print("按列的性质分组（行数）")
for k, v in buckets.most_common():
    print("  %-14s %4d 行   例: %s" % (k, v, "; ".join(detail[k][:4])))
print()
print("合计 %d 条" % sum(buckets.values()))