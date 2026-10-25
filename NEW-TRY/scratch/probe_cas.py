# -*- coding: utf-8 -*-
"""Probe PubChem E-utilities for the right CAS -> CID query syntax."""
import re
import ssl
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
CTX = ssl._create_unverified_context()
E = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def g(u):
    r = urllib.request.Request(u, headers={"User-Agent": "t/1.0"})
    return urllib.request.urlopen(r, timeout=30, context=CTX).read().decode("utf-8", "replace")


def titles(ids):
    if not ids:
        return []
    s = g("%s/esummary.fcgi?db=pccompound&id=%s" % (E, ",".join(ids)))
    return re.findall(r'<Item Name="Title"[^>]*>([^<]+)</Item>', s)[:3]


for term in ['687-47-8[Synonym]',
             '"687-47-8"[Synonym]',
             '687-47-8',
             'Ethyl lactate[Title]',
             '108-95-2[Synonym]',
             '"108-95-2"[Synonym]']:
    try:
        x = g("%s/esearch.fcgi?db=pccompound&retmax=3&term=%s"
              % (E, urllib.parse.quote(term)))
        ids = re.findall(r"<Id>(\d+)</Id>", x)
        print("%-26s ids=%-20s %s" % (term, ids, titles(ids)))
    except Exception as e:
        print("%-26s ERROR %s" % (term, e))