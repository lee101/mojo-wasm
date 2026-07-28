import argparse
import sys
from pathlib import Path

from .compiler import BuildError, build


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mojowasm", description="Compile Mojo to wasm32")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="compile a .mojo file to .wasm")
    b.add_argument("source")
    b.add_argument("-o", "--out")
    b.add_argument("-O", "--opt", type=int, default=3)
    b.add_argument("--no-cache", action="store_true")
    b.add_argument("--keep-ir", action="store_true")

    s = sub.add_parser("serve", help="run the browser playground")
    s.add_argument("--port", type=int, default=8770)
    s.add_argument("--host", default="127.0.0.1")

    a = ap.parse_args(argv)
    if a.cmd == "serve":
        from .server import serve

        return serve(a.host, a.port)

    src = Path(a.source)
    out = a.out or str(src.with_suffix(".wasm"))
    try:
        r = build(src, out, opt=a.opt, cache=not a.no_cache, keep_ir=a.keep_ir)
    except BuildError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{r.path} {len(r.wasm)} bytes{' (cached)' if r.cached else ''}")
    if r.symbols:
        print("exports:", ", ".join(r.symbols))
    return 0
