# -*- coding: utf-8 -*-
"""
Resolve CAS numbers against a second, independent chemical database and cross-correspond.

PubChem alone decides every CAS in the workbook today. That is a single point of failure: a
wrong answer from one source is indistinguishable from a right one, and the round-trip check
inside fill_cas cannot see it because it round-trips the same source.

So NIST Chemistry WebBook is asked the same question, independently, and the two answers
are compared:

  agree            both sources name the same registry number - written, and noted
  disagree         written as a blank-for-review rather than picked, because there is no
                   basis in the evidence for preferring one database over the other
  PubChem empty    NIST's answer is used and marked as coming from NIST
  NIST empty       PubChem's answer stands

NIST is a good second opinion here because it is a curated, non-commercial compilation
rather than a structure database: its coverage is narrower than PubChem's, so a name it
knows is a name a chemist curated, and a disagreement usually means one of the two read the
name differently.

Usage:
    python src/cas_crosscheck.py --names out/re整理/names.txt [--apply]
"""
import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fill_cas as F   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.join(HERE, "..", "out", "re整理")
CACHE = os.path.join(REOUT, "nist_cache.json")
CTX = ssl._create_unverified_context()
UA = {"User-Agent": "reorganise/1.0 (cas cross-check)"}

CAS_RE = re.compile(r"\d{2,7}-\d{2}-\d")
# NIST prints "CAS Registry Number: 123-66-0" near the top of a hit; anywhere else on the
# page is a reference in the text, which is not the compound's own number.
CAS_LINE = re.compile(r"CAS\s+Registry\s+Number[^0-9]{0,60}(\d{2,7}-\d{2}-\d)")


def _get(url, timeout=30):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout,
        context=CTX).read().decode("utf-8", "replace")


def nist_cas(name, pause=0.35):
    """CAS from NIST by name, or None.

    Two rejections here are load-bearing, both added after the first run produced 20-odd
    confident wrong numbers:

      - a non-ASCII name is refused outright. NIST indexes no Chinese names, and rather
        than say so it serves an unrelated record: querying "1-辛醇b" returned the page for
        BORON, and the CAS on it, 7440-42-8, was written into dozens of rows before this was
        noticed. A second source that invents an answer is worse than no second source.
      - a results page is refused. "Search Results" and "Name Not Found" mean nothing was
        found; the first CAS-shaped number on such a page belongs to something else.
    """
    if not name or any(ord(ch) > 0x2E80 for ch in name):
        return None, "non-ascii-refused"
    u = ("https://webbook.nist.gov/cgi/cbook.cgi?Action=Search&Units=SI&Name="
         + urllib.parse.quote(name) + "&NoIon=on&NoMix=on")
    try:
        txt = _get(u)
    except Exception as e:
        return None, "error:%s" % type(e).__name__
    if ("Registry Number Not Found" in txt or "no matches" in txt.lower()
            or "Name Not Found" in txt):
        return None, "not-found"
    title = re.search(r"<title>([^<]*)</title>", txt)
    tname = (title.group(1).strip() if title else "")
    if tname.lower() in ("search results", "nist chemistry webbook", ""):
        # a hit list, not a record: any CAS on it belongs to whichever entry came first
        return None, "results-page"
    m = CAS_LINE.search(txt)
    if m:
        return m.group(1), "ok"
    return None, "no-cas-on-page"


def nist_name_of(cas):
    """The compound name NIST gives for a registry number - used to check a disagreement."""
    u = "https://webbook.nist.gov/cgi/cbook.cgi?ID=C%s&Mask=2000" % cas.replace("-", "")
    try:
        txt = _get(u)
    except Exception:
        return None
    if "Registry Number Not Found" in txt:
        return None
    m = re.search(r"<title>([^<]*)</title>", txt)
    return m.group(1).strip() if m else None


def selfcheck():
    """
    Two probes before anything is written: one name NIST must know, one it must not.

    This exists because the failure was silent. The first run happily returned Boron's
    registry number for twenty Chinese names, every one of them a confident CAS that would
    have been written into the workbook, and nothing in the output said so. A second source
    that invents answers is worse than none, so the refusal is checked rather than assumed.
    """
    good, bad = "ethyl acetate", "1-辛醇"
    cas_ok, st_ok = nist_cas(good)
    cas_no, st_no = nist_cas(bad)
    print("self-check: %-16s -> %-12s (%s)" % (good, cas_ok or "-", st_ok))
    print("            %-16s -> %-12s (%s)" % (bad, cas_no or "-", st_no))
    problems = []
    if cas_ok != "141-78-6":
        problems.append("%s gave %s, expected 141-78-6" % (good, cas_ok))
    if cas_no:
        problems.append("%s returned %s - NIST must refuse it" % (bad, cas_no))
    for p in problems:
        print("   SELF-CHECK FAILED: %s" % p)
    return not problems


