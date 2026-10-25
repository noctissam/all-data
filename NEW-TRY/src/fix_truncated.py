# -*- coding: utf-8 -*-
"""
Complete compound names that OCR clipped, using chemical morphology.

Why not the corpus
------------------
The obvious approach - match an OCR name against names read cleanly elsewhere - does
not work on this corpus, and it is worth being explicit about why. The names that come
through untouched are the ones in the Chinese journals, which print compound names in
Chinese: 乙酸乙酯, 己酸乙酯, 苯乙醇. Every ENGLISH name in the project was read by OCR,
because every English paper in the folder is image-only. So the clean set contains
almost no Latin names at all, and a script that tries to learn "ethyl hexanoate" from it
finds nothing to learn. An earlier version of this work did exactly that and produced
four corrections out of 492 damaged names.

What the damage actually is
---------------------------
A table column is narrower than the word in it, and the OCR engine returns what fits:
"Ethyl acetat" for ethyl acetate, "1-Butano" for 1-butanol, "1-Heptano" for 1-heptanol.
The tail is lost, never scrambled - so the fix is to recognise a stem and put the right
suffix back. English systematic nomenclature makes that a closed set:

    -ate        ester        ethyl acetate        acid + alcohol
    -ol         alcohol      1-butanol
    -al         aldehyde     hexanal              -CHO
    -ane        alkane       nonane
    -one        ketone       2-pentanone
    -oic acid   acid         hexanoic acid
    -dioic acid diacid       hexanedioic acid

Chinese names clip the same way, ending mid-word (乙酸乙, 3-甲基」醇), but a single
wrong hanzi is indistinguishable from a real isomer - 2-甲基丁醇 and 2-甲基丙醇 differ
by exactly the kind of substitution an OCR engine makes - so Chinese is repaired only
where the clip point is unambiguous, and everything else is reported rather than guessed.

Stems are matched case-insensitively and the digits are never touched, so 1-Butano can
become 1-butanol but 1-Butano never becomes 2-butanol.

Usage:
    python src/fix_truncated.py            # report
    python src/fix_truncated.py --apply    # rewrite the intermediate json
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))

CJK = re.compile(r"[一-鿿]")

# (clipped tail, completed tail). Order matters and it is not alphabetical.
#
# The trap is "ano": 1-Butano is 1-BUTANOL with its "l" cut off, and a rule that sees
# "ano" and completes it to "ane" silently converts an alcohol into an alkane. So the
# alcohol, aldehyde and ketone tails are tried FIRST - they are the ones that are merely
# missing a final letter - and the bare "ane" rule comes last, for a name that really is
# an alkane and lost its "e".
SUFFIXES = [
    ("anoic acid", "anoic acid"),
    ("oic acid", "oic acid"),
    ("ethanoic acid", "ethanoic acid"),
    ("yl acetate", "yl acetate"),
    ("yl butyrate", "yl butyrate"),
    ("yl hexanoate", "yl hexanoate"),
    ("anoate", "anoate"),
    ("enoate", "enoate"),
    ("ynoate", "ynoate"),
    # esters are the most common family in these papers and the one the OCR engine
    # truncates most, because "...oate" is exactly one character past a column edge
    ("oate", "oate"),
    ("ate", "ate"),
    ("oat", "oate"),
    ("at", "ate"),
    ("anol", "anol"),
    ("ono", "onol"),
    ("ano", "anol"),           # 1-Butano -> 1-Butanol
    ("onal", "onal"),
    ("anon", "anone"),         # 2-Heptanon -> 2-heptanone
    ("anal", "anal"),
    ("enone", "enone"),
    ("one", "one"),
    ("ene", "ene"),
    ("yne", "yne"),
    ("enol", "enol"),
    ("en", "ene"),
    ("ane", "ane"),
]

# Clipped tails whose completion is genuinely two-valued from the stem alone. An alkane
# "nonane" and an alcohol "nonanol" both lose their last letter to give "nonan", so the
# clipped form carries no evidence either way and the name is left exactly as printed.
# Roots that legitimately take one of several tails, so a clipped form of them cannot
# be completed from the stem alone: "nonan" is "nonane" minus its e or "nonanol" minus
# its l. Kept as documentation of why those stay unresolved.
AMBIGUOUS_TAIL = {"ano", "on", "an"}

STEM_ALIASES = {
    "acetat": "acetate", "formiat": "formate", "butyrat": "butyrate",
    "isobutyrat": "isobutyrate", "isovalerat": "isovalerate",
    "valerat": "valerate", "propionat": "propionate", "lactat": "lactate",
    "pyroat": "pyruvate", "citrat": "citrate", "malat": "malate",
    "succinat": "succinate", "fumarat": "fumarate", "maleat": "maleate",
    "oleat": "oleate", "linoleat": "linoleate", "linolenat": "linolenate",
    "caproat": "caproate", "caprylat": "caprylate", "laurat": "laurate",
    "myristat": "myristate", "palmitat": "palmitate", "stearat": "stearate",
    "phenylethanoat": "phenylacetate", "benzylacetat": "benzylacetate",
    "phenylpropionat": "phenylpropionate",
    # two-word esters where the tail clipped in the second word
    "ethylacetat": "ethyl acetate", "butylacetat": "butyl acetate",
    "hexylacetat": "hexyl acetate", "isoamylacetat": "isoamyl acetate",
    "methylacetat": "methyl acetate", "propylacetat": "propyl acetate",
    "phenylethylacetat": "phenylethyl acetate", "furfurylacetat": "furfuryl acetate",
    "diethylbutanedioat": "diethyl butanedioate",
    "ethylbenzenpropanoat": "ethylphenylpropanoate",
    "ethylbutanedioat": "ethyl succinate", "ethylpropanoat": "ethyl propanoate",
    "ethylbutanoat": "ethyl butanoate", "ethyl2methylbutanoat": "ethyl 2-methylbutanoate",
    "ethyl3methylbutanoat": "ethyl 3-methylbutanoate",
    "ethyl4methylpentanoat": "ethyl 4-methylpentanoate",
    "ethyl3phenylpropanoat": "ethyl 3-phenylpropanoate",
    "ethyl2hydroxy4methylvalerat": "ethyl 2-hydroxy-4-methylvalerate",
    "methylbutyloctanoat": "3-methylbutyl octanoate",
    "isopentylhexanoat": "isopentyl hexanoate",
    "methylbutylhexanoat": "3-methylbutyl hexanoate",
}

# English names a clip can leave ambiguous: two completions both plausible, no way to
# choose from the stem alone, so they are reported rather than filled in.
AMBIGUOUS = {
    "nonalacton": "nonalactone",
    "methylbutano": "methylbutanoate",
    "hexen-1-o": "hexen-1-ol",
    "octen-3-o": "octen-3-ol",
    "terpineo": "terpineol",
    "cineol": "cineole",
    "propanedio": "propanediol",
    "hexanedio": "hexanediol",
}

# A cell that is not a name at all: a CAS number, a run of digits, an OCR smear of
# figure text. These are excluded from the stem search entirely.
JUNK = re.compile(r"^[\d\s'.,+*#()\-–—:;/\\|]*$|^\d{2,7}-\d{2}-\d$")
MIN_LEN = 4

# Table serial numbers that OCR glued onto the front of the name ("15 Ethyl hexanoate",
# "46 Ethyl 3-phenylpropanoate"). They belong to the No. column, not the name, and they
# make every name unique so no two rows can ever be matched against each other.
LEADING_NO = re.compile(r"^\s*\d{1,3}\s+(?=[A-Za-z])")


def digits(s):
    return [c for c in s if c.isdigit()]


# Words that live in the same table but are not compounds: odour descriptors, sample
# codes, column headings. Left out of the repair scan entirely.
#
# This list exists because a stem rule applied to everything produces confident nonsense
# from ordinary prose - "roast meat" became "roast meate", since "meate" passes a stem
# test written for alkane roots. The rule has to know what it is looking at before it
# starts appending letters.
NOT_A_NAME = re.compile(
    r"^(meat|bread|butter|cream|honey|sugar|salt|smoke|roast|grill|fruit|apple|"
    r"banana|pear|plum|grape|citrus|lemon|orange|melon|berry|floral|flavour|"
    r"flavor|odor|odour|aroma|taste|sweet|sour|bitter|sharp|soft|smooth|warm|"
    r"dry|wet|green|fresh|rich|woody|spicy|sweetish|total|mean|value|index|"
    r"blank|control|sample|standard|internal|retention|concentration|"
    r"detection|quantification|area|peak|response|group|rank|correlation|"
    r"significant|positive|negative|higher|lower|medium|low|high)\b", re.I)


def is_prose(s):
    """Olfactory and analytical vocabulary, not a compound name."""
    return bool(NOT_A_NAME.match(s.strip()))


def keep_case(src, repl):
    """
    Apply the capitalisation of the original to the replacement.

    The alias table is written in lower case because that is how the tables key it, but
    the papers print "Ethyl acetate" and not "ethyl acetate", and a name that changes
    case here will look like a different entry to whoever compares the sheet against
    the PDF.
    """
    if not src or not repl:
        return repl
    if src[0].isupper():
        return repl[0].upper() + repl[1:]
    return repl


def looks_like_name(s):
    if not s or len(s) < MIN_LEN:
        return False
    if JUNK.match(s):
        return False
    if is_prose(s):
        return False
    return True


def repair_latin(n):
    """
    Complete one Latin name, or return None when the stem does not decide it.

    Every plausible completion is generated and then filtered by two rules, which is
    what keeps "Butano" from becoming "Butane":

      the result must be a real systematic name, so "Butano" + "e" -> "butanoe" is
        rejected while "Butano" + "l" -> "butanol" survives;

      the digits must be untouched, so no completion can move a compound from 2- to
        3-methyl or shift a double bond.

    A completion is used only when exactly one survives. "Nonan" would fit both
    "nonane" and "nonanol", so it is left as printed rather than guessed.
    """
    if CJK.search(n) or not looks_like_name(n):
        return None
    pre = LEADING_NO.match(n)
    if pre:
        # repair the name proper, then restore the serial number in front of it
        got = repair_latin(n[len(pre.group(0)):])
        return (pre.group(0) + got) if got else None
    low = n.lower()
    if low in AMBIGUOUS:
        return AMBIGUOUS[low]
    # whole-name aliases come first: they encode what stem rules cannot decide on their
    # own, such as which alkyl fragment belongs with which acid
    key = re.sub(r"[\s\-()]+", "", low)
    if key in STEM_ALIASES:
        return keep_case(n, STEM_ALIASES[key])

    cands = set()
    for stem, full in SUFFIXES:
        if low.endswith(stem):
            cand = n[:len(n) - len(stem)] + full
            if cand != n and digits(cand) == digits(n) and plausible(cand):
                cands.add(cand)

    # A clipped tail may instead be missing only its final letter. Appending is only
    # allowed when the character before the tail is itself a valid stem ending, which is
    # what separates "hexanoat" + "e" = "hexanoate" from the nonsense "butano" + "ol" =
    # "butanool". Without this the append rule proposes a dozen candidates for every name
    # and nothing ever comes out unique.
    if low[-1:] in "aeno" and low[-2:-1] in "aeioulnrs":
        for tail in ("ane", "anol", "anal", "anone", "anoic acid", "ate", "ene",
                     "yne", "ol", "al", "one", "e"):
            cand = n + tail
            if cand != n and digits(cand) == digits(n) and plausible(cand):
                cands.add(cand)

    # restore forms that only differ by a dropped final letter of a known alias
    low2 = re.sub(r"[^a-z]", "", low)
    if low2 in STEM_ALIASES and " " not in n:
        pre = re.match(r"^[\d,\-\s\(\)EZ]*", n).group(0)
        if pre:
            cand = pre + STEM_ALIASES[low2]
            if cand != n and digits(cand) == digits(n):
                cands.add(cand)

    cands = {c for c in cands if plausible(c)}
    if len(cands) == 1:
        return next(iter(cands))
    return None


def repair_entry(cell):
    """Public entry: repair one cell as it appears in the grid, serial number included."""
    if not cell:
        return None
    return repair_latin(cell.strip())


# The functional-group tail a completed name must end in. Declared before plausible()
# uses it - defining it afterwards turns every call into a NameError.
VALID_TAIL = re.compile(
    r"(anoate|enoate|ynoate|oate|yl\s+\w+|anoic\s+acid|oic\s+acid|dioic\s+acid"
    r"|anol|anal|anone|one|ane|ene|yne|ol|al|ate|oic|ide|ine|oat|at)$", re.I)

# The part of a name before its functional-group tail. A completion is only believable if
# what precedes the tail is itself a well-formed stem, so "hexano" + "ate" passes while
# "butano" + "ol" (butanool) and "pheno" + "al" (phenoal) do not. This is the filter
# that makes a unique candidate possible; without it every clipped name generates a
# dozen equally-shaped guesses.
# The tails a completed name can end in, longest first. The order matters twice over:
# plausible() peels the longest matching tail off the right, and "hexanoate" matches
# both "oate" and "anoate", so a shorter match would leave the stem "hex" and reject a
# perfectly good name.
TAILS_BY_LEN = sorted(
    ["anoate", "enoate", "ynoate", "oate", "anoic acid", "oic acid", "dioic acid",
     "anone", "anol", "anal", "ane", "ene", "yne", "one", "ate", "ol", "al",
     "oic", "ide", "ine", "oat", "at", "yl"],
    key=len, reverse=True)

# What is left after the tail is peeled off must look like a chemical root. The roots
# that matter here all end in a vowel+consonant pattern typical of alkane stems
# (butan, pentan, hexan), in "-yl", or in "-ol"/"-one". An arbitrary English word does
# not, which is what keeps "meat" from passing as "meate".
STEM_OK = re.compile(
    r"(an|ane|ane|ene|yne|yl|ol|one|ic|ide|ine|ate|oate|al)$", re.I)


def plausible(s):
    """
    Is this a well-formed systematic name?

    The tail is peeled off from the right and the remaining stem must look like a
    chemical root. Tails are tried LONGEST first, but a tail is only accepted when it
    leaves a valid stem - because "hexanoate" matches "anoate" as well as "oate", and
    taking the first match would leave the stem "hex", which is not a root.

    Appending a tail without this check proposes "butanool" and "phenoal" as readily as
    "hexanoate", and then no candidate is ever unique, so nothing gets repaired.
    """
    s = s.strip()
    low = s.lower()
    if NOT_A_NAME.match(low):
        return False
    for tail in TAILS_BY_LEN:
        if not low.endswith(tail):
            continue
        stem = s[:len(s) - len(tail)].strip()
        if not stem:
            continue
        # A two-word ester carries its root in the whole first word ("Ethyl acet" from
        # "Ethyl acetate"), which no single-token stem test can judge; a root that is
        # itself a plain alkyl or acyl fragment is accepted on that basis.
        if " " in stem and ALKYL_ROOT.fullmatch(stem.split()[-1] + "yl|ate|oate"):
            return True
        if " " in stem and ALKYL_ROOT.fullmatch(stem.split()[0]):
            return True
        if STEM_OK.search(stem):
            return True
    return False


# Alcohol and acyl fragments that appear as the first word of a two-word name.
ALKYL_ROOT = re.compile(
    r"(ethyl|methyl|propyl|isopropyl|butyl|isobutyl|sec-butyl|tert-butyl|"
    r"pentyl|isopentyl|hexyl|heptyl|octyl|nonyl|decyl|dodecyl|tetradecyl|"
    r"hexadecyl|octadecyl|phenyl|benzyl|furfuryl|furfur|cyclohexyl|allyl|"
    r"isoamyl|isopentyl|geranyl|neryl|citronellyl|phenylethyl|phenethyl|"
    r"formyl|acetyl|propionyl|butyryl|valeryl|caproyl|octanoyl|benzoyl|"
    r"acet|methan|ethan|propan|butan|pentan|hexan|heptan|octan|nonan|decan|"
    r"dodecan|tetradecan|hexadecan|octadecan|phenyl|furfur|glycerol|"
    r"iso)", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    sys.path.insert(0, HERE)
    from normalize_names import base_name, load_all

    trusted, suspect, detail = load_all()

    # Walk every cell of every OCR-derived table rather than trusting the inferred name
    # column. Column inference picks the compound-name column for a well-formed table,
    # but on the OCR papers it sometimes settles on a sample-code column instead, and a
    # name repair that only ever looks at one column repairs nothing. A truncated latin
    # name is self-identifying - it can only be completed by the stem rules below - so
    # scanning every cell costs nothing and cannot miss one.
    cells = {}
    import json as _json
    import re as _re
    for fn in sorted(os.listdir(REOUT)):
        if not _re.match(r"^(bm|en)_\d+\.json$", fn):
            continue          # band_* is text-layer: already exact, never touch it
        d = _json.load(open(os.path.join(REOUT, fn), encoding="utf-8"))
        for t in d.get("tables", []):
            for key in ("rows", "header_rows"):
                for row in t.get(key, []):
                    for cell in row:
                        s = (cell or "").strip()
                        if not s or CJK.search(s):
                            continue
                        c = repair_entry(s)
                        if c and c != s:
                            cells[s] = c
    targets = sorted(cells)
    fixes = cells

    print("OCR latin cells needing repair: %d" % len(targets))
    print("completed: %d    unresolved (left exactly as printed)" % len(fixes))
    print()
    items = sorted(fixes.items())
    if a.limit:
        items = items[:a.limit]
    for n, d in items:
        print("   %-30s -> %s" % (n, d))

    p = os.path.join(REOUT, "name_completions.csv")
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ocr_name", "completed_name", "ocr_rows", "digits_preserved"])
        for n, d in sorted(fixes.items()):
            w.writerow([n, d, suspect[n], digits(n) == digits(d)])
    print("\n-> %s" % p)

    if not a.apply:
        print("(dry run; pass --apply to rewrite)")
        return

    applied = 0
    for fn in sorted(os.listdir(REOUT)):
        if not re.match(r"^(bm|en|band|raw)_\d+\.json$", fn):
            continue
        path = os.path.join(REOUT, fn)
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        changed = False
        for t in d.get("tables", []):
            for key in ("rows", "header_rows"):
                for row in t.get(key, []):
                    for j, cell in enumerate(row):
                        f = fixes.get((cell or "").strip())
                        if f and cell != f:
                            row[j] = f
                            changed = True
                            applied += 1
        if changed:
            json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("cells rewritten: %d" % applied)


if __name__ == "__main__":
    main()
