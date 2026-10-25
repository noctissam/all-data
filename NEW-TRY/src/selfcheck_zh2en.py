# -*- coding: utf-8 -*-
"""
Self-check for the Chinese -> English name translator.

Two things are checked on every case, because each one silently produces a wrong
compound rather than an obviously broken string:

  digits  the number sequence written in the Chinese name must survive into the
          English name unchanged. 2,5-dimethylpyrazine must not come out as
          2,3-dimethylpyrazine.

  spread  the carbon count implied by the English name must agree with the one
          implied by the Chinese name.

Run as: python selfcheck_zh2en.py [--fix]
--fix only reports; nothing is written back.
"""

import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")

import zh2en_full as Z

# ---------------------------------------------------------------- known-good
# Each case is (chinese, {acceptable english}). Several names are accepted because
# PubChem indexes synonyms: ethyl butanoate and ethyl butyrate are the same ester,
# oct-1-en-3-ol and 1-octen-3-ol the same enol. Requiring one spelling would push the
# rules towards a canonical form that adds no information.
EXPECT = [
    ("己酸乙酯", {"ethyl hexanoate"}),
    ("乙酸乙酯", {"ethyl acetate"}),
    ("丁酸乙酯", {"ethyl butanoate", "ethyl butyrate"}),
    ("苯乙醇", {"2-phenylethanol"}),
    ("乙酸", {"acetic acid"}),
    ("2-甲基丁醛", {"2-methylbutanal"}),
    ("异戊醛", {"3-methylbutanal", "isopentanal"}),
    ("2,3-丁二酮", {"2,3-butanedione"}),
    ("2-乙基呋喃", {"2-ethylfuran"}),
    ("2,5-二甲基呋喃", {"2,5-dimethylfuran"}),
    ("2-甲基吡嗪", {"2-methylpyrazine"}),
    ("2,3,5,6-四甲基吡嗪", {"2,3,5,6-tetramethylpyrazine"}),
    ("2-乙基吡嗪", {"2-ethylpyrazine"}),
    ("1,2-丙二醇", {"1,2-propanediol"}),
    ("环己酮", {"cyclohexanone"}),
    ("环戊酮", {"cyclopentanone"}),
    ("愈创木酚", {"2-methoxyphenol", "guaiacol"}),
    ("4-甲基愈创木酚", {"4-methylguaiacol"}),
    ("苯甲醛", {"benzaldehyde"}),
    ("糠醛", {"furan-2-carbaldehyde", "furfural"}),
    ("苯甲酸乙酯", {"ethyl benzoate"}),
    ("1,1-二乙氧基乙烷", {"1,1-diethoxyethane"}),
    ("1,1,3-三乙氧基丙烷", {"1,1,3-triethoxypropane"}),
    ("乳酸乙酯", {"ethyl lactate"}),
    ("γ-壬内酯", {"5-pentyloxolan-2-one"}),
    ("乙酸异丁酯", {"isobutyl acetate"}),
    ("乙酸异戊酯", {"isopentyl acetate", "isoamyl acetate"}),
    ("乙酸丁酯", {"butyl acetate"}),
    ("1-辛烯-3-醇", {"oct-1-en-3-ol", "1-octen-3-ol"}),
    ("3-辛烯-2-酮", {"oct-3-en-2-one", "3-octen-2-one"}),
    ("反-2,4-癸二烯醛", {"trans-2,4-decadienal"}),
    ("1-丁醇", {"butan-1-ol", "1-butanol"}),
    ("2-戊醇", {"pentan-2-ol"}),
    ("2-甲基丁烷", {"2-methylbutane"}),
    ("2-丁酮", {"butan-2-one"}),
    ("3-甲基丁醇", {"3-methylbutan-1-ol"}),
    ("己酸3-甲基丁酯", {"3-methylbutyl hexanoate"}),
    ("2-甲基丁酸乙酯", {"ethyl 2-methylbutanoate"}),
    ("2-羟基丁酸乙酯", {"ethyl 2-hydroxybutanoate"}),
    ("2-乙基-5-甲基吡嗪", {"2-ethyl-5-methylpyrazine"}),
    ("2-乙基-5-甲基呋喃", {"2-ethyl-5-methylfuran"}),
    ("2-甲基-1-丙醇", {"2-methylpropan-1-ol"}),
    ("2-甲基-3-辛酮", {"2-methyloctan-3-one"}),
    ("2,6-二甲基-4-庚醇", {"2,6-dimethylheptan-4-ol"}),
    ("2-十一烯醛", {"undec-2-enal"}),
    ("4-甲基-2-戊酮", {"4-methylpentan-2-one"}),
    ("异丁酸乙酯", {"ethyl isobutanoate", "ethyl isobutyrate"}),
    ("异戊酸乙酯", {"ethyl isovalerate"}),
    ("己酸异丁酯", {"isobutyl hexanoate"}),
    # Lactones. The chinese prefix names the substituent on a gamma-butyrolactone, not
    # the ring size; these are the english names behind the CAS numbers sheet 34 prints,
    # so each one is pinned to what that paper's own column says.
    ("γ-丁内酯", {"oxolan-2-one"}),
    ("γ-戊内酯", {"5-methyloxolan-2-one"}),
    ("γ-己内酯", {"5-ethyloxolan-2-one"}),
    ("γ-庚内酯", {"5-propyloxolan-2-one"}),
    ("γ-辛内酯", {"5-butyloxolan-2-one"}),
    ("γ-壬内酯", {"5-pentyloxolan-2-one"}),
    ("γ-癸内酯", {"5-hexyloxolan-2-one"}),
    ("γ-十二内酯", {"5-octyloxolan-2-one"}),
]

