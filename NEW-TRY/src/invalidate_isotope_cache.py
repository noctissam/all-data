# -*- coding: utf-8 -*-
"""
Drop cached lookups that resolved to an isotopically labelled record.

The isotope guard in fill_cas only applies to a fresh lookup, so every name already in
pubchem_cache.json keeps whatever it was given before the guard existed - "phenol" is
cached as 13127-88-3, which is phenol-d6. Re-running fill_cas alone would not change that,
and the workbook would still carry the labelled analog's registry number.

The cached CIDs are checked in batches of 20 through one esummary call each, which is far
cheaper than re-resolving several hundred names one at a time, and only the entries that
are actually affected are dropped.

Usage: python src/invalidate_isotope_cache.py [--apply]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import fill_cas as F   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "..", "out", "re整理", "pubchem_cache.json")
BATCH = 20


def iupac_for(cid):
    xml = F.get("%s/esummary.fcgi?db=pccompound&id=%s" % (F.EUTILS, cid))
    m = re.findall(r"<Item Name=\"IUPACName\"[^>]*>([^<]*)</Item>", xml)
    syn = re.search(r'<Item Name="SynonymList"[^>]*>(.*?)</Item>\s*</Item>', xml, re.S)
    names = re.findall(r'<Item Name="string"[^>]*>([^<]+)</Item>',
                       syn.group(1)) if syn else []
    return (m[0] if m else ""), names[:6]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete the entries")
    a = ap.parse_args()

    cache = json.load(open(CACHE, encoding="utf-8"))
    pairs = []
    for name, v in cache.items():
        if not (isinstance(v, list) and len(v) >= 3 and v[1] and str(v[2]).startswith("ok")):
            continue
        pairs.append((name, str(v[1])))
    print("cached resolved lookups: %d" % len(pairs))

    by_cid = {}
    for name, cid in pairs:
        by_cid.setdefault(cid, []).append(name)
    cids = list(by_cid)
    print("distinct CIDs: %d  -> %d esummary calls"
          % (len(cids), (len(cids) + BATCH - 1) // BATCH))

    bad = []
    for i in range(0, len(cids), BATCH):
        chunk = cids[i:i + BATCH]
        try:
            xml = F.get("%s/esummary.fcgi?db=pccompound&id=%s"
                        % (F.EUTILS, ",".join(chunk)))
        except Exception as e:
            print("  batch %d failed: %s" % (i, e))
            continue
        # each DocSum block belongs to one CID
        for block in re.findall(r"<DocSum>(.*?)</DocSum>", xml, re.S):
            cid = re.search(r"<Id>(\d+)</Id>", block)
            iu = re.search(r'<Item Name="IUPACName"[^>]*>([^<]*)</Item>', block)
            syn = re.search(r'<Item Name="SynonymList"[^>]*>(.*?)</Item>\s*</Item>',
                            block, re.S)
            names = re.findall(r'<Item Name="string"[^>]*>([^<]+)</Item>',
                               syn.group(1)) if syn else []
            if not cid:
                continue
            if F.has_isotope(iu.group(1) if iu else "") or any(
                    F.has_isotope(n) for n in names[:8]):
                bad.extend(by_cid.get(cid.group(1), []))
        time.sleep(0.34)

    print("\nlookups pointing at a labelled record: %d" % len(bad))
    for n in bad[:40]:
        print("   %-40s -> %s" % (n[:40], cache[n][0]))

    if bad and a.apply:
        for n in bad:
            cache.pop(n, None)
        json.dump(cache, open(CACHE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("\ndropped %d entries; re-run fill_cas to resolve them again" % len(bad))
    elif bad:
        print("\n(dry run - pass --apply to drop them)")


if __name__ == "__main__":
    main()