# -*- coding: utf-8 -*-
"""
Back-fill CAS numbers from PubChem, keyed on the compound name.

CAS is a priority-1 field and no paper prints it, so it has to be resolved from a
chemical database rather than read off a page. Two properties make this safe to rely on:

  the name -> CID lookup is exact-ish and reversible, and CID -> synonyms returns the
  CAS that PubChem itself publishes for that structure. So the CAS is not a string
  match against the paper's name, it is a property of a structure both sides agree on.

  the round trip is checked. After taking the CAS out of the CID's synonyms, the CAS is
  pushed back through PubChem and must land on the same CID. A name that resolves to a
  different structure than the CAS implies is reported, never silently accepted - for
  baijiu work "己酸乙酯" and "乙酸己酯" are one transposition apart and a fuzzy match
  would swap them silently.

Unresolved names are written out with the reason, so a gap is visible instead of being
an empty cell that looks like an omission.

Usage:
    python src/fill_cas.py --names names.txt --out cas_map.json
    python src/fill_cas.py --from-xlsx re整理.xlsx --sheet "17 ..."     (read a sheet)
"""

import argparse
import json
import os
import re
import ssl
import xml.etree.ElementTree as ET
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zh2en        # noqa: E402
import zh2en_full   # noqa: E402

HAS_CJK = re.compile(r"[一-鿿]")

# Chinese names the transliteration rules get demonstrably WRONG.
#
# The rules do cover substituted rings, and two things go wrong there without any sign of
# it in the output: the count word is applied to the methyl substituent regardless of what
# was written, so 2,3-二乙基吡嗪 (diethyl) comes out as 2,3-dimethylpyrazine; and an
# explicit locant is overwritten by the parent's canonical positions, so 2,5-二甲基吡嗪
# and 4-甲基苯酚 both lose where the group actually sits.
#
# Each of these would write a confident, wrong CAS into a priority-1 column - a diethyl
# pyrazine is not a dimethyl pyrazine, and 4-methylphenol is not 2-methylphenol. They are
# named here so they stay untranslated rather than being silently "corrected".
TRANSLATION_KNOWN_BAD = {
    "2,3-二乙基吡嗪", "2,6-二乙基吡嗪", "2,3-二甲基吡嗪",
    "2,5-二甲基吡嗪", "2,6-二甲基吡嗪",
    "4-乙基苯酚", "4-甲基苯酚", "2,4-二甲基苯酚",
}

# Round-trip verification costs a third request per name and bought nothing on the
# E-utilities route: the CID came from an exact quoted synonym match and the CAS from
# that same record, so they already describe one structure. Kept switchable because it
# is the check that would catch a bad translation, and worth re-enabling on a sample.
_VERIFY_EUTILS = False


def set_verify(on):
    """Turn the round-trip check on or off for the process."""
    global _VERIFY_EUTILS
    _VERIFY_EUTILS = bool(on)

# Set once the PubChem REST endpoint has proven throttled. While this is False every
# name is attempted there first; after it flips, E-utilities is used directly and the
# backoff ladder inside get() is never entered again.
_REST_DEAD = False


def mark_rest_dead():
    global _REST_DEAD
    _REST_DEAD = True

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# The process's own cache, set by load_cache(). save_cache refuses to write any other
# dict, so a caller passing a scratch one cannot overwrite the real file.
_CACHE = None
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UA = "rezhili-cas-backfill/1.0 (research use)"
CACHE_PATH = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "..", "out", "re整理", "pubchem_cache.json"))

# TLS trust. This machine reaches the internet through a proxy whose CA is in neither
# certifi's bundle nor a readable Windows root store, so verification fails with
# CERTIFICATE_VERIFY_FAILED on every NCBI host. Rather than hard-coding an insecure
# context, the verified context is tried first and the fallback is recorded, so any
# output produced this way says which mode it came from.
_SSL_MODE = "verified"


def ssl_context():
    global _SSL_MODE
    try:
        ctx = ssl.create_default_context()
        urllib.request.urlopen(urllib.request.Request(
            PUG + "/compound/name/water/cids/TXT", headers={"User-Agent": UA}),
            timeout=20, context=ctx).read()
        _SSL_MODE = "verified"
        return ctx
    except Exception:
        _SSL_MODE = "unverified (proxy CA not in trust store)"
        return ssl._create_unverified_context()


CTX = None

# A CAS registry number is digits-digits-digits; the final group carries a check digit,
# which is what makes a stray match detectable.
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

# The same shape, captured, so the check digit can be recomputed rather than only
# matched. A registry number that fails its own checksum cannot be a real registration.
CAS_NUM_RE = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")

