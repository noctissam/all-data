# -*- coding: utf-8 -*-
"""
Drop cached CAS results for every chinese-named compound.

A cache entry records the answer, not the route. The translator has since been rewritten
- it now keeps the position a name writes instead of overwriting it with the parent's
canonical one - so a cached value cannot be assumed to still follow from the name. For
chinese names the rules used to turn 2,3-二乙基吡嗪 into 2,3-dimethylpyrazine and 4-甲基苯酚
into 2-methylphenol, and a CAS stored under either name is a wrong number that looks
perfectly ordinary.

English-named entries are left alone: they were looked up directly, with no translation
step in between, so nothing about the change applies to them.

Run: python purge_zh_cache.py [--dry]
"""

import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")

import zh2en_full as Z

CACHE = "out/re整理/pubchem_cache.json"


def main():
    dry = "--dry" in sys.argv
    every = "--all" in sys.argv
    cache = json.load(open(CACHE, encoding="utf-8"))
    before = len(cache)
    drop = list(cache) if every else [k for k in cache if re.search(r"[一-鿿]", k)]
    for k in drop:
        cache.pop(k)
    after = len(cache)
    print("cache %d -> %d   dropped %d entries%s"
          % (before, after, len(drop), " (every entry)" if every else
             " (chinese-named only)"))

    kept = {k: v for k, v in cache.items() if str(v[2]).startswith("ok")}
    print("kept %d entries, %d of them resolved" % (after, len(kept)))

    # what the rewritten rules can now reach among the dropped names
    now = [k for k in drop if Z.translate(k)]
    print("of the dropped names, %d are now translatable" % len(now))
    print("   -> %d lookups needed" % len(now))

    if dry:
        return 0
    json.dump(cache, open(CACHE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("-> %s" % CACHE)
    return 0


if __name__ == "__main__":
    sys.exit(main())