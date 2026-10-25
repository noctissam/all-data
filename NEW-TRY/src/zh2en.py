# -*- coding: utf-8 -*-
"""
Translate systematic Chinese compound names into the English names PubChem indexes.

Why a translation layer at all
------------------------------
CAS is a priority-1 field and no paper prints it for most of these compounds, so it has
to come from a database. PubChem does not index Chinese names at all: the synonyms of
CID 31265 (ethyl hexanoate) contain no CJK whatsoever, and an autocomplete for 异戊醇
returns nothing. A Chinese name sent straight to PubChem simply does not resolve.

So the Chinese names are rendered into the English systematic name that PubChem does
index, and the CAS is then taken from that CID. The translation is rule-based, not a
lookup table, because Chinese systematic nomenclature IS a literal transliteration of the
English one:

    己酸乙酯   hexanoic acid + ethyl   ->  ethyl hexanoate
    2-戊酮     pentan-2-one            ->  2-pentanone
    1-丁醇     butan-1-ol             ->  1-butanol

Every result is still verified downstream by fill_cas.py, which round-trips the CAS back
through PubChem and insists it lands on the same CID. A translation that produced the
wrong structure would fail that check rather than contribute a wrong CAS.

What is deliberately not done
-----------------------------
Names that are not systematic - benzaldehyde as 苯甲醛 is fine, but a sample code or a
captured OCR fragment is not - are returned untranslated and reported. Guessing those
would put a confident wrong CAS into a priority-1 column.
"""

import re

# carbon-chain stem, chinese -> (english root, carbon count)
STEM = {
    "甲": ("meth", 1), "乙": ("eth", 2), "丙": ("prop", 3), "丁": ("but", 4),
    "戊": ("pent", 5), "己": ("hex", 6), "庚": ("hept", 7), "辛": ("oct", 8),
    "壬": ("non", 9), "癸": ("dec", 10),
    "十一": ("undec", 11), "十二": ("dodec", 12), "十三": ("tridec", 13),
    "十四": ("tetradec", 14), "十五": ("pentadec", 15), "十六": ("hexadec", 16),
    "十七": ("heptadec", 17), "十八": ("octadec", 18), "十九": ("nonadec", 19),
    "二十": ("eicos", 20), "二十一": ("heneicos", 21), "二十二": ("docos", 22),
}
# multi-character stems must be tried before single characters
STEM_KEYS = sorted(STEM, key=len, reverse=True)