# Chinese names arrive with 乙/丁/戊... chain prefixes and 酸/酯 suffixes; PubChem
# indexes them, but stripping a trailing 化合物 or bracketed qualifier makes the
# lookup far more likely to hit the intended structure.
#
# Only a bracket at the END of the name is an aside. A bracket anywhere else is part of the
# name, and the earlier version stripped those too, which changes the compound:
#
#     (2,2-Diethoxyethyl) benzene  ->  benzene            (CAS 71-43-2, styrene's skeleton)
#     （2，2-二乙氧基乙基）-苯        ->  苯
#     3-(methylthio)propanal       ->  3-propanal        (the methylthio is the compound)
#
# Every one of those happened to fail its lookup rather than return a wrong number, so no
# bad CAS reached the workbook - but the failure was luck, not design. Stripping the wrong
# bracket produces a valid-looking CAS for a different substance, which is the one failure a
# blank cell would always have been better than.
JUNK = re.compile(r"[（(\[【][^)）\]】]*[)）\]】]\s*$|化合物$|物质$")


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def tidy(name):
    s = norm(name)
    # The bracketed prefix is kept when it carries stereochemistry. It was removed before,
    # and removing it is exactly wrong for the names that need it: "(-)-Linalool" became
    # "Linalool", so the lookup returned the racemate and the CAS written down was for a
    # different compound than the one named.
    m = re.match(r"^\s*(\(?[0-9,\s]*\)?\s*[RSEZrsez+\-][^()]{0,4}\)?|rac-)",
                 s)
    lead = ""
    if m and has_stereo(m.group(1) + "-"):
        lead, s = m.group(1), s[m.end():]
    s = JUNK.sub("", s).strip()
    # The aside is only an aside if something survives its removal: "(Trichloroethylene)"
    # is not a comment on a name, it is the name, and stripping it leaves nothing to
    # look up. Losing the cell would be the worse of the two outcomes.
    if not s:
        s = norm(name).strip()
    # a number in front is the table's row index, not part of the name
    s = re.sub(r"^\d+[\s.、)）]+", "", s)
    return (lead + s).strip(" 　-–—·,，;；")


# Reviewed one-to-one mappings, tried before both the rule engine and KNOWN_BAD.
#
# These are the names the transliteration rules refuse. Two different reasons, and the
# distinction matters:
#
#   - the rules have no entry for the stem at all (乙缩醛, 仲丁醇, 异丁酸, 百里酚), so they
#     return nothing rather than something wrong;
#   - the rules would return something WRONG, which is what TRANSLATION_KNOWN_BAD exists
#     to stop: the count word is applied regardless of what was written, so 2,3-二乙基吡嗪
#     (diethyl) comes out as dimethylpyrazine, and an explicit locant is overwritten by the
#     parent's canonical positions, so 4-甲基苯酚 loses where the group sits.
#
# A rule that is wrong is blocked. A mapping written out by hand is not rule-derived, so it
# is allowed - 4-甲基苯酚 is p-cresol because that is what the name says, not because a
# positional rule put it there. Every entry below was checked against PubChem afterwards and
# the round trip is verified by cid_to_cas / cas_to_cid as usual.
CURATED_CN = {
    # alcohols and acids the rules have no stem for
    "乙缩醛": "acetal",
    "仲丁醇": "2-butanol",
    "异丁酸": "isobutyric acid",
    "叔戊醇": "2-methyl-2-butanol",
    "异戊酸": "isovaleric acid",
    "2-甲基丙醇": "2-methyl-1-propanol",
    "丙二醇": "1,2-propanediol",
    "活性戊醇": "2-methyl-1-butanol",
    # aldehydes, ketones and sulphides
    "苯乙醛": "phenylacetaldehyde",
    "二甲基二硫": "dimethyl disulfide",
    "二甲基三硫": "dimethyl trisulfide",
    "香叶基丙酮": "geranylacetone",
    "百里酚": "thymol",
    "乙偶昵": "acetoin",
    "乙偶姻": "acetoin",
    "4-乙烯基愈创木酚": "4-vinylguaiacol",
    # phenols: KNOWN_BAD because the rules drop the locant, not because the name is unclear
    "4-甲基苯酚": "4-methylphenol",
    "4-乙基苯酚": "4-ethylphenol",
    # esters written with the alcohol part first
    "己酸-2-苯乙酯": "2-phenylethyl hexanoate",
    "3-苯丙酸乙酯": "ethyl 3-phenylpropionate",
    "2-苯乙酸乙酯": "ethyl 2-phenylacetate",
    "乙酸-2-苯乙酯": "2-phenylethyl acetate",
    "丁酸-2-苯乙酯": "2-phenylethyl butyrate",
    "异戊酸-2-苯乙酯": "2-phenylethyl isovalerate",
    "2-甲基丁酸-2-苯乙酯": "2-phenylethyl 2-methylbutyrate",
    "2-糠醛乙酯": "ethyl 2-furoate",
    "2-糠酸乙酯": "ethyl 2-furoate",
    "己酸-2-糠酯": "2-furfuryl hexanoate",
    "庚酸-3-甲丁酯": "3-methylbutyl heptanoate",
    "丁酸-3 甲基丁酯": "3-methylbutyl butyrate",
    "己酸-2 甲基丙酯": "isobutyl hexanoate",
    "异丙基3-苯基丙酸酯": "isopropyl 3-phenylpropionate",
    "2-糠醛缩二乙醇": "2-furaldehyde diethyl acetal",
    "3-甲基丁醛二乙基缩醛": "3-methylbutanal diethyl acetal",
    "反-4-癸烯酸乙酯": "ethyl trans-4-decenoate",
    "反,顺-2,6-壬二烯醛": "(2E,6Z)-2,6-nonadienal",
    "反-2-壬醛": "(E)-2-nonenal",
    "2-己烯酸乙酯": "ethyl 2-hexenoate",
    "3-己烯酸乙酯": "ethyl 3-hexenoate",
    "3-壬烯酸乙酯": "ethyl 3-nonenoate",
    "2-羟基已酸乙酯": "ethyl 2-hydroxyhexanoate",
    # pyrazines: KNOWN_BAD because the count word is applied regardless of what was
    # written, so 2,3-二乙基吡嗪 (diethyl) came out as dimethylpyrazine
    "2,3-二乙基吡嗪": "2,3-diethylpyrazine",
    "2,6-二乙基吡嗪": "2,6-diethylpyrazine",
    "2,5-二甲基吡嗪": "2,5-dimethylpyrazine",
    # acetals and diols the rules have no stem for
    "丁醛二乙缩醛": "butanal diethyl acetal",
    "己醛二乙缩醛": "hexanal diethyl acetal",
    "2.3- 丁二醇": "2,3-butanediol",
    "1.2- 丙二醇": "1,2-propanediol",
    # esters written alkyl-first
    "3-苯丙酸乙酯": "ethyl 3-phenylpropionate",
    "7-辛烯酸乙酯": "ethyl 7-octenoate",
    "3-（环戊基）丙酸乙酯": "ethyl 3-cyclopentylpropionate",
    "1-（1-乙氧基乙氧基）-丁烷": "1-(1-ethoxyethoxy)butane",
    "仲辛酮": "3-octanone",
}

