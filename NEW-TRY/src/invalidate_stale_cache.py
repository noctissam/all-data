# -*- coding: utf-8 -*-
"""
Invalidate cache entries that a name-cleaning rule would now change the answer for.

clean_name() strips a trailing unit and a leading retention index from the queried string.
That makes an existing cache entry wrong in a way that is invisible: the cache is keyed by
the ORIGINAL name, so "1-丁醇（mg·L-1）" keeps whatever verdict it was given when the whole
string was sent to PubChem, and the cleaning never runs.

This is the second time a change to the lookup rules has been shadowed by the cache - the
first was CURATED_CN, which sat unused because every name it covered had already been
recorded as "untranslatable". So the rule now is: any change to what gets sent to PubChem
must come with an invalidation pass, and this script is that pass.

Only entries whose cleaned form differs are dropped; everything else keeps its result.

Usage: python src/invalidate_stale_cache.py [--apply]
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import fill_cas as F   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    cache = F.load_cache()
    stale = []
    for key, v in list(cache.items()):
        cleaned = F.clean_name(key)
        if cleaned and cleaned != key:
            stale.append((key, v))

    print("cache entries: %d" % len(cache))
    print("entries whose cleaned form differs: %d" % len(stale))
    for key, v in stale[:20]:
        print("   %-34s %-16s %s" % (key[:34], (v[0] or "-")[:16], str(v[2])[:28]))
    if len(stale) > 20:
        print("   ... %d more" % (len(stale) - 20))

    if not stale:
        return

    if a.apply:
        for key, _v in stale:
            cache.pop(key, None)
        # one write, here, and not again at the end: see the note below
        F.save_cache(cache)

    F._REST_DEAD = True
    changed = same = stillbad = 0
    for key, v in stale:
        try:
            cas, cid, st = F.resolve(key, cache)
        except F.Throttled:
            print("   THROTTLED at %r - rerun later" % key[:30])
            time.sleep(10)
            continue
        old = (v[0] or "-")
        if cas and cas != old:
            changed += 1
        elif cas == old:
            same += 1
        else:
            stillbad += 1
        print("   %-34s %-14s -> %-14s %s" % (key[:34], old[:14], (cas or "-")[:14],
                                             st[:26]))
        time.sleep(0.35)

    # deliberately NOT saving again: `cache` may have been written by another process
    # while this one was resolving, and writing a snapshot back over it is how the
    # curated resolutions were lost once already.
    print("\nnewly resolved: %d   unchanged: %d   still unresolved: %d"
          % (changed, same, stillbad))


if __name__ == "__main__":
    main()