# A stereodescriptor in parentheses - (2E), (4E), (E), (R), (S), (Z), (--), (+) - plus the
# free-standing forms. Written to be stripped from BOTH sides of a comparison: PubChem spells
# out the configuration the query never mentioned, NIST leaves it off, and the two numbers
# then look like a disagreement when they are the same compound.
STEREO = re.compile(
    r"\(\s*[+\-]?\s*\)|[（(]\s*[+\-]\s*[）)]"
    r"|[（(]\s*[0-9]*\s*[A-Za-zαβ]\s*[）)]"
    # "L(--)-lactate", "D(+)", "(S)": a lone L/D/R/S straight before a dash or a bracket, and
    # a run of dashes closing a bracket. Without these "Ethyl L(--)-lactate" shows no
    # stereodescriptor at all and the case cannot be recognised.
    r"|[-–]{1,3}[）)]|\b[LR](?=[-–(（])"
    r"|\b(?:dl|cis|trans)\b|α|β")


def _core_title(s):
    """Title with stereodescriptors and punctuation removed, for comparing two answers."""
    s = STEREO.sub(" ", str(s or ""))
    s = re.sub(r"[(),，、]", " ", s)
    s = re.sub(r"-\s*$", "", s.strip())
    return re.sub(r"\s+", " ", s).strip().lower()


def _key(s):
    """Letters and digits only, for asking whether a title IS the thing that was asked for."""
    return re.sub(r"[^0-9a-z一-鿿]+", "", str(s or "").lower())


def pubchem_title(cas):
    """What PubChem calls this registry number."""
    u = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/%s/property/"
         "Title/JSON" % urllib.parse.quote(cas))
    try:
        r = json.loads(urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "reorganise/1.0"}),
            timeout=30, context=CTX).read().decode("utf-8", "replace"))
        return r["PropertyTable"]["Properties"][0].get("Title", "")
    except Exception:
        return ""