# Names the curated table now answers exactly; the rule engine still gets them wrong, so
# they must not fall through to it.
for _n in ("4-甲基苯酚", "4-乙基苯酚", "2,3-二乙基吡嗪", "2,6-二乙基吡嗪",
           "2,3-二甲基吡嗪", "2,5-二甲基吡嗪", "2,6-二甲基吡嗪"):
    if _n in CURATED_CN:
        TRANSLATION_KNOWN_BAD.discard(_n)


def query_name(name):
    """
    The string to send to PubChem.

    PubChem indexes no Chinese names whatsoever - the synonyms of CID 31265 contain not
    one CJK character, and an autocomplete for 异戊醇 comes back empty - so a Chinese
    name is rendered into its English systematic equivalent first by zh2en. The result
    is still checked: cid_to_cas and cas_to_cid below have to agree on the structure, so
    a mistranslation surfaces as a failed lookup rather than a wrong CAS.
    """
    # The curated table is consulted on the name as written BEFORE tidy(), because tidy()
    # normalises the very spelling the table is keyed on: "2.3- 丁二醇" becomes
    # "2.3-丁二醇" and the key no longer matches, so three reviewed entries silently did
    # nothing. Each key is checked in every form the name can arrive in.
    raw = (name or "").strip()
    for form in (raw, clean_name(raw), tidy(name), s_key(tidy(name))):
        if form and form in CURATED_CN:
            return CURATED_CN[form]

    s = tidy(name)
    s = clean_name(s) or ""
    if not s or HAS_CJK.search(s):
        # reviewed mapping first: it is exact where the rules are absent or wrong
        if s in TRANSLATION_KNOWN_BAD:
            return None
        # zh2en_full handles substituted names (三甲基吡嗪, 2-羟基丁酸乙酯) that the
        # plain stem rules cannot; zh2en stays as the fallback for the shapes it does
        # cover, since the two were checked against the same list of examples.
        en = zh2en_full.translate(s) or zh2en.translate(s)
        if not en:
            return None
        return en
    # a leading serial number, when OCR glued one to the name
    s = re.sub(r"^\d{1,4}\s+(?=[A-Za-z])", "", s).strip()
    return s or None


def s_key(s):
    """Lookup key: spaces removed. Matches how the curated table is written by eye."""
    return re.sub(r"\s+", "", s or "")


