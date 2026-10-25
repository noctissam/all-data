# -*- coding: utf-8 -*-
"""Audit the two-database disagreements: what does each registry number actually name?

A disagreement is only resolvable once both numbers are identified. If NIST answered a
different compound - which it does, by serving the first hit on a results page rather than
saying it found nothing - then NIST is simply wrong here and PubChem stands.
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
import cas_crosscheck as X   # noqa: E402

CTX = ssl._create_unverified_context()
UA = {"User-Agent": "reorganise/1.0 (cas disagreement audit)"}


def pubchem_title(cas):
    """What PubChem says this registry number is."""
    u = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/%s/property/"
         "Title,MolecularFormula/JSON" % urllib.parse.quote(cas))
    try:
        r = json.loads(urllib.request.urlopen(
            urllib.request.Request(u, headers=UA), timeout=30,
            context=CTX).read().decode("utf-8", "replace"))
        p = r["PropertyTable"]["Properties"][0]
        return p.get("Title", ""), p.get("MolecularFormula", "")
    except Exception as e:
        return "ERR:%s" % type(e).__name__, ""


def main():
    cx = json.load(open(os.path.join(X.REOUT, "cas_cross.json"), encoding="utf-8"))
    dis = [(k, v) for k, v in cx.items() if v.get("status") == "disagree"]
    print("两库不一致: %d 个名字\n" % len(dis))
    for name, v in sorted(dis, key=lambda x: -x[1].get("rows", 0)):
        p, n = v.get("pubchem", ""), v.get("nist", "")
        print("=" * 82)
        print("名字      : %s" % name)
        print("PubChem   : %-14s  实际是 -> %s" % (p, pubchem_title(p)[0] or "查不到"))
        nn = X.nist_name_of(n)
        print("NIST      : %-14s  实际是 -> %s" % (n, nn or "NIST 未收录此号"))
        time.sleep(0.4)


if __name__ == "__main__":
    main()