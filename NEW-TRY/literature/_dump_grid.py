# -*- coding: utf-8 -*-
"""Dump one reconstructed grid so the current extraction state can be inspected."""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

g = json.load(open(sys.argv[1], encoding="utf-8"))
print("id=%s page=%s cols=%d head=%d body=%d" % (g["id"], g["page"], g["n_col"], g["n_head_row"], g["n_body_row"]))
print("caption:", g["caption_text"][:160])
print()
print("HEADER:")
for r in g["header"]:
    print("  ", [(c["text"], c["span"]) for c in r])
print()
print("BODY (first %s):" % (sys.argv[2] if len(sys.argv) > 2 else "8"))
for r in g["body"][: int(sys.argv[2]) if len(sys.argv) > 2 else 8]:
    print("  ", [c["text"] for c in r])
print()
print("verify:", json.dumps(g["verify"], ensure_ascii=False))