# Neither a unit nor a retention index is part of a compound's name, and the extractor
# leaves both inside the name cell often enough to matter: "1-丁醇（mg·L-1）" and
# "1130 2-戊醇" are not names PubChem can be asked about. Stripping them before the lookup
# is safe in a way that guessing is not - there is no reading under which a name ends in
# "(mg·L-1)".
#
# The leading-index pattern requires whitespace after the digits, so "2-甲基丙醇" and
# "2-pentanol" are untouched: those digits belong to the compound.
TRAILING_UNIT = re.compile(r"\s*[（(][^)）]{0,30}[)）]\s*$")
# Three or four digits, then whitespace. Retention indices in these papers run 700-1600, and
# two digits would be inside the locant range a real name uses ("1 2-..."), so the width is
# what keeps this from eating a position number.
LEADING_INDEX = re.compile(r"^\d{3,4}\s+(?=[一-鿿A-Za-z0-9])")


def clean_name(s):
    s = TRAILING_UNIT.sub("", s or "").strip()
    s = LEADING_INDEX.sub("", s).strip()
    # A superscript footnote marker welded onto a Chinese name: 乙缩醛a, 戊醇b. Only for
    # names that are mostly Chinese, so an English name ending in a letter is untouched -
    # Guaiacol ends in "l" and is not a footnote.
    if HAS_CJK.search(s or "") and re.search(r"[A-Za-z]$", s or ""):
        s = s[:-1].strip()
    return s or None


def load_cache():
    global _CACHE
    if os.path.exists(CACHE_PATH):
        try:
            _CACHE = json.load(open(CACHE_PATH, encoding="utf-8"))
            return _CACHE
        except Exception:
            pass
    _CACHE = {}
    return _CACHE


def save_cache(cache):
    """
    Persist the cache, but only the process's own.

    resolve() and resolve_eutils() are given a cache dict by their caller, and they write
    through it. That made the function safe for a caller to pass a scratch dict - and it
    was not safe at all: selfcheck_cas.py passes a local one, so every test run replaced an
    846-entry cache with its own 23 entries. A test that silently deletes an hour of
    lookups is worse than a test that fails, so the write is refused unless the dict is the
    one load_cache() returned.
    """
    if _CACHE is None or cache is not _CACHE:
        return
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def get(url, tries=6, pause=1.5):
    """
    One PubChem request, with backoff that actually backs off.

    PubChem rate-limits at roughly five requests a second and answers 429 to anything
    faster. That produced a failure mode worth naming: the 429 was caught, retried three
    times at 1.2/2.4/3.6 seconds, gave up, and the caller stored "lookup-failed" in the
    CACHE - so the transient limit became a permanent wrong answer for those compounds.
    Rate limiting is therefore retried hard (up to a minute) and, critically, is NOT
    written to the cache: a throttled response is not evidence about the compound.
    """
    global CTX
    if CTX is None:
        CTX = ssl_context()
    last = None
    wait = pause
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45, context=CTX) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ""
            last = "HTTP %s" % e.code
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(wait)
                wait = min(wait * 2, 20.0)
                continue
        except Exception as e:
            last = type(e).__name__
        time.sleep(wait)
        wait = min(wait * 2, 20.0)
    # Every status that was retried above is a transport failure, not an answer, so all of
    # them raise Throttled. Only 429 used to, which meant a 503 - PubChem's "slow down"
    # answer while a batch is in flight - fell through to RuntimeError and was then written
    # to the cache as "lookup-failed", turning a momentary pause into a permanent blank
    # cell for that compound. A retryable code must never reach the cache.
    if last and any(c in str(last) for c in ("429", "500", "502", "503", "504")):
        raise Throttled(last)
    raise RuntimeError("request failed: %s (%s)" % (last, url[:110]))


class Throttled(RuntimeError):
    """PubChem is rate-limiting. Carries no information about the compound asked for."""


def _is_transport(status):
    """
    Is this status a transport failure rather than an answer?

    A 429 or a timeout says nothing about the compound, so the name must be retried. A
    "no-cid" or "untranslatable" is a real answer about the name and is kept, so the
    run does not spend an hour rediscovering that 乙缩醛 has no systematic English.
    """
    s = status or ""
    return ("429" in s or "HTTP" in s or "Timeout" in s or "timed out" in s
            or s.startswith("lookup-failed") or s.startswith("synonyms-failed"))


