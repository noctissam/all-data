# -*- coding: utf-8 -*-
"""PDF path for a sheet index, from the sheet map."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REOUT = os.path.abspath(os.path.join(HERE, "..", "out", "re整理"))


def pdf_for(idx):
    for e in json.load(open(os.path.join(REOUT, "sheet_map.json"), encoding="utf-8")):
        if e.get("idx") == idx and e.get("path") and os.path.exists(e["path"]):
            return e["path"]
    return None