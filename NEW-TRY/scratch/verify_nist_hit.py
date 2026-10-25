# -*- coding: utf-8 -*-
"""Does the NIST page we take a CAS from actually correspond to the name we asked for?"""
import re
import ssl
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
CTX = ssl._create_unverified_context()
UA = {"User-Agent": "reorganise/1.0"}


def page(name):
    u = ("https://webbook.nist.gov/cgi/cbook.cgi?Action=Search&Units=SI&Name="
         + urllib.parse.quote(name) + "&NoIon=on&NoMix=on")
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA),
                                 timeout=30, context=CTX).read().decode("utf-8", "replace")


CAS_LINE = re.compile(r"CAS\s+Registry\s+Number[^0-9]{0,60}(\d{2,7}-\d{2}-\d)")
for name in ("1-辛醇b", "2-丁醇b", "1-辛醇", "辛醇", "ethyl hexanoate", "acetic acid",
             "Isoamyl alcohol"):
    try:
        t = page(name)
    except Exception as e:
        print("%-16s ERROR %s" % (name, e))
        continue
    m = CAS_LINE.search(t)
    title = re.search(r"<title>([^<]*)</title>", t)
    # does the page repeat the queried name near the CAS line?
    ctx = t[max(0, m.start() - 400):m.start()] if m else ""
    print("%-16s CAS=%-13s title=%-22s name_on_page=%s"
          % (name, m.group(1) if m else "-", (title.group(1) if title else "?")[:22],
             (name in ctx) or (name.lower() in ctx.lower()) if m else "-"))