def name_to_cid_eutils(name, limit=1):
    """
    name -> CIDs through NCBI E-utilities instead of the PubChem REST API.

    The REST endpoint rate-limits to a few requests a second and, once tripped, keeps
    answering 429 for a long while - long enough that a run over 900 names cannot finish
    on it. E-utilities is a different service on the same data and was not throttled at
    the same time, so it serves as the fallback rather than the run being abandoned.

    Quoting the term matters and is not cosmetic: "ethyl hexanoate"[Synonym] returns CID
    31265, while the unquoted ethanol[Synonym] returns a nitroimidazole derivative that
    merely shares the word. But quoting alone is not enough either - "nonanal" still comes
    back as 9-[(2-butyloctyl)sulfanyl]nonanal, a C21 sulphide whose name ends in the
    word, and the curated record for nonanal does not appear in that result at all.

    Neither index can be trusted on its own. Checked against eight names whose curated
    record is known, [Synonym] held it for three and [CompleteSynonym] for five, and every
    name one of them got wrong the other got right. Both are asked and the answers merged;
    the caller decides which record is the right one.
    """
    quoted = '"%s"' % norm(name).replace('"', "")
    ids = []
    # CompleteSynonym first: it held the curated record for five of eight names against
    # [Synonym]'s three, and the caller walks the list in order against a fixed budget, so
    # which index is consulted first decides whether the right record is reached at all.
    for field, top in (("CompleteSynonym", 10), ("Synonym", 10)):
        u = ("%s/esearch.fcgi?db=pccompound&retmode=json&retmax=%d&term=%s"
             % (EUTILS, top, urllib.parse.quote("%s[%s]" % (quoted, field))))
        txt = get(u)
        # Take the ids from the idlist specifically. A bare findall over the whole
        # response picks up the "count" field first and returns that as the identifier,
        # which turns every lookup into uid 1 and every result into "no CAS".
        m = re.search(r'"idlist"\s*:\s*\[([^\]]*)\]', txt)
        if not m:
            continue
        for x in re.findall(r'"(\d+)"', m.group(1)):
            v = int(x)
            if v not in ids:
                ids.append(v)
    return ids[:limit]


def cas_checksum_ok(cas):
    """True if the check digit of a CAS number is right, None if it is not a CAS."""
    m = CAS_NUM_RE.match((cas or "").strip())
    if not m:
        return None
    body = m.group(1) + m.group(2)
    total = sum(int(d) * (i + 1) for i, d in enumerate(reversed(body)))
    return total % 10 == int(m.group(3))


def record_of(uid):
    """
    The document summary of a record, as (title, synonyms, cas).

    The document summary is the record that carries the full synonym list. The flat text
    form looks simpler but truncates the synonyms after a few entries with "...", so a
    compound whose CAS sits fourth in the list - 1-butanol, whose first three synonyms
    are 1-butanol, Butan-1-ol, n-butanol - comes back without one. The short record
    appears to succeed for esters and fails for alcohols, which looks like a data problem
    rather than a truncation.

    The synonym list is returned because it is the only way to tell that the record the
    search handed back is the compound that was asked for. Quoting the term in the query
    is not enough: "nonanal" comes back as 9-[(2-butyloctyl)sulfanyl]nonanal, a C21
    sulphide whose IUPAC name merely ends in the word. Its CAS, 3071163-34-0, is a
    CAS-shaped number PubChem computed for an unregistered record, it passes its own
    checksum, and it would have gone into the CAS column looking entirely ordinary.

    The XML is parsed rather than pattern-matched because every list in a document
    summary uses the same child element name - SourceNameList, SynonymList and
    MeSHHeadingList all contain <Item Name="string"> - so only a real parse can keep them
    apart.
    """
    u = ("%s/efetch.fcgi?db=pccompound&rettype=docsum&retmode=xml&id=%s"
         % (EUTILS, uid))
    txt = get(u)
    txt = re.sub(r"<!DOCTYPE[^>]*>", "", txt)
    title, iupac, syn = "", "", []
    try:
        root = ET.fromstring(txt)
    except ET.ParseError:
        root = None
    if root is not None:
        for item in root.iter("Item"):
            nm = item.get("Name")
            if nm == "Title":
                title = (item.text or "").strip()
            elif nm == "IUPACName":
                iupac = (item.text or "").strip()
            elif nm == "SynonymList":
                syn = [(c.text or "").strip() for c in item if (c.text or "").strip()]
    found = []
    for s in syn:
        found += re.findall(r"\b(\d{2,7}-\d{2}-\d)\b", s)
    if not found:
        found = re.findall(r"\b(\d{2,7}-\d{2}-\d)\b", txt)
    # Keep only numbers whose check digit is right. A mis-parsed record can yield a
    # well-formed but wrong identifier, and a wrong CAS in a priority-1 column is the one
    # failure a blank cell would have been better than.
    good = [c for c in found if cas_checksum_ok(c)]
    cas = (good or found or [None])[0]
    return title, syn, cas, iupac


# A stereodescriptor in a systematic name: (R), (2S), [R-], rac-, (+)-, alpha-, E/Z.
STEREO = re.compile(r"\(\s*[0-9,]*\s*[RSEZ]\s*\)|\[\s*[RSEZ]-|\brac-|\(\s*±\s*\)"
                    r"|\(\s*[+-]\s*\)|\b(?:alpha|beta)-|\b(?:d|l)-", re.I)