# names that are already the standard English form in Chinese usage
DIRECT = {
    "苯甲醛": "benzaldehyde", "苯乙醇": "2-phenylethanol", "苯甲醇": "benzyl alcohol",
    "苯甲酸": "benzoic acid", "苯酚": "phenol", "甲酚": "cresol",
    "苯乙烯": "styrene", "苯": "benzene", "甲苯": "toluene", "二甲苯": "xylene",
    "糠醛": "furfural", "呋喃甲醛": "furfural", "糠醇": "furfuryl alcohol",
    "苯乙酮": "acetophenone", "香叶醇": "geraniol", "香茅醇": "citronellol",
    "橙花醇": "nerol", "金合欢醇": "farnesol", "芳樟醇": "linalool",
    "薄荷醇": "menthol", "蒎烯": "pinene", "柠檬烯": "limonene", "茴香脑": "anethole",
    "甲基叔丁基醚": "methyl tert-butyl ether", "异戊烷": "isopentane",
    "正己烷": "hexane", "环己烷": "cyclohexane", "环己酮": "cyclohexanone",
    "四氢呋喃": "tetrahydrofuran", "二氯甲烷": "dichloromethane",
    "三氯甲烷": "chloroform", "氯仿": "chloroform", "甲醇": "methanol",
    "乙醇": "ethanol", "异丙醇": "isopropanol", "正丙醇": "1-propanol",
    "异丁醇": "isobutanol", "叔丁醇": "tert-butanol", "正丁醇": "1-butanol",
    "异戊醇": "isoamyl alcohol", "正戊醇": "1-pentanol", "正己醇": "1-hexanol",
    "乙醚": "diethyl ether", "丙酮": "acetone", "乙醛": "acetaldehyde",
    "甲醛": "formaldehyde", "乙酸": "acetic acid", "甲酸": "formic acid",
    "草酸": "oxalic acid", "柠檬酸": "citric acid", "苹果酸": "malic acid",
    "乳酸": "lactic acid", "丙氨酸": "alanine", "苯丙氨酸": "phenylalanine",
    "蛋氨酸": "methionine", "苏氨酸": "threonine", "色氨酸": "tryptophan",
    "赖氨酸": "lysine", "谷氨酸": "glutamic acid", "缬氨酸": "valine",
    "亮氨酸": "leucine", "异亮氨酸": "isoleucine", "甘氨酸": "glycine",
    "尿素": "urea", "乙酰胺": "acetamide", "乙醚": "diethyl ether",
    "2-甲基丁醇": "2-methylbutanol", "3-甲基丁醇": "isoamyl alcohol",
    "正丙醇": "propan-1-ol", "异丙醇": "propan-2-ol",
    "叔丁醇": "2-methylpropan-2-ol", "正丁醇": "butan-1-ol",
    "异丁醇": "2-methylpropan-1-ol", "正戊醇": "pentan-1-ol",
    "正己醇": "hexan-1-ol", "正庚醇": "heptan-1-ol", "正辛醇": "octan-1-ol",
    "正壬醇": "nonan-1-ol", "正癸醇": "decan-1-ol",
    "正丙醛": "propanal", "正丁醛": "butanal", "异丁醛": "isobutyraldehyde",
    "正戊醛": "pentanal", "正己醛": "hexanal", "正庚醛": "heptanal",
    "正辛醛": "octanal", "丙烯醛": "acrolein", "巴豆醛": "crotonaldehyde",
    "肉桂醛": "cinnamaldehyde", "丁香醛": "eugenol", "香茅醛": "citronellal",
    "柠檬醛": "citral", "戊二醛": "pentanedial",
    "2-丁酮": "2-butanone", "2-戊酮": "2-pentanone", "3-戊酮": "3-pentanone",
    "2-己酮": "2-hexanone", "3-己酮": "3-hexanone", "2-庚酮": "2-heptanone",
    "3-庚酮": "3-heptanone", "2-辛酮": "2-octanone", "3-辛酮": "3-octanone",
    "4-甲基-2-戊酮": "4-methyl-2-pentanone", "乙酰乙酸乙酯": "ethyl acetoacetate",
    "乙酸乙酯": "ethyl acetate", "乙酸丁酯": "butyl acetate",
    "乙酸异丁酯": "isobutyl acetate", "乙酸甲酯": "methyl acetate",
    "乙酸乙酯": "ethyl acetate", "乳酸乙酯": "ethyl lactate",
    "DL-乳酸乙酯": "ethyl lactate",
    "苯乙酸乙酯": "ethyl phenylacetate", "苯甲酸甲酯": "methyl benzoate",
    "苯甲酸乙酯": "ethyl benzoate", "肉豆蔻酸乙酯": "ethyl myristate",
    "硬脂酸乙酯": "ethyl stearate", "软脂酸乙酯": "ethyl palmitate",
    "月桂酸乙酯": "ethyl laurate", "油酸乙酯": "ethyl oleate",
    "亚油酸乙酯": "ethyl linoleate", "亚麻酸乙酯": "ethyl linolenate",
    "安息香酸乙酯": "ethyl benzoate", "水杨酸甲酯": "methyl salicylate",
    "阿魏酸甲酯": "methyl ferulate", "咖啡酸乙酯": "ethyl caffeate",
    "香豆素": "coumarin", "黄樟素": "safrole", "丁香酚": "eugenol",
    "香芹酚": "carvacrol", "百里香酚": "thymol", "没食子酸": "gallic acid",
    "香兰素": "vanillin", "乙基麦芽酚": "ethyl maltol", "麦芽酚": "maltol",
    "乙酰基": "acetyl", "内酯": "lactone",
}

# 酯:  <acid>酸<alcohol>酯   ->  <alcohol-en> <acid-en>ate
# The acid part is read up to the LAST 酸 (ethyl hexanoate: 己酸乙酯).
ESTER_TAIL = re.compile(r"^(?P<acid>.+?)酸(?P<alc>[一-鿿]+?)酯$")
# 醛/醇/酮/酸/烷/烯 with an optional locant prefix
SIMPLE = [
    (re.compile(r"^(?P<n>\d+)?-?(?P<body>[一-鿿]+?)醛$"), "al"),
    (re.compile(r"^(?P<n>\d+)?-?(?P<body>[一-鿿]+?)醇$"), "ol"),
    (re.compile(r"^(?P<n>\d+)?-?(?P<body>[一-鿿]+?)酮$"), "one"),
    (re.compile(r"^(?P<n>\d+)?-?(?P<body>[一-鿿]+?)酸$"), "oic acid"),
    (re.compile(r"^(?P<n>\d+)?-?(?P<body>[一-鿿]+?)烷$"), "ane"),
    (re.compile(r"^(?P<n>\d+)?-?(?P<body>[一-鿿]+?)烯$"), "ene"),
    (re.compile(r"^(?P<n>\d+)?-?(?P<body>[一-鿿]+?)酚$"), "ol"),
]