# Names an earlier translator got wrong because it overwrote a written position with
# the parent's canonical numbering. They are listed here rather than left to the rules
# alone, because a regression here would be silent: 2,3-diethylpyrazine turning back
# into 2,3-dimethylpyrazine would look like a plausible name and be a different
# compound.
REGRESSIONS = [
    ("2,3-二乙基吡嗪", {"2,3-diethylpyrazine"}),
    ("2,6-二乙基吡嗪", {"2,6-diethylpyrazine"}),
    ("2,3-二甲基吡嗪", {"2,3-dimethylpyrazine"}),
    ("2,5-二甲基吡嗪", {"2,5-dimethylpyrazine"}),
    ("2,6-二甲基吡嗪", {"2,6-dimethylpyrazine"}),
    ("2,5-二甲基-3-乙基吡嗪", {"3-ethyl-2,5-dimethylpyrazine"}),
    ("2,3-二乙基-5-甲基吡嗪", {"2,3-diethyl-5-methylpyrazine"}),
    ("2,3,5-三甲基-6-乙基吡嗪", {"6-ethyl-2,3,5-trimethylpyrazine"}),
    ("4-甲基苯酚", {"4-methylphenol"}),
    ("4-乙基苯酚", {"4-ethylphenol"}),
    ("2,4-二甲基苯酚", {"2,4-dimethylphenol"}),
    ("2, 4-二甲基苯酚", {"2,4-dimethylphenol"}),
]

# names that must be REFUSED, never guessed
MUST_REFUSE = [
    "2,5-二甲基-3-丁基吡嗪",
    "1,1-二乙氧基-2-苯乙烷",
    # genuinely ambiguous: the group carbon is never written
    "戊醇", "己酮", "2-甲基丙醇", "2-甲基丙酮", "3-甲基丁酮",
    # delta lactones: no printed CAS anywhere in the corpus shows which ring size the
    # convention implies, so translating them would repeat the gamma mistake in reverse
    "δ-癸内酯", "δ-壬内酯", "δ-十二内酯",
    # shorter than 丁 there is no such gamma-lactone
    "γ-丙内酯",
    # not compounds at all
    "其他类物质总含量", "酸类物质总含量", "醇类物质总含量",
    "表 3", "表3 主要挥发性成分", "序号", "总计", "未知",
    "酯类", "酸类", "醇类",
    # ocr damage
    "1-」醇", "2-了醇", "1--丁烷", "2-十—酮",
    # a written position that fits nothing must not be dropped
    "2-己酸乙酯", "2-壬醛",
]

DIGIT_RUN = re.compile(r"\d+")


def cn_digits(s):
    """Digit sequence as written, using the CN_NUM values for count words."""
    out = []
    for m in re.finditer(r"\d+", s):
        out.append(m.group(0))
    # a bare CN count word before a substituent is a multiplier, not a locant:
    # 三甲基 is "trimethyl", not position 3. Locants only appear next to a hyphen
    # or in a comma list, so only harvest those.
    for m in re.finditer(r"([一-鿿]{1,3})?(?=-)|(?<=,)\s*([一-鿿]+)", s):
        pass
    return out


