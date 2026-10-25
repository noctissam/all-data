# -*- coding: utf-8 -*-
"""What does PubChem call the record behind a given registry number?"""
import re
import sys
import urllib.parse

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import fill_cas as F

for cas in ("67-66-3", "13127-88-3", "108-95-2"):
    term = urllib.parse.quote("%s[Synonym]" % cas)
    txt = F.get("%s/esearch.fcgi?db=pccompound&retmax=3&term=%s" % (F.EUTILS, term))
    uids = re.findall(r"<Id>(\d+)</Id>", txt)
    print("=== %s -> %s" % (cas, uids))
    for uid in uids[:2]:
        title, syn, c, iupac = F.record_of(uid)
        print("   title=%r" % title)
        print("   iupac=%r" % iupac)
        print("   iso(title)=%s iso(iupac)=%s  first_syn=%r"
              % (F.has_isotope(title), F.has_isotope(iupac), (syn or [None])[0]))