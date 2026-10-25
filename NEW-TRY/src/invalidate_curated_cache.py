# -*- coding: utf-8 -*-
"""
Drop the cache entries that the CURATED_CN table cannot reach.

The curated mappings were added after most of these names had already been looked up, and
a cached entry short-circuits resolve() before any translation happens. So the names were
sitting in the cache as "untranslatable" - a verdict reached before CURATED_CN existed -
and the new table was never consulted for any of them. Only the one entry that had never
been cached was resolved by the first run.

This drops every CURATED_CN key and reports what each one changes, so the new answers can
be compared against the old ones rather than taken on trust.

Usage: python src/invalidate_curated_cache.py [--apply]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import fill_cas as F   # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "out", "re整理", "pubchem_cache.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    cache = F.load_cache()
    before = {}
    drop = []
    for cn in F.CURATED_CN:
        key = F.tidy(cn)
        v = cache.get(key)
        if v is None:
            continue
        before[cn] = (v[0], v[2])
        # anything that is not a confirmed ok result, and any ok result whose CAS differs
        # from what the curated mapping yields, has to be looked up again
        drop.append(cn)

    print("curated entries to re-resolve: %d" % len(drop))
    if a.apply:
        for cn in drop:
            cache.pop(F.tidy(cn), None)
        F.save_cache(cache)
        print("dropped; re-run fill_cas to fill them under the curated mappings")

    # now resolve and print the change for each
    print("\n%-18s %-26s %-26s %s" % ("name", "cached before", "after curated", "note"))
    changed = same = 0
    for cn in sorted(F.CURATED_CN):
        key = F.tidy(cn)
        scratch = {} if a.apply else cache
        # with --apply the entry is gone from the cache, so resolve() does a real lookup
        try:
            cas, cid, st = F.resolve(cn, cache if not a.apply else scratch)
        except F.Throttled:
            print("%-18s THROTTLED - rerun later" % cn[:18])
            time.sleep(10)
            continue
        old = before.get(cn, ("(none)", ""))[0]
        note = ""
        if old and old != cas:
            note = "CHANGED"
            changed += 1
        elif old == cas:
            same += 1
        else:
            note = "newly resolved" if cas else "still no CAS"
        print("%-18s %-26s %-26s %s"
              % (cn[:18], old or "-", cas or "-", note))
        time.sleep(0.35)
    # Deliberately NOT saving the cache here.
    #
    # This run resolves into `scratch`, so the `cache` object in hand is the snapshot taken
    # at start-up. Writing it back at the end is a last-writer-wins clobber: it silently
    # reverts every lookup another process made while this one was running. That is not
    # hypothetical - it threw away the 41 curated resolutions that fill_cas had written
    # minutes earlier, and the coverage dropped from 82% back to 78% with no error anywhere.
    # The cache was already saved once, right after the entries were dropped, which is the
    # only write this script needs to make.
    print("\nchanged: %d   unchanged: %d" % (changed, same))


if __name__ == "__main__":
    main()