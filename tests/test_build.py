import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from mojowasm import build, exported_symbols, retarget_ir  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def test_retarget_strips_host_specifics():
    ir = '\n'.join([
        'target datalayout = "e-m:e-p270:32:32"',
        'target triple = "x86_64-unknown-linux-gnu"',
        'define dso_local double @f(double %0) #0 {\n  ret double %0\n}',
        'attributes #0 = { "target-cpu"="broadwell" "target-features"="+avx2" }',
    ])
    w = retarget_ir(ir)
    assert "wasm32-unknown-unknown" in w
    assert "broadwell" not in w and "+avx2" not in w
    assert "attributes #0 = { nounwind }" in w
    assert exported_symbols(ir) == ["f"]


def test_build_kernels_and_run(tmp_path):
    out = tmp_path / "kernels.wasm"
    r = build(ROOT / "examples" / "kernels.mojo", out, cache=False)
    assert out.exists() and r.wasm[:4] == b"\0asm"
    assert {"sum", "dot", "matmul", "heap_sum"} <= set(r.symbols)


def test_cache_hit(tmp_path):
    src = ROOT / "examples" / "mandelbrot.mojo"
    build(src, tmp_path / "a.wasm")
    r = build(src, tmp_path / "b.wasm")
    assert r.cached


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_kernels_match_python(tmp_path):
    wasm = tmp_path / "kernels.wasm"
    build(ROOT / "examples" / "kernels.mojo", wasm)
    script = tmp_path / "run.mjs"
    script.write_text(f"""
import {{ loadMojo }} from "{ROOT / 'js' / 'mojowasm.js'}";
import {{ readFile }} from "node:fs/promises";
const m = await loadMojo(new Uint8Array(await readFile("{wasm}")));
const n = 997;
const a = m.allocF64(n).set(Array.from({{length:n}},(_,i)=>i*0.5));
const b = m.allocF64(n).set(Array.from({{length:n}},(_,i)=>i%7));
const M=8,K=8,N=8;
const A=m.allocF64(M*K).set(Array.from({{length:M*K}},(_,i)=>(i%13)*0.25));
const B=m.allocF64(K*N).set(Array.from({{length:K*N}},(_,i)=>(i%5)*0.5));
const C=m.allocF64(M*N);
m.exports.matmul(A.ptr,B.ptr,C.ptr,M,K,N);
const s=m.allocF64(n).set(Array.from({{length:n}},(_,i)=>i%11));
const d=m.allocF64(n);
m.exports.moving_average(s.ptr,d.ptr,n,5);
console.log(JSON.stringify({{
  sum: m.exports.sum(a.ptr,n),
  dot: m.exports.dot(a.ptr,b.ptr,n),
  heap: m.exports.heap_sum(500),
  c: Array.from(C.view),
  ma: Array.from(d.view).slice(0,10),
}}));
""")
    got = json.loads(subprocess.run([NODE, str(script)], capture_output=True, text=True, check=True).stdout)

    n = 997
    a = [i * 0.5 for i in range(n)]
    b = [i % 7 for i in range(n)]
    assert got["sum"] == pytest.approx(sum(a))
    assert got["dot"] == pytest.approx(sum(x * y for x, y in zip(a, b)))
    assert got["heap"] == pytest.approx(sum(i * 0.5 for i in range(500)))

    M = K = N = 8
    A = [(i % 13) * 0.25 for i in range(M * K)]
    B = [(i % 5) * 0.5 for i in range(K * N)]
    ref = [sum(A[i * K + k] * B[k * N + j] for k in range(K)) for i in range(M) for j in range(N)]
    assert got["c"] == pytest.approx(ref)

    s = [i % 11 for i in range(n)]
    ma = [sum(s[max(0, i - 4):i + 1]) / min(i + 1, 5) for i in range(10)]
    assert got["ma"] == pytest.approx(ma)
