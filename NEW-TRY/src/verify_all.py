# -*- coding: utf-8 -*-
"""
Run every check and leave a report per check.

Each script answers one question about the workbook, and none of them can be answered by
looking at the pipeline that produced it:

  selfcheck_zh2en  the chinese-name translator still gives the right english name, still
                   refuses what it cannot place, and no longer loses a written position
  audit_zh2en      how much of the chinese vocabulary is reachable and what is left
  verify_cas       every CAS number passes its own check digit, the printed and resolved
                   values agree, and a sample survives a round trip
  verify_names     no cell in the 化合物名称 column holds something that is not a name
  verify_values    every concentration column states a unit and every value reads as a
                   number, or as the specific thing it is (mean+/-sd, not detected)

Reports are written as UTF-8 next to the workbook, because the console code page turns
Chinese compound names into mojibake on the way out.

Run: python verify_all.py [--roundtrip N] [--offline]
"""

import argparse
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "src")

OUT = os.path.join("out", "re整理")
HERE = os.path.dirname(os.path.abspath(__file__))

CHECKS = [
    ("selfcheck_zh2en", "name translation", []),
    ("selfcheck_cas", "record selection", []),
    ("audit_zh2en", "name coverage", ["--offline"]),
    ("verify_cas", "CAS column", []),
    ("verify_names", "name column", []),
    ("verify_values", "concentration columns", []),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roundtrip", type=int, default=0,
                    help="verify N resolved CAS numbers against a second lookup")
    ap.add_argument("--offline", action="store_true",
                    help="skip the checks that need the network")
    a = ap.parse_args()

    made = []
    for mod, title, extra in CHECKS:
        out = os.path.join(OUT, "%s.txt" % mod)
        cmd = [sys.executable, os.path.join(HERE, mod + ".py"), "--out", out] + extra
        if mod == "audit_zh2en" and not a.offline:
            cmd = [c for c in cmd if c != "--offline"]
        if mod == "verify_cas" and a.roundtrip:
            cmd += ["--roundtrip", str(a.roundtrip)]
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        dt = time.time() - t0
        bad = r.returncode != 0
        print("%-18s %-26s %6.1fs  %s"
              % (mod, title, dt, "REPORTED PROBLEMS" if bad else "clean"))
        if r.stderr.strip():
            print("    stderr: %s" % r.stderr.strip().splitlines()[-1][:110])
        if os.path.exists(out):
            made.append(out)

    print()
    print("reports written:")
    for p in made:
        print("   %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())