#!/usr/bin/env python3
"""Local preview server that mimics Cloudflare Pages routing for this static site.

  python3 tools/dev_server.py [port]        # default 8788

* /about            -> about.html           (pretty URLs)
* /es/              -> es/index.html
* /about.html       -> 301 /about           (same as _redirects)
* unknown path      -> 404.html with status 404
* POST /api/*       -> small JSON stub (the real handlers are Pages Functions)
"""
from __future__ import annotations
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _resolve(self):
        path = urlsplit(self.path).path
        rel = path.lstrip("/")
        if path.endswith(".html"):
            target = path[: -len(".html")]
            if target.endswith("/index"):
                target = target[: -len("index")]
            self.send_response(301)
            self.send_header("Location", target or "/")
            self.end_headers()
            return None
        f = ROOT / rel
        if path.endswith("/") or rel == "":
            f = f / "index.html"
        elif not f.is_file() and (ROOT / (rel + ".html")).is_file():
            f = ROOT / (rel + ".html")
        if f.is_file() and ROOT in f.resolve().parents:
            return f
        return False

    def do_GET(self):
        f = self._resolve()
        if f is None:
            return
        if f is False:
            body = (ROOT / "404.html").read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.path = "/" + str(f.relative_to(ROOT))
        super().do_GET()

    do_HEAD = do_GET

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        body = b'{"status":"ok","dev":true}'
        self.send_response(200 if self.path.startswith("/api/") else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if "404" in (args[1] if len(args) > 1 else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    print(f"PlainBTC preview: http://localhost:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
