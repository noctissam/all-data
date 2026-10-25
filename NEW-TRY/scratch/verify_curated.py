# -*- coding: utf-8 -*-
"""
Resolve every CURATED_CN entry and print what PubChem says the number belongs to.

The point is not that the lookup succeeds - it is that the record it lands on is the
compound the Chinese name denotes. A curated entry that resolves to a neighbouring
structure is worse than no entry, because it is trusted: it bypasses the rule engine and
the KNOWN_BAD guard, so nothing downstream will question it.

Each row prints the English name that was sent, the CID, the CAS, and the first synonyms
PubChem lists for that CID, so the identification can be checked by reading.
"""
import re
import sys
import time
import urllib.parse

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import fill_cas as F   # noqa: E402


def cid_names(cid):
    xml = F.get("%s/esummary.fcgi?db=pccompound&id=%s" % (F.EUTILS, cid))
    syn = re.search(r'<Item Name="SynonymList"[^>]*>(.*?)</Item>\s*</Item>', xml, re.S)
    out = re.findall(r'<Item Name="string"[^>]*>([^<]+)</Item>', syn.group(1)) if syn else []
    iu = re.search(r'<Item Name="IUPACName"[^>]*>([^<]*)</Item>', xml)
    return (iu.group(1) if iu else ""), [s for s in out
                                         if not re.match(r"^(DTXSID|CID|\d{2,7}-\d{2}-\d)", s, re.I)][:4]


def main():
    F._REST_DEAD = True
    cache = F.load_cache()
    ok = bad = 0
    for cn, en in sorted(F.CURATED_CN.items()):
        key = F.tidy(cn)
        # resolve through a scratch dict so a bad entry never reaches the real cache
        scratch = {}
        try:
            cas, cid, st = F.resolve(cn, scratch)
        except F.Throttled:
            print("%-16s %-34s THROTTLED" % (cn[:16], en[:34]))
            time.sleep(10)
            continue
        except Exception as e:
            print("%-16s %-34s ERROR %s" % (cn[:16], en[:34], e))
            bad += 1
            continue
        if not cas:
            print("%-16s %-34s -> NO CAS  (%s)" % (cn[:16], en[:34], st[:40]))
            bad += 1
            time.sleep(0.4)
            continue
        iu, syn = cid_names(cid)
        # does the record carry the English name we sent?
        want = re.sub(r"[^a-z0-9]", "", en.lower())
        hit = any(re.sub(r"[^a-z0-9]", "", s.lower()) == want for s in syn) or \
            re.sub(r"[^a-z0-9]", "", (iu or "").lower()) == want
        mark = "ok  " if hit else "CHECK"
        if hit:
            ok += 1
        else:
            bad += 1
        print("%s %-16s %-34s %-12s %-9s %s" % (mark, cn[:16], en[:34], cas, cid,
                                               " / ".join(syn[:3])))
        time.sleep(0.4)
    print("\nmatched: %d   need review: %d   (of %d)"
          % (ok, bad, len(F.CURATED_CN)))


if __name__ == "__main__":
    main()