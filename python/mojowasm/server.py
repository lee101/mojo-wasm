"""Playground server: edit Mojo in the browser, compile here, run there.

POST /compile  {"source": "..."}  -> application/wasm (or 400 + compiler text)
GET  /*                            -> static files from the repo root
"""

from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .compiler import BuildError, build

ROOT = Path(__file__).resolve().parents[2]
MAX_SOURCE = 256 * 1024


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):  # quieter
        pass

    def do_POST(self):
        if self.path.rstrip("/") != "/compile":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_SOURCE:
            self.send_error(413)
            return
        try:
            src = json.loads(self.rfile.read(n) or b"{}").get("source", "")
        except json.JSONDecodeError:
            self.send_error(400, "bad json")
            return
        try:
            res = build(src)
        except BuildError as e:
            body = str(e).encode()
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/wasm")
        self.send_header("Content-Length", str(len(res.wasm)))
        self.send_header("X-Mojowasm-Cached", "1" if res.cached else "0")
        self.end_headers()
        self.wfile.write(res.wasm)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.path = "/playground/index.html"
        return super().do_GET()


def serve(host: str = "127.0.0.1", port: int = 8770) -> int:
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"mojo-wasm playground on http://{host}:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
