# -*- coding: utf-8 -*-
"""Check the scale-factor pattern against the strings the PDF actually yields."""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

PAT = re.compile(r"^[（(]?\s*×\s*10[^)）]*[)）]?$")
print("pattern:", PAT.pattern)
for s in ["（×10-2）", "（×10-1）", "芳香族（×10-2）", "（×10-3）", "(×10-2)",
          "（�0-2�", "��嗵族（×10-2）"]:
    print("  %-20r -> %s" % (s, bool(PAT.match(s.strip()))))