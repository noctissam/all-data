# -*- coding: utf-8 -*-
"""
Add the CATEGORY_ROW guard to build_rec整理.py.

Patched by line index rather than by text match: the file stores its CJK ranges as literal
"\\u4e00" escapes, and there are two copies of the CHEM_RADICAL / LATIN_NAME /
looks_like_compound block, so a text anchor is ambiguous and an escape-aware string keeps
being rewritten into the characters it was meant to match.

Idempotent: exits if the guard is already present.
"""
import io
import sys

sys.stdout.reconfigure(encoding="utf-8")
P = "src/build_rec整理.py"

s = io.open(P, encoding="utf-8").read()
if "CATEGORY_ROW" in s:
    print("already patched")
    sys.exit(0)

DEF = "\n\ndef looks_like_compound(s):"
last = s.rfind(DEF)
if last < 0:
    raise SystemExit("could not find looks_like_compound")

cat = '''

# Class labels and grand totals, not compounds. The ratio tables (表3-3, 表3-6) print
# 酯类 / 醇类 / 醛酮类 / 吡嗪类 and their Σ totals as rows. Every one of those passes the
# radical test below, because 酯, 醇, 醛 and 酮 are all radicals - so they entered the
# compound block and were then offered to the CAS lookup as if they were substances. A
# class label covers a whole group and has no registry number, so the blank cell there is
# the correct answer rather than a gap.
CATEGORY_ROW = re.compile(
    r"(?:酯|醇|酸|醛|酮|烯|苯|酚|吡嗪|含氮|硫化物|缩醛|呋喃|萜烯|芳香族)"
    r"类\\s*(?:[Σ∑]\\s*)?(?:\\(\\s*×\\s*10[^)]*\\))?\\s*$"
    r"|物质总含量|总含量")
'''

# 1. the regex, immediately before the (last) definition
s = s[:last] + cat + s[last:]

# 2. the guard, right after that definition's "if not s: return False"
last = s.rfind("\n\ndef looks_like_compound(s):")
anchor = "    if not s:\n        return False\n"
pos = s.find(anchor, last)
if pos < 0:
    raise SystemExit("could not find the guard insertion point")
pos += len(anchor)
guard = "    # checked before the radical test, which these rows would otherwise pass\n" \
        "    if CATEGORY_ROW.search(s):\n        return False\n"
s = s[:pos] + guard + s[pos:]

io.open(P, "w", encoding="utf-8").write(s)
print("patched build_rec整理.py")