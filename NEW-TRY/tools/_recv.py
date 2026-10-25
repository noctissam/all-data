# -*- coding: utf-8 -*-
"""
Tiny local receiver so the browser can hand us the publisher's table JSON verbatim.

Usage:
    python tools/_recv.py <outfile> [port]

Then, in the page:
    fetch('http://127.0.0.1:8765/save', {method:'POST', mode:'cors',
          headers:{'Content-Type':'text/plain'}, body: jsonString})

Content-Type text/plain keeps it a simple request, so no CORS preflight is needed.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

OUTFILE = sys.argv[1] if len(sys.argv) > 1 else "publisher_tables.json"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", OUTFILE)
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        prev = b""
        if os.path.exists(path):
            with open(path, "rb") as f:
                prev = f.read()
            prev = prev.rstrip().rstrip(b",") + b","
        with open(path, "wb") as f:
            f.write(prev + body.strip().rstrip(b","))
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"ok")
        print("saved chunk %d bytes -> %s (total %d)" % (len(body), path, os.path.getsize(path)))

    def do_GET(self):
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"receiver up")

    def log_message(self, *a):
        pass


print("listening on 127.0.0.1:%d -> %s" % (PORT, OUTFILE))
HTTPServer(("127.0.0.1", PORT), H).serve_forever()
