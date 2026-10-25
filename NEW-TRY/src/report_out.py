# -*- coding: utf-8 -*-
"""
Send a script's report to a file in UTF-8 as well as to the console.

The console here is a legacy code page: piping output through PowerShell writes the bytes
it received, and a report full of Chinese compound names comes back as mojibake that no
amount of decoding recovers. Writing the file from Python, in UTF-8, sidesteps the shell
entirely, so the report stays readable whether it is read on screen or from disk.

Use:  sys.stdout = open_report(path)     before printing anything.
"""

import io
import sys

_ORIG = sys.stdout


class _Tee(object):
    def __init__(self, console, path):
        self.console = console
        self.f = io.open(path, "w", encoding="utf-8")

    def write(self, s):
        self.console.write(s)
        try:
            self.f.write(s)
        except UnicodeEncodeError:
            self.f.write(s.encode("utf-8", "replace").decode("utf-8"))

    def flush(self):
        self.console.flush()
        self.f.flush()

    def reconfigure(self, **kw):
        """Accept and ignore - the console keeps its own encoding, and the file is
        already UTF-8. Present because scripts call sys.stdout.reconfigure() after
        redirecting, and a wrapper without it turns their output into an AttributeError."""
        return self.console.reconfigure(**kw)

    def writelines(self, lines):
        for s in lines:
            self.write(s)

    def isatty(self):
        return False


def open_report(path):
    """Return a stdout that also writes UTF-8 to path, or stdout unchanged if no path."""
    if not path:
        return _ORIG
    return _Tee(_ORIG, path)


def arg_path(ap, default=""):
    """An --out argument shared by the verify scripts."""
    ap.add_argument("--out", default=default,
                    help="also write the report to this file, in UTF-8")
    return ap.parse_args()