# -*- coding: utf-8 -*-
"""
Self-check for the CAS resolver's choice of record.

The resolver does more than find a CAS: given a name it has to pick between records that
all carry that name. PubChem keeps one record per stereoisomer, one per registry entry and
one per isotopic form, and they all list the plain name among their synonyms. Getting the
pick wrong does not produce an error - it produces an ordinary-looking CAS for a different
compound, which is the failure this whole exercise exists to avoid.

Four things went wrong here at different times, and each is pinned below by a case that
failed before the fix:

  the wrong record       "nonanal" resolving to 9-[(2-butyloctyl)sulfanyl]nonanal, a C21
                         sulphide whose name ends in the word
  a made-up number       that record's 3071163-34-0, a CAS-shaped number PubChem computed
                         for an unregistered record, which passes its own checksum
  the enantiomer         "2-butanol" resolving to (2R)-butan-2-ol
  the prefix stripped    "(-)-Linalool" becoming "Linalool" and resolving to the racemate

Run: python selfcheck_cas.py
"""

import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")

import fill_cas as F  # noqa: E402

CASES = [
    # name, expected CAS, what the case is for
    ("Ethyl lactate", "97-64-3", "racemate, not the (2R) or (2S) ester"),
    ("2-Butanol", "78-92-2", "racemate, not an enantiomer"),
    ("2-Pentanol", "6032-29-7", "racemate, not an enantiomer"),
    ("2-Hexanol", "626-93-7", "racemate, not an enantiomer"),
    ("2-Heptanol", "543-49-7", "racemate, not an enantiomer"),
    ("2-Methyl-1-butanol", "137-32-6", "racemate, not an enantiomer"),
    ("(-)-Linalool", "126-91-0", "a named enantiomer, not the racemate"),
    ("(+)-Linalool", "126-90-9", "the other enantiomer"),
    ("linalool", "78-70-6", "the racemate"),
    ("benzyl alcohol", "100-51-6", "benzyl alcohol, not benzaldehyde"),
    # a plain name must not resolve to the labelled analog. This one answered 13127-88-3,
    # which is phenol-d6, and it reached the workbook as the CAS for phenol.
    ("phenol", "108-95-2", "phenol itself, not phenol-d6"),
    ("toluene", "108-88-3", "toluene itself, not toluene-d8"),
    # A bracket that is not at the end of the name is part of the name. Stripping it used
    # to answer these with 3-propanol's, benzene's and ethanol's CAS - valid numbers for the
    # wrong substances. The second is the one that settles it: 6314-97-2 is also the number
    # the paper prints for that row, so the lookup now agrees with the source instead of
    # contradicting it.
    ("3-(methylthio)propanal", "3268-49-3", "the methylthio is the compound, not an aside"),
    ("(2,2-Diethoxyethyl) benzene", "6314-97-2",
     "a bracketed prefix is part of the name, not an aside"),
    ("2-[(Z)-9-Octadecenyloxy]ethanol", "5353-25-3",
     "a bracketed substituent is part of the name"),
    # chloroform-d is deliberately NOT tested here: PubChem indexes 67-66-3 against CID
    # 6212, whose IUPAC name is plain "chloroform", so no test on the record can tell the
    # labelled analog apart. That is a gap in the source, not in the selector below.
    ("nonanal", "124-19-6", "not a sulphide whose name ends in -nonanal"),
    ("2-butanol", "78-92-2", "the systematic spelling of the same"),
    ("Ethyl hexanoate", "123-66-0", "plain lookup"),
    ("ethyl acetate", "141-78-6", "plain lookup"),
    ("Cyclohexanone", "108-94-1", "plain lookup"),
    ("3-Methylbutanal", "590-86-3", "a positional isomer, not 2-methylbutanal"),
    ("benzyl alcohol", "100-51-6", "synonym spelling"),
    ("Trichloroethylene", "79-01-6", "a name written entirely inside brackets"),
    ("己酸乙酯", "123-66-0", "from a chinese name"),
    ("乙酸乙酯", "141-78-6", "from a chinese name"),
    ("苯乙醇", "60-12-8", "from a chinese name"),
    ("乙酸异戊酯", "123-92-2", "from a chinese name"),
    ("壬醛", "124-19-6", "from a chinese name"),
    ("柠檬烯", "138-86-3", "handedness unstated, so the unspecified record"),
]

# Names that must come back with no CAS at all rather than a plausible wrong one.
MUST_REFUSE = [
    "FEMA", "Table", "Unknown", "Obviousness", "Typicality",
    "3-propanal + butyric acid",
]


def main():
    cache = {}
    bad = 0
    t0 = time.time()
    print("=== 1. the record chosen for each name ===")
    for name, want, why in CASES:
        got = F.resolve_eutils(name, cache)[0]
        if got == want:
            print("   ok    %-22s %-13s %s" % (name[:22], got, why))
        else:
            print("   WRONG %-22s got %-13s wanted %s   (%s)"
                  % (name[:22], got or "-", want, why))
            bad += 1

    print()
    print("=== 2. names that must be refused ===")
    for name in MUST_REFUSE:
        r = F.resolve_eutils(name, cache)
        if r[0]:
            print("   LEAK  %-24s -> %s" % (name, r[0]))
            bad += 1
        else:
            print("   ok    %-24s %s" % (name, r[2][:44]))

    print()
    print("=== 3. tidy() keeps what identifies the compound ===")
    for s, want in (("(-)-Linalool", "(-)-Linalool"),
                    ("(+)-Linalool", "(+)-Linalool"),
                    ("(3R)-Linalool", "(3R)-Linalool"),
                    ("2-Phenylethanol", "2-Phenylethanol"),
                    ("(Trichloroethylene)", "(Trichloroethylene)"),
                    ("己酸乙酯", "己酸乙酯")):
        got = F.tidy(s)
        if got != want:
            print("   WRONG %-24r -> %r wanted %r" % (s, got, want))
            bad += 1
        else:
            print("   ok    %-24r -> %r" % (s, got))

    print()
    print("PROBLEMS: %d      (%.1fs for %d lookups)"
          % (bad, time.time() - t0, len(CASES) + len(MUST_REFUSE)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())