def resolve_disagreements(path, pause=0.5):
    """
    Settle the disagreements where the evidence settles them.

    Three cases came out of auditing all five by hand:

      - NIST answered with a number it does not itself hold. "Ethyl 4-decenoate" came back
        as 10-11-1, which is diphenylamine. That is a bad hit, not an opinion.
      - The name carries a stereodescriptor that one database dropped. "Ethyl L(--)-lactate"
        came back from PubChem as plain "Ethyl Lactate" - the racemate - while NIST gave
        "(L)-", which is what the name asked for.
      - Both answers name the same compound and differ only in whether they spell out an
        E/Z configuration the query never mentioned. That is not a conflict.

    Anything still unsettled keeps status 'disagree' and stays blank.
    """
    merged = json.load(open(path, encoding="utf-8"))
    dis = [(k, v) for k, v in merged.items() if v.get("status") == "disagree"]
    print("disagreements to resolve: %d" % len(dis))
    for name, v in dis:
        p, n = v.get("pubchem", ""), v.get("nist", "")
        nn = nist_name_of(n) or ""
        pt = pubchem_title(p)
        if not nn:
            v["status"], v["cas"] = "nist-bad-hit", p
            note = "NIST 给的号它自己不收录（%s），按坏命中丢弃，保留 PubChem" % n
        elif STEREO.search(name) and STEREO.search(nn) and not STEREO.search(pt):
            v["status"], v["cas"] = "stereo-resolved", n
            note = "名字带构型标记，PubChem 丢成外消旋（%s），采纳 NIST 的 %s" % (pt or "?", nn)
        elif _core_title(pt) and _core_title(pt) == _core_title(nn):
            v["status"], v["cas"] = "stereo-variant", p
            note = "同一化合物，仅构型标注详略不同（%s / %s），保留 PubChem" % (pt or "?", nn)
        elif _key(nn) and _key(name) in _key(nn) and _key(name) not in _key(pt):
            # one of them answers the question that was asked. Cedrol and Cedran-8-ol are
            # two different terpenes, and only one of them is the word in the query.
            v["status"], v["cas"] = "title-match", n
            note = "只有 NIST 的标题就是所查的物质（%s vs %s），采纳 NIST" % (nn, pt or "?")
        elif _key(pt) and _key(name) in _key(pt) and _key(name) not in _key(nn):
            v["status"], v["cas"] = "title-match", p
            note = "只有 PubChem 的标题就是所查的物质（%s vs %s），采纳 PubChem" % (pt, nn or "?")
        else:
            v["cas"] = ""
            note = "证据不足，仍留空"
        v["note"] = note
        print("   %-26s %-13s %s" % (name[:26], v["cas"] or "(留空)", note))
        time.sleep(pause)
    json.dump(merged, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    left = sum(1 for v in merged.values() if v.get("status") == "disagree")
    print("仍留空: %d" % left)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default="", help="file of names, one per line")
    ap.add_argument("--apply", action="store_true", help="write cas_cross.json")
    ap.add_argument("--resolve", action="store_true",
                    help="audit and settle the disagreements in cas_cross.json")
    ap.add_argument("--pause", type=float, default=0.35)
    ap.add_argument("--no-selfcheck", action="store_true")
    a = ap.parse_args()

    if a.resolve:
        resolve_disagreements(os.path.join(REOUT, "cas_cross.json"), a.pause)
        return

    if not a.no_selfcheck and not selfcheck():
        raise SystemExit("aborting: the NIST route is not behaving, and a second source that"
                         " invents an answer is worse than no second source")

    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))

    if a.names and os.path.exists(a.names):
        names = [x.strip() for x in open(a.names, encoding="utf-8") if x.strip()]
    else:
        pub = json.load(open(os.path.join(REOUT, "cas_by_name.json"), encoding="utf-8"))
        names = sorted(pub.get("rows", {}))
    print("names to cross-check: %d" % len(names))

    out, stat = {}, {"agree": 0, "disagree": 0, "nist-only": 0, "pubchem-only": 0,
                     "neither": 0, "cached": 0, "error": 0}
    for i, name in enumerate(names):
        key = F.tidy(name)
        if key in cache:
            got = cache[key]
            stat["cached"] += 1
        else:
            got = nist_cas(key, a.pause)
            cache[key] = got
            time.sleep(a.pause)
            json.dump(cache, open(CACHE, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        cas, status = got
        if status.startswith("error"):
            stat["error"] += 1
        out[name] = {"nist": cas or "", "nist_status": status}
        if i and i % 50 == 0:
            print("   %d/%d  %s" % (i, len(names), stat))

    json.dump(out, open(os.path.join(REOUT, "cas_nist_raw.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # compare against PubChem
    pub = json.load(open(os.path.join(REOUT, "cas_by_name.json"), encoding="utf-8"))
    pcas, rows = pub.get("cas", {}), pub.get("rows", {})
    agree, disagree, nist_only, pc_only, neither = [], [], [], [], []
    for name, rec in out.items():
        p = pcas.get(name, "")
        n = rec["nist"]
        if p and n:
            (agree if p == n else disagree).append((name, p, n, rows.get(name, 0)))
        elif n and not p:
            nist_only.append((name, n, rows.get(name, 0)))
        elif p and not n:
            pc_only.append((name, p, rows.get(name, 0)))
        elif not p and not n:
            neither.append((name, rows.get(name, 0)))

    merged = {}
    for name, rec in out.items():
        p, n = pcas.get(name, ""), rec["nist"]
        if p and n and p != n:
            merged[name] = {"cas": "", "pubchem": p, "nist": n,
                            "status": "disagree", "rows": rows.get(name, 0)}
        elif p:
            merged[name] = {"cas": p, "pubchem": p, "nist": n, "status": "agree"
                            if n == p else "pubchem-only",
                            "rows": rows.get(name, 0)}
        elif n:
            merged[name] = {"cas": n, "pubchem": "", "nist": n, "status": "nist-only",
                            "rows": rows.get(name, 0)}
        else:
            merged[name] = {"cas": "", "pubchem": "", "nist": "",
                            "status": "neither", "rows": rows.get(name, 0)}

    print()
    print("agree        %4d" % len(agree))
    print("disagree     %4d   <- not written; needs a decision" % len(disagree))
    print("NIST only    %4d   <- newly filled" % len(nist_only))
    print("PubChem only %4d" % len(pc_only))
    print("neither      %4d   <- stays blank" % len(neither))
    for name, p, n, k in sorted(disagree, key=lambda x: -x[3])[:25]:
        print("   %-34s pubchem %-12s nist %-12s (x%d)" % (name[:34], p, n, k))

    if a.apply:
        json.dump(merged, open(os.path.join(REOUT, "cas_cross.json"), "w",
                               encoding="utf-8"), ensure_ascii=False, indent=1)
        print("\n-> out/re整理/cas_cross.json")


if __name__ == "__main__":
    main()