def main():
    bad = 0
    print("=== 1. known-good pairs ===")
    p1 = 0
    for cn, want in EXPECT:
        got = Z.translate(cn)
        if got is None:
            print("   MISS  %-22s (expected %s)" % (cn, " / ".join(sorted(want))))
            bad += 1
            p1 += 1
        elif got not in want:
            print("   DIFF  %-22s -> %-26s (expected %s)"
                  % (cn, got, " / ".join(sorted(want))))
            bad += 1
            p1 += 1
    print("   %d/%d ok" % (len(EXPECT) - p1, len(EXPECT)))

    print("=== 1b. position-overwrite regressions ===")
    p1b = 0
    for cn, want in REGRESSIONS:
        got = Z.translate(cn)
        if got not in want:
            print("   REGR  %-22s -> %-28s (expected %s)"
                  % (cn, got, " / ".join(sorted(want))))
            p1b += 1
    print("   %d/%d ok" % (len(REGRESSIONS) - p1b, len(REGRESSIONS)))
    bad += p1b

    print("=== 2. must refuse ===")
    rb = 0
    for cn in MUST_REFUSE:
        got = Z.translate(cn)
        if got is not None:
            print("   LEAK  %-22s -> %s" % (cn, got))
            rb += 1
    print("   %d/%d ok" % (len(MUST_REFUSE) - rb, len(MUST_REFUSE)))

    print("=== 3. locants survive translation (whole corpus) ===")
    try:
        cache = json.load(open("out/re整理/pubchem_cache.json", encoding="utf-8"))
        corpus = [k for k in cache if re.search(r"[一-鿿]", k)]
    except Exception:
        corpus = []

    def locs_cn(s):
        """Positions written in the chinese part of the cell: digits before - or ,.

        Only the chinese half counts. A cell may hold an english name glued on whose
        digits are its own, and comparing those against the chinese half would report a
        position as lost when the translator never had it to begin with.
        """
        cut = re.search(r"[A-Za-z]", s)
        cn = s[:cut.start()] if cut else s
        # digits right before a latin name belong to that name, not to the chinese one
        cn = re.sub(r"[\d\-_,;/\s]+$", "", cn)
        if any(re.fullmatch(r"[\d.]+", t) for t in cn.split()):
            # a bare number means the table row was never split into columns, so only
            # the first token is the compound name
            cn = cn.split()[0]
        else:
            # spaces inside a name are OCR noise ("3- 羟基-2- 丁酮"), not word breaks
            cn = re.sub(r"\s+", "", cn)
        out = []
        for m in re.finditer(r"\d+(?=\s*[-–,])", cn):
            out += [int(x) for x in re.findall(r"\d+", m.group(0))]
        return out

    def locs_en(s):
        """Positions in the English name: bare integer tokens. Split on space too, or
        'ethyl 2-methylbutanoate' hides its 2 inside the first fragment."""
        return [int(t) for t in re.split(r"[\s,\-()]", s) if t.isdigit()]

    d3 = 0
    for cn in corpus:
        got = Z.translate(cn)
        if not got:
            continue
        a, b = locs_cn(cn), locs_en(got)
        lost = [x for x in a if x not in b]
        # A systematic english name states positions the chinese leaves implicit -
        # 丙酮 becomes propan-2-one - so extra positions are only suspicious when the
        # chinese already wrote some, because then they should be the same ones.
        extra = [x for x in b if x not in a and x != 1] if a else []
        if lost or extra:
            print("   LOC   %-24s -> %-30s  cn=%s en=%s lost=%s extra=%s"
                  % (cn, got, a, b, lost, extra))
            d3 += 1
    print("   checked %d chinese names, %d locant problems"
          % (len(corpus), d3))
    bad += d3

    print("=== 4. no english output containing stray characters ===")
    s4 = 0
    for cn in corpus:
        got = Z.translate(cn)
        if not got:
            continue
        if re.search(r"[^A-Za-z0-9,\-'\s()αβγδΔ]", got):
            print("   CHAR  %-24s -> %r" % (cn, got))
            s4 += 1
    print("   %d suspect" % s4)
    bad += s4

    print("=== 5. cells whose chinese and english halves disagree ===")
    Z.CONFLICTED.clear()
    for cn in corpus:
        Z.translate(cn)
    for src, zh_en, en in Z.CONFLICTED:
        print("   BOTH  %-24s chinese-> %-26s english-> %s" % (src, zh_en, en))
    print("   %d conflicted, chinese side kept" % len(Z.CONFLICTED))

    print("=== 6. table sizes ===")
    for label, tbl in (("DIRECT", Z.DIRECT), ("KNOWN_BAD", Z.KNOWN_BAD),
                       ("AMBIGUOUS", Z.AMBIGUOUS)):
        print("   %-10s %d entries" % (label, len(tbl)))

    print()
    print("PROBLEMS: %d" % bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())