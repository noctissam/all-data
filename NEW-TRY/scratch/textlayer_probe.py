# -*- coding: utf-8 -*-
"""
Is a disputed string actually present in the PDF's text layer?

Separates three causes that look identical in the workbook:

  - the text is in the PDF but the grid step put it in the wrong cell (recoverable here);
  - the text is in the PDF only as vector outlines, so there is nothing to read and it
    would need OCR (this is the `needs-ocr` route, not `band`);
  - the text is not in the document at all.

The band route means text_ok() passed, so case 2 does not apply to those papers and a
missing cell is always a grid-assignment problem rather than an OCR one.

Usage: python scratch/textlayer_probe.py <pdf> <page-1-based> [substring ...]
"""
import os
import sys

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")
import pymupdf   # noqa: E402


def main():
    pdf, page = sys.argv[1], int(sys.argv[2])
    needles = sys.argv[3:]
    doc = pymupdf.open(pdf)
    p = doc[page - 1]
    txt = p.get_text("text")
    print("page %d  chars=%d  images=%d  drawings=%d"
          % (page, len(txt), len(p.get_images(full=True)), len(p.get_drawings())))
    if not needles:
        print(txt[:3000])
        return
    flat = "".join(txt.split())
    for n in needles:
        key = "".join(n.split())
        print("  %-26s %s" % (n, "FOUND" if key in flat else "absent"))
    doc.close()


if __name__ == "__main__":
    main()