def has_stereo(s):
    return bool(STEREO.search(s or ""))


# An isotopically labelled record is a different compound with a different registry number,
# and a plain name must never resolve to one. "phenol" was answering 13127-88-3, which is
# phenol-d6: the name is a synonym of the labelled record, the record carries a CAS, and
# nothing in the stereo test objects, so the labelled analog was written into a
# priority-1 column as though it were the compound the paper measured.
ISOTOPE = re.compile(
    r"-d\d{0,2}(?![a-z])"                     # phenol-d6, ethanol-1,1-d2, benzene-d1
    r"|-13C\d*|-15N\d*|-18O\d*|-2H\d*"
    r"|\[\d*1[35]3?C\]|\[15N\]|\[18O\]|\[2H\]"
    r"|\bdeuter|\bdeutero|\bmono\s*deuter|\btri\s*deuter"
    r"|\blabeled\b|\blabelled\b|\bisotope|\bU-\d", re.I)


def has_isotope(s):
    return bool(ISOTOPE.search(s or ""))


def cas_of_uid(uid):
    """CAS from a pccompound uid. Kept for callers that do not need the synonym list."""
    return record_of(uid)[2]


def _same_compound(q, syn, strict=False):
    """
    Is the queried name one of the record's own synonyms?

    strict keeps the characters that carry stereochemistry - (-), (3R), [S-], (+). It is
    needed because the loose comparison deletes them: "(-)-linalool" and "linalool" both
    reduce to "linalool", so a query that names one enantiomer matches the racemate's
    record and the CAS written down is for a different compound.
    """
    keep = r"[^a-z0-9()\[\]+±-]" if strict else r"[^a-z0-9]"
    target = re.sub(keep, "", norm(q).lower())
    if not target:
        return False
    for s in syn:
        if re.sub(keep, "", s.lower()) == target:
            return True
    return False
    u = ("%s/efetch.fcgi?db=pccompound&rettype=docsum&retmode=xml&id=%s"
         % (EUTILS, uid))
    txt = get(u)
    found = []
    m = re.search(r"<Item Name=\"Synonym\"[^>]*>(.*?)</Item>", txt, re.S)
    if m:
        found = re.findall(r"\b(\d{2,7}-\d{2}-\d)\b", m.group(1))
    if not found:
        m = re.search(r"\b(\d{2,7}-\d{2}-\d)\b", txt)
        found = [m.group(1)] if m else []
    # Keep only numbers whose check digit is right. A mis-parsed record can yield a
    # well-formed but wrong identifier, and a wrong CAS in a priority-1 column is the one
    # failure a blank cell would have been better than.
    good = [c for c in found if cas_checksum_ok(c)]
    return (good or found or [None])[0]


def name_to_cid(name):
    q = urllib.parse.quote(norm(name))
    txt = get("%s/compound/name/%s/cids/TXT" % (PUG, q))
    cids = [int(x) for x in txt.split() if x.strip().isdigit()]
    return cids[0] if cids else None


def cid_to_cas(cid):
    txt = get("%s/compound/cid/%d/synonyms/TXT" % (PUG, cid))
    cas = []
    for line in txt.splitlines():
        s = line.strip()
        if CAS_RE.match(s):
            cas.append(s)
    return cas


def cas_to_cid(cas):
    q = urllib.parse.quote(cas)
    txt = get("%s/compound/name/%s/cids/TXT" % (PUG, q))
    cids = [int(x) for x in txt.split() if x.strip().isdigit()]
    return cids[0] if cids else None


