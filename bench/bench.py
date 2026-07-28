"""Build the example kernels and benchmark wasm vs hand-written JS in node."""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from mojowasm import build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    for name in ("kernels", "mandelbrot"):
        r = build(ROOT / "examples" / f"{name}.mojo", ROOT / "build" / f"{name}.wasm")
        print(f"{name}.wasm {len(r.wasm)} bytes{' (cached)' if r.cached else ''}")
    node = shutil.which("node")
    if not node:
        sys.exit("node required for the benchmark")
    subprocess.run([node, str(ROOT / "bench" / "bench.mjs")], check=True)
