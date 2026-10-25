# -*- coding: utf-8 -*-
"""
Decide the printed-vs-resolved CAS conflicts with evidence instead of by policy.

write_cas keeps a printed CAS over a resolved one, which is right in general: the printed
number is the one the authors used for their own standards. But when the two disagree the
usual cause is that the OCR put the printed CAS one row off, and then the policy preserves
a number that belongs to a different compound.

The test is direct: look the printed CAS up in PubChem and read back the name it belongs
to. If that name is a different compound from the row's own name, the printed value is
misaligned and keeping it writes a wrong number into a priority-1 column. If it is the
same compound - "cedrol" carries more than one registry number - then the printed value is
correct and stays.

Usage: python src/audit_cas_conflicts.py
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "reorganise/1.0"})
    ctx = None
    try:
        import ssl
        ctx = ssl._create_unverified_context()
    except Exception:
        pass
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return r.read().decode("utf-8", "replace")


def cas_to_title(cas):
    """The PubChem compound name a registry number belongs to, or None.

    pccompound esummary carries no "Title" item - the record's names live in
    SynonymList, so the first entry is what stands in for a title. Parsing for a Title
    item silently returned nothing for every query and made all seven conflicts look like
    misalignment, which is how the audit nearly "confirmed" a conclusion it had invented.
    """
    term = urllib.parse.quote("%s[Synonym]" % cas)
    xml = _get("%s/esearch.fcgi?db=pccompound&retmax=5&term=%s" % (EUTILS, term))
    ids = re.findall(r"<Id>(\d+)</Id>", xml)
    if not ids:
        return None
    xml = _get("%s/esummary.fcgi?db=pccompound&id=%s"
               % (EUTILS, ",".join(ids[:3])))
    syn = re.search(r'<Item Name="SynonymList"[^>]*>(.*?)</Item>\s*</Item>', xml, re.S)
    if syn:
        names = re.findall(r'<Item Name="string"[^>]*>([^<]+)</Item>', syn.group(1))
        # skip registry-style entries (DTXSID..., CAS) that sort first in the list
        names = [n for n in names
                 if not re.match(r"^(DTXSID|CID|\d{2,7}-\d{2}-\d)", n, re.I)]
        if names:
            return names[0]
    return None


def norm(s):
    return re.sub(r"[^a-z0-9一-鿿]", "", (s or "").lower())


def same_compound(a, b):
    """
    Loose identity test between two chemical names, name-to-name and synonym-to-name.

    Substring containment is the useful part: PubChem's first synonym is often a qualified
    form of the plain name ("Ethyl L-lactate" vs "Ethyl lactate", "(-)-terpineol" vs
    "terpineol"), and that difference is exactly the case where the printed number is more
    specific rather than wrong. Requiring equality here would call all of those errors and
    push the pipeline toward overwriting a correct registry number.
    """
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def main():
    conflicts = json.load(open(os.path.join(REOUT, "conflicts.json"), encoding="utf-8"))
    out = []
    for c in conflicts:
        printed, resolved, name = c["printed"], c["resolved"], c["name"]
        t_printed = cas_to_title(printed)
        t_resolved = cas_to_title(resolved)
        same = same_compound(t_printed, name)
        verdict = ("印刷值指向同一化合物" if same else
                   "印刷值指向别的化合物 -> 疑似整列错位")
        row = dict(sheet=c["sheet"], name=name, printed=printed,
                   printed_is=t_printed, resolved=resolved, resolved_is=t_resolved,
                   verdict=verdict)
        out.append(row)
        print("%-34s %-22s" % (c["sheet"][:34], name[:22]))
        print("    印刷 %-12s -> %s" % (printed, t_printed))
        print("    反查 %-12s -> %s" % (resolved, t_resolved))
        print("    => %s" % verdict)
        time.sleep(0.4)
    json.dump(out, open(os.path.join(REOUT, "conflicts_audited.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n-> out/re整理/conflicts_audited.json")


if __name__ == "__main__":
    main()