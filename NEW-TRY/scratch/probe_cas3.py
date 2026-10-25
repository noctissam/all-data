# -*- coding: utf-8 -*-
"""Probe CAS-by-name sources that do not need an API key."""
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
CTX = ssl._create_unverified_context()
UA = {"User-Agent": "reorganise/1.0"}


def get(url, timeout=25):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout,
        context=CTX).read().decode("utf-8", "replace")


print("--- NIST WebBook : search by Name ---")
for n in ("ethyl hexanoate", "acetic acid", "linalool"):
    try:
        u = ("https://webbook.nist.gov/cgi/cbook.cgi?Action=Search&Units=SI"
             "&Name=" + urllib.parse.quote(n) + "&NoIon=on&NoMix=on")
        txt = get(u)
        cas = re.search(r"CAS Registry Number[^0-9]{0,40}([0-9]{2,7}-[0-9]{2}-[0-9])", txt)
        hits = re.findall(r"cbook\.cgi\?ID=C([0-9]+)&amp;Mask", txt)
        print("  %-16s CAS=%-14s ids=%s" % (n, cas.group(1) if cas else "-", hits[:3]))
    except Exception as e:
        print("  %-16s ERROR %s" % (n, e))

print("--- NIST WebBook : lookup by CAS (no dashes) ---")
for cas in ("141786", "6604820", "787856"):
    try:
        u = "https://webbook.nist.gov/cgi/cbook.cgi?ID=C%s&Mask=2000" % cas
        txt = get(u)
        nm = re.search(r"<title>([^<]*)</title>", txt)
        got = re.search(r"CAS Registry Number[^0-9]{0,40}([0-9]{2,7}-[0-9]{2}-[0-9])", txt)
        print("  C%-8s title=%-34s CAS=%s" % (cas, (nm.group(1) if nm else "?")[:34],
                                              got.group(1) if got else "-"))
    except Exception as e:
        print("  C%-8s ERROR %s" % (cas, e))

print("--- Wikidata : CAS as property P231 ---")
for n in ("ethyl hexanoate", "acetic acid", "linalool"):
    try:
        u = ("https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json"
             "&language=en&type=item&limit=3&search=" + urllib.parse.quote(n))
        r = json.loads(get(u))
        out = []
        for it in r.get("search", []):
            qid = it["id"]
            d = json.loads(get("https://www.wikidata.org/wiki/Special:EntityData/%s.json" % qid))
            props = d["entities"][qid].get("claims", {})
            cas = [c["mainsnak"]["datavalue"]["value"]
                   for c in props.get("P231", [])
                   if "datavalue" in c["mainsnak"]]
            out.append((qid, cas[:2]))
        print("  %-16s %s" % (n, out))
    except Exception as e:
        print("  %-16s ERROR %s" % (n, e))