# English tails. The carbonyl stems need the linking "an": the Chinese 己 is "hex",
# but the English is hexANoate / hexANol / hexANal / hexANone. Writing "hexoate" or
# "hexate" produces a word PubChem has never heard of, and the lookup fails silently
# rather than loudly - which is why this table exists.
#
# Methane is the exception and carries no linking vowel: methANol is methanol.
TAIL_EN = {
    "al": "anal", "ol": "anol", "one": "anone",
    "oic acid": "anoic acid", "ane": "ane", "ene": "ene",
}
# meth- takes the tails without the linker
METH_EN = {
    "al": "anal", "ol": "anol", "one": "anone",
    "oic acid": "anoic acid", "ane": "ane", "ene": "ene",
}
# eth- keeps "an" too (ethanol, hexanoate) but these two are named specially
ETH_SPECIAL = {"oic acid": "acetic acid", "al": "acetaldehyde"}
# 乙酸/醋酸 are acetic; the rest map to the stem directly
ACID_FIX = {"乙": "acetic acid", "甲": "formic acid"}


def stem_of(s):
    """
    Longest-matching carbon stem.

    Returns (english_root, chinese_key_matched) - note the root is the first element of
    the table entry, not the entry itself, since the table also stores a carbon count.
    """
    for k in STEM_KEYS:
        if s.startswith(k):
            return STEM[k][0], k
    return None


def alcohol_en(cn):
    """Chinese alkyl fragment -> english alkyl fragment for an ester."""
    if not cn:
        return None
    st = stem_of(cn)
    if not st:
        return None
    root, used = st[0], st[1]
    rest = cn[len(used):]
    if rest.startswith("异"):
        return "iso" + root + "yl"
    if rest.startswith("正") or rest == "":
        return root + "yl"
    if rest in ("基",):
        return root + "yl"
    return None


def translate(name):
    """Return the English systematic name, or None when it cannot be derived."""
    s = (name or "").strip()
    if not s:
        return None
    if s in DIRECT:
        return DIRECT[s]

    m = ESTER_TAIL.match(s)
    if m:
        acid_cn = m.group("acid")
        alc_cn = m.group("alc")
        a = alcohol_en(alc_cn)
        if a is None:
            return None
        if acid_cn in ACID_FIX:
            return "%s %s" % (a, "acetate" if acid_cn == "乙" else "formate")
        st = stem_of(acid_cn)
        if not st:
            return None
        root, used = st[0], st[1]
        rest = acid_cn[len(used):]
        if rest and rest != "酸":
            return None
        # ethanoate and methanoate are named acetate and formate
        if root == "eth":
            return "%s acetate" % a
        if root == "meth":
            return "%s formate" % a
        return "%s %sate" % (a, root + "ano")

    # a locant may sit in front: 2-戊酮, 3-甲基-2-戊酮
    loc = ""
    body = s
    m2 = re.match(r"^(\d+)-?(.*)$", s)
    if m2:
        loc, body = m2.group(1), m2.group(2)

    for rx, tail in SIMPLE:
        mm = rx.match(body)
        if not mm:
            continue
        inner = mm.group("body")
        # The locant group is optional in the pattern, so "己醛" leaves it unset; fall
        # back to the one stripped from the front of the whole name.
        n_here = mm.group("n") or loc
        st = stem_of(inner)
        if not st:
            return None
        root, used = st[0], st[1]
        rest = inner[len(used):]
        if rest and rest not in ("基",):
            return None
        # a locant with nothing in front of it means C-1 by convention
        if n_here == "1" and not loc and not inner[:len(used)]:
            n_here = None
        if rest and rest not in ("基",):
            return None
        n = n_here
        if tail == "oic acid" and not n:
            if root == "eth":
                return "acetic acid"
            if root == "meth":
                return "formic acid"
        if tail == "al" and not n:
            # An aldehyde with no locant is by definition at C-1, so it is named from
            # the stem directly: 己醛 is hexanal, not hex-1-al.
            return root + "anal"
        if tail == "oic acid" and root == "meth" and not n:
            return "formic acid"
        name_en = root + TAIL_EN[tail]
        return ("%s-%s" % (n, name_en)) if n else name_en
    return None
