# -*- coding: utf-8 -*-
"""
Audit of the chinese -> english name translation.

Three questions, none of which can be answered by looking at the rules alone:

  coverage      how many names the rules now reach, and what is left.

  bilingual     a cell may hold a chinese name and an english one that name different
                compounds - 丁酸异丁酯 against "3-methylbutyl butanoate" is isobutyl
                butanoate against sec-amyl butanoate. Text comparison cannot tell a
                synonym from a different compound, so both sides are resolved to a PubChem
                CID and compared there.

  residue       why each untranslated name was left alone, so the remainder is a list of
                decisions rather than a pile of failures.

Run: python audit_zh2en.py [--offline]
"""

import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")

import zh2en_full as Z

CACHE = "out/re整理/pubchem_cache.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_ctx = ssl._create_unverified_context()


def cid_of(name, memo):
    """name -> PubChem CID through an exact quoted synonym search, or None."""
    if name in memo:
        return memo[name]
    term = '"%s"[Synonym]' % name.replace('"', "")
    u = ("%s/esearch.fcgi?db=pccompound&retmode=json&retmax=5&term=%s"
         % (EUTILS, urllib.parse.quote(term)))
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "p/1"}),
            timeout=30, context=_ctx).read().decode("utf-8", "replace")
        m = re.search(r'"idlist"\s*:\s*\[([^\]]*)\]', r)
        memo[name] = int(re.findall(r'"(\d+)"', m.group(1))[0]) if m and m.group(1).strip() else None
    except Exception:
        memo[name] = None
    return memo[name]


def why_not(name):
    """Why a name was left untranslated."""
    s = Z._norm(name)
    if Z.ARTIFACT.search(s):
        return "ocr-fragment"
    if Z.NOT_COMPOUND.match(s) or Z.CLASS_HEAD.search(s):
        return "not-a-compound"
    if Z._key(s) in Z.AMBIGUOUS_BY_KEY:
        return "ambiguous"
    if Z._key(s) in Z.KNOWN_BAD_BY_KEY:
        return "blocked"
    if re.search(r"[A-Za-z]", s):
        return "damaged-english"
    if len(s) <= 2 or not re.search(r"(酸|醇|醛|酯|酮|烷|烯|炔|环|基)", s):
        return "fragment"
    return "rules-do-not-cover"


def main():
    offline = "--offline" in sys.argv
    cache = json.load(open(CACHE, encoding="utf-8"))
    corpus = [k for k in cache if re.search(r"[一-鿿]", k)]
    out = {k: Z.translate(k) for k in corpus}
    reach = [k for k, v in out.items() if v]

    print("=" * 68)
    print("COVERAGE   %d of %d chinese names translated  (%.0f%%)"
          % (len(reach), len(corpus), 100.0 * len(reach) / max(len(corpus), 1)))
    print("=" * 68)

    rest = Counter(why_not(k) for k in corpus if not out[k])
    for reason, n in rest.most_common():
        print("   %-18s %d" % (reason, n))
    print()

    print("--- residue by reason ---")
    for reason in rest:
        names = [k for k in sorted(corpus) if not out[k] and why_not(k) == reason]
        print("   %s (%d):" % (reason, len(names)))
        for n in names[:14]:
            print("      %s" % n)
        if len(names) > 14:
            print("      ... and %d more" % (len(names) - 14))
        print()

    Z.CONFLICTED.clear()
    for k in corpus:
        Z.translate(k)
    print("=" * 68)
    print("BILINGUAL CELLS   %d where the two halves were compared"
          % len(Z.CONFLICTED))
    print("=" * 68)
    memo = {}
    for src, zh_en, en in Z.CONFLICTED:
        if offline:
            print("   %-22s %-26s vs %s" % (src, zh_en, en))
            continue
        a, b = cid_of(zh_en, memo), cid_of(en, memo)
        if a and b and a == b:
            verdict = "same compound (synonym), chinese kept"
        elif a and b:
            verdict = "DIFFERENT COMPOUND  cid %s vs %s - needs a look" % (a, b)
        else:
            verdict = "one side not in PubChem (%s / %s)" % (a, b)
        print("   %-22s %-26s vs %-28s %s" % (src, zh_en, en, verdict))

    # a dump the CAS step can use to purge stale cache entries
    stale = [k for k in corpus if not out[k]]
    json.dump({"translated": {k: v for k, v in out.items() if v},
               "unreachable": stale},
              open("out/re整理/zh2en_audit.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print()
    print("-> out/re整理/zh2en_audit.json  (%d translated, %d unreachable)"
          % (len(out) - len(stale), len(stale)))

    # Cells that held more than a name. These are extraction faults, not translation
    # faults, and the numbers in them belong in other columns - so they are listed with
    # the sheet and row they sit on rather than quietly used.
    Z.CELL_EXTRA.clear()
    for k in corpus:
        Z.translate(k)
    print()
    print("=" * 68)
    print("CELLS THAT HELD MORE THAN A NAME   %d" % len(Z.CELL_EXTRA))
    print("=" * 68)
    numeric = [(s, e, r) for s, e, r in Z.CELL_EXTRA
               if any(re.fullmatch(r"[\d.]+", t) for t in r.split())]
    print("   %d contain bare numbers, which means the table row was never split"
          % len(numeric))
    print("   %d are descriptive text after the name" % (len(Z.CELL_EXTRA) - len(numeric)))
    for s, e, r in Z.CELL_EXTRA[:20]:
        tag = "NUM" if any(re.fullmatch(r"[\d.]+", t) for t in r.split()) else "TXT"
        print("   %-3s %-24s %-24s | %s" % (tag, s, e, r[:50]))
    return 0


if __name__ == "__main__":
    sys.exit(main())