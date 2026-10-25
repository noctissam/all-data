# -*- coding: utf-8 -*-
"""Probe second CAS sources for reachability and whether they answer a name query."""
import json
import ssl
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
CTX = ssl._create_unverified_context()
UA = {"User-Agent": "reorganise/1.0"}


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout, context=CTX).read().decode(
        "utf-8", "replace")


NAMES = ["ethyl hexanoate", "ethyl acetate", "acetic acid", "linalool"]

print("--- CAS Common Chemistry ---")
for n in NAMES[:2]:
    try:
        u = ("https://commonchemistry.cas.org/api/search?q="
             + urllib.parse.quote(n) + "&max=3")
        r = json.loads(get(u))
        hits = r.get("hits") or []
        print("  %-16s hits=%d" % (n, len(hits)))
        for h in hits[:2]:
            print("     cas=%s  name=%r" % (h.get("cas"), (h.get("name") or "")[:40]))
    except Exception as e:
        print("  %-16s ERROR %s" % (n, e))

print("--- NIST Chemistry WebBook ---")
for n in NAMES[:2]:
    try:
        u = ("https://webbook.nist.gov/cgi/cbook.cgi?Units=SI&Mask=2000"
             "&Action=Search&Formula=" + urllib.parse.quote(n) + "&NoIon=on"
             "&NoMix=on")
        txt = get(u)
        has = "CAS" in txt
        import re
        cases = re.findall(r"\[?(\d{2,7}-\d{2}-\d)\]?", txt)[:3]
        print("  %-16s len=%d  CAS_present=%s  found=%s" % (n, len(txt), has, cases))
    except Exception as e:
        print("  %-16s ERROR %s" % (n, e))

print("--- ChEBI (EBI) ---")
try:
    u = ("https://www.ebi.ac.uk/chebi/backend/api/public/compounds/search/"
         "?query=ethyl%20hexanoate&maxResults=3")
    r = json.loads(get(u))
    print("  hits:", len(r.get("compounds") or []))
    for c in (r.get("compounds") or [])[:2]:
        print("     ", c.get("chebiId"), c.get("name"))
except Exception as e:
    print("  ERROR", e)