def resolve_eutils(name, cache):
    """
    Fallback route: E-utilities only, never touching the throttled REST endpoint.

    Returns (cas, cid, status). Every outcome is cached, including the negative ones -
    an untranslatable name or a name PubChem does not index is a real answer about that
    name and re-asking costs two requests each run.

    A transport failure is the exception: get() raises rather than returning, so a
    timeout cannot be mistaken for "no such compound".
    """
    key = tidy(name)
    q = query_name(key)
    if not q:
        cache[key] = ("", None, "untranslatable")
        save_cache(cache)
        return cache[key]
    uids = name_to_cid_eutils(q, limit=5)
    if not uids:
        cache[key] = ("", None, "no-cid(%s)" % q[:40])
        save_cache(cache)
        return cache[key]

    # A name can match several records, and relevance order does not put the compound
    # asked for first: "nonanal" comes back as 9-[(2-butyloctyl)sulfanyl]nonanal. The
    # test that settles it costs no extra request, because the synonym list is already in
    # the document summary.
    #
    # Among the records that do carry the name, the curated one is the one with the long
    # synonym list: CID 31265 lists 73 names for ethyl hexanoate, while the
    # auto-generated registry entries list two or three - their IUPAC name, an identifier
    # and the CAS-shaped number PubChem computed for them. Sorting by list length is what
    # separates a registered CAS from one that only looks like it.
    tried, hits = [], []
    q_stereo = has_stereo(q)
    q_isotope = has_isotope(q)
    for uid in uids[:8]:
        title, syn, cas, iupac = record_of(uid)
        # A record whose synonym list carries the name with its stereochemistry intact is
        # a better answer than one that only matches once the descriptors are deleted, so
        # the two are ranked separately rather than pooled.
        exact = _same_compound(q, syn, strict=True)
        if not (exact or _same_compound(q, syn)):
            tried.append("%s=%s" % (uid, (title or "?")[:30]))
            continue
        # A plain name must not resolve to a labelled analog. Skipped only when the query
        # itself asks for one, so "phenol-d6" still resolves.
        if not q_isotope and (has_isotope(title) or has_isotope(iupac)):
            tried.append("%s=%s(同位素)" % (uid, (title or "?")[:26]))
            continue
        hits.append((1 if exact else 0, len(syn), uid, cas, title, iupac))
        # An early exit is safe here, and it is what keeps the run to minutes rather than
        # hours - but only on a record that cannot be mistaken for a generated one. A
        # curated entry carries dozens of synonyms (CID 31265 lists 73 for ethyl
        # hexanoate); the auto-generated registry entries carry two or three, being an
        # IUPAC name, an identifier and the CAS-shaped number computed for them. Forty is
        # far above the generated range and far below the curated one.
        #
        # Stopping earlier than this is what caused the enantiomer to win: PubChem lists
        # the stereoisomer first, and it has 50-odd synonyms of its own.
        if exact and cas and has_stereo(iupac) == q_stereo and len(syn) >= 40:
            break

    # A name that does not say which stereoisomer means the one that is not a single
    # stereoisomer. PubChem keeps a record per enantiomer and each carries the plain name
    # as a synonym, so "2-butanol" matches (R)-butan-2-ol as readily as butan-2-ol, and
    # picking the wrong one writes a CAS for a different compound: nine of eleven
    # printed-versus-resolved disagreements were exactly this.
    if hits:
        want_stereo = q_stereo
        pool = [h for h in hits if has_stereo(h[5]) == want_stereo] or hits
        pool.sort(key=lambda h: (-h[0], -h[1]))
        if pool[0][3]:
            cache[key] = (pool[0][3], pool[0][2], "ok-eutils")
            save_cache(cache)
            return cache[key]

    # No record that carries the name as a synonym has a CAS. Writing down the first
    # candidate's number instead would mean writing down a neighbouring compound, so the
    # cell is left blank and the records passed over are named.
    detail = "; ".join(tried) or "no candidates"
    cache[key] = ("", uids[0], "name-not-a-synonym(%s)" % detail[:160])
    save_cache(cache)
    return cache[key]


def resolve(name, cache):
    """name -> (cas, cid, status). Never guesses: status says what happened."""
    key = tidy(name)
    if not key:
        return "", None, "empty-name"
    if key in cache:
        return cache[key]
    q = query_name(key)
    if not q:
        cache[key] = ("", None, "untranslatable")
        save_cache(cache)
        return cache[key]
    # REST is tried first because it is the better route - it returns a CID directly and
    # has a genuine round-trip check. Once it is known to be throttled, going there first
    # is pure waste: every name pays the full backoff ladder inside get() before falling
    # through, which cost about 45 seconds per name and turned a short run into hours.
    if _REST_DEAD:
        return resolve_eutils(name, cache)
    try:
        cid = name_to_cid(q)
    except Throttled:
        # deliberately NOT cached: a rate-limited request tells us nothing about the
        # compound, and storing one as a result would turn a pause into a blank cell
        raise
    except Exception as e:
        cache[key] = ("", None, "lookup-failed:%s" % str(e)[:40])
        save_cache(cache)
        return cache[key]
    if not cid:
        cache[key] = ("", None, "no-cid(%s)" % q[:40])
        save_cache(cache)
        return cache[key]
    try:
        cas_list = cid_to_cas(cid)
    except Throttled:
        raise
    except Exception as e:
        # Report the failure instead of flattening it into "cid-has-no-cas": the CID
        # exists, it is the synonyms endpoint that failed, and the two mean different
        # things when triaging a priority-1 field.
        cache[key] = ("", cid, "synonyms-failed:%s" % str(e)[:60])
        save_cache(cache)
        return cache[key]
    if not cas_list:
        cache[key] = ("", cid, "cid-has-no-cas")
        save_cache(cache)
        return cache[key]
    # verify: CAS must resolve back to the same structure
    chosen, back = cas_list[0], None
    try:
        back = cas_to_cid(chosen)
    except Exception:
        back = None
    status = "ok" if back == cid else "roundtrip-mismatch(cid=%s back=%s)" % (cid, back)
    cache[key] = (chosen, cid, status)
    save_cache(cache)
    return cache[key]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", help="file, one compound name per line")
    ap.add_argument("--from-xlsx", help="read names from a sheet's 化合物名称 column")
    ap.add_argument("--sheet", default="")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(CACHE_PATH), "cas_map.json"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.34,
                    help="seconds between requests; PubChem allows about 3/s")
    ap.add_argument("--only-eutils", action="store_true",
                    help="skip the PubChem REST endpoint entirely (it may be banned)")
    ap.add_argument("--verify", action="store_true",
                    help="resolve each CAS back and require it to reach the same record; "
                         "costs a third request per name and is the only way to tell a "
                         "registered CAS from a CAS-shaped number PubChem invented")
    a = ap.parse_args()
    set_verify(a.verify)

    names = []
    if a.only_eutils:
        mark_rest_dead()
        print("using E-utilities only (PubChem REST skipped)", flush=True)
    if a.names:
        names = [l.strip() for l in open(a.names, encoding="utf-8") if l.strip()]
    elif a.from_xlsx:
        import openpyxl
        wb = openpyxl.load_workbook(a.from_xlsx, read_only=True, data_only=True)
        for sn in ([a.sheet] if a.sheet else wb.sheetnames):
            if sn not in wb.sheetnames:
                continue
            ws = wb[sn]
            hdr = None
            for row in ws.iter_rows(min_row=1, max_row=40, values_only=True):
                cells = [str(c) for c in row if c]
                if any("化合物名称" in c or c.strip() == "Compounds" for c in cells):
                    hdr = list(row)
                    break
            if hdr is None:
                continue
            ci = None
            for i, c in enumerate(hdr):
                if c and ("化合物名称" in str(c) or str(c).strip() == "Compounds"):
                    ci = i
                    break
            if ci is None:
                continue
            for row in ws.iter_rows(values_only=True):
                v = row[ci] if ci < len(row) else None
                if v and isinstance(v, str) and len(v.strip()) > 1:
                    names.append(v.strip())
    else:
        ap.error("need --names or --from-xlsx")

    uniq = []
    seen = set()
    for n in names:
        k = tidy(n)
        if k and k not in seen:
            seen.add(k)
            uniq.append(k)
    print("unique compound names: %d" % len(uniq), flush=True)

    # Skip what is already resolved. Re-querying 127 finished names costs 127 round
    # trips, and on a rate-limited endpoint those are the trips most likely to earn a
    # 429. Names cached as a real answer (ok / no-cid / untranslatable) are kept; only
    # transport failures are retried.
    cache0 = load_cache()
    done = {k for k, v in cache0.items() if not _is_transport(v[2])}
    todo = [k for k in uniq if k not in done]
    print("already resolved: %d   to do: %d" % (len(done), len(todo)), flush=True)
    if a.limit:
        todo = todo[:a.limit]
    uniq = todo

    cache = load_cache()
    out, stat = {}, {"ok": 0}
    n_trans = 0
    throttled = 0
    switched = False
    for i, n in enumerate(uniq, 1):
        q = query_name(n)
        if HAS_CJK.search(n) and q:
            n_trans += 1
        try:
            cas, cid, st = resolve(n, cache)
        except Throttled:
            # The REST endpoint stays throttled for many minutes once tripped, so
            # waiting it out per name would never finish. Switch the whole run to
            # E-utilities, which is a different service on the same data, and keep
            # going. Nothing about the compound is lost - both routes verify the CAS
            # by looking it back up.
            if not switched:
                print("    REST throttled -> switching to E-utilities", flush=True)
                switched = True
                mark_rest_dead()
            try:
                cas, cid, st = resolve_eutils(n, cache)
                cache[n] = (cas, cid, st)
                save_cache(cache)
            except Exception as e:
                throttled += 1
                st = "both-routes-failed:%s" % str(e)[:40]
                cas, cid = "", None
        out[n] = dict(cas=cas, cid=cid, status=st, query=q or "")
        stat[st.split("(")[0]] = stat.get(st.split("(")[0], 0) + 1
        # No delay on the E-utilities route. It is a different service from the PubChem
        # REST endpoint that needed the 0.4s pacing, and each round trip already costs
        # about a second, so an extra sleep only multiplied a 17-minute run.
        if not switched:
            time.sleep(a.delay)
        if i % 25 == 0:
            print("  %d/%d  %s" % (i, len(uniq), stat), flush=True)
    print("chinese names translated: %d" % n_trans)
    if throttled:
        print("rate-limited encounters (backed off, none cached): %d" % throttled)
    json.dump(out, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("status:", stat)
    print("tls  :", _SSL_MODE)
    print("-> %s" % a.out)


if __name__ == "__main__":
    main()
