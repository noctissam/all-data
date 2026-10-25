# -*- coding: utf-8 -*-
"""Show the candidate records for a name, with the isotope/stereo verdicts."""
import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import fill_cas as F

for name in ("chloroform", "phenol"):
    print("=== %s" % name)
    q = F.query_name(F.tidy(name))
    txt = F.get("%s/esearch.fcgi?db=pccompound&retmax=8&term=%s" % (F.EUTILS, F.urllib.parse.quote(q)))
    import re
    uids = re.findall(r"<Id>(\d+)</Id>", txt)
    for uid in uids[:6]:
        title, syn, cas, iupac = F.record_of(uid)
        print("  %-9s cas=%-12s title=%-22s iso(title)=%-5s iso(iupac)=%-5s iupac=%s"
              % (uid, cas, (title or "")[:22], F.has_isotope(title),
                 F.has_isotope(iupac), (iupac or "")[:40]))