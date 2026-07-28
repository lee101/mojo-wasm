"""Compile Mojo source to a freestanding wasm32 module.

Mojo's own LLVM has no wasm backend registered, so the pipeline is:

    mojo build --emit llvm   ->  x86-64 LLVM IR
    retarget IR to wasm32    ->  clang -c --target=wasm32
    link with runtime shim   ->  wasm-ld --no-entry --export-dynamic

Only the exported (`@export(...) ... abi("C")`) surface is callable from JS.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_C = ROOT / "runtime" / "mwrt.c"
CACHE_DIR = Path(os.environ.get("MOJOWASM_CACHE", Path.home() / ".cache" / "mojowasm"))

WASM32_DATALAYOUT = "e-m:e-p:32:32-p10:8:8-p20:8:8-i64:64-n32:64-S128-ni:1:10:20"
WASM32_TRIPLE = "wasm32-unknown-unknown"

# runtime symbols always kept alive so hosts can drive memory
RUNTIME_EXPORTS = ("mw_alloc", "mw_heap_used", "mw_heap_reset")


class BuildError(RuntimeError):
    pass


def _tool(name: str) -> str:
    for base in (ROOT / ".pixi" / "envs" / "default" / "bin", None):
        cand = shutil.which(name, path=str(base)) if base else shutil.which(name)
        if cand:
            return cand
    raise BuildError(f"{name} not found; run `pixi install` in {ROOT}")


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise BuildError(f"{cmd[0]} failed:\n{p.stderr or p.stdout}")
    return p


def retarget_ir(ir: str) -> str:
    """Rewrite host IR so a wasm32 clang will accept it.

    The x86 datalayout and cpu/feature attributes are host-specific and must go.
    Everything else in the module is target neutral for the numeric subset we
    support (see README for what does not survive).
    """
    ir = re.sub(r"^target datalayout.*$", f'target datalayout = "{WASM32_DATALAYOUT}"', ir, flags=re.M)
    ir = re.sub(r"^target triple.*$", f'target triple = "{WASM32_TRIPLE}"', ir, flags=re.M)
    ir = re.sub(r'"target-cpu"="[^"]*"\s*', "", ir)
    ir = re.sub(r'"target-features"="[^"]*"\s*', "", ir)
    ir = re.sub(r"attributes (#\d+) = \{\s*\}", r"attributes \1 = { nounwind }", ir)
    return ir


def exported_symbols(ir: str) -> list[str]:
    return re.findall(r"^define dso_local [^@]*@([A-Za-z_][\w.$]*)\(", ir, flags=re.M)


@dataclass
class BuildResult:
    wasm: bytes
    path: Path
    symbols: list[str] = field(default_factory=list)
    cached: bool = False


def _runtime_object(clang: str, opt: int, workdir: Path) -> Path:
    key = hashlib.sha256((RUNTIME_C.read_bytes() + str(opt).encode())).hexdigest()[:16]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    obj = CACHE_DIR / f"mwrt-{key}.o"
    if not obj.exists():
        tmp = workdir / "mwrt.o"
        _run([clang, f"--target={WASM32_TRIPLE}", f"-O{opt}", "-nostdlib", "-ffreestanding",
              "-c", str(RUNTIME_C), "-o", str(tmp)])
        shutil.copy(tmp, obj)
    return obj


def build(
    source: str | Path,
    out: str | Path | None = None,
    *,
    opt: int = 3,
    stack_size: int = 1 << 20,
    initial_memory: int = 16 << 20,
    keep_ir: bool = False,
    cache: bool = True,
) -> BuildResult:
    """Compile one .mojo file (or a source string) to a .wasm module."""
    src_path: Path | None = None
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and str(source).endswith(".mojo")):
        src_path = Path(source).resolve()
        src_text = src_path.read_text()
    else:
        src_text = str(source)

    key = hashlib.sha256(
        (src_text + RUNTIME_C.read_text() + f"{opt}:{stack_size}:{initial_memory}").encode()
    ).hexdigest()[:20]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_wasm = CACHE_DIR / f"{key}.wasm"
    if cache and cached_wasm.exists():
        data = cached_wasm.read_bytes()
        dest = Path(out) if out else cached_wasm
        if out:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        return BuildResult(data, dest, symbols=[], cached=True)

    mojo, clang, wasm_ld = _tool("mojo"), _tool("clang"), _tool("wasm-ld")

    with tempfile.TemporaryDirectory(prefix="mojowasm-") as td:
        work = Path(td)
        mojo_src = work / "mod.mojo"
        mojo_src.write_text(src_text)
        ll = work / "mod.ll"
        cmd = [mojo, "build", "--emit", "llvm", f"--optimization-level={opt}", "-o", str(ll)]
        if src_path is not None:
            cmd += ["-I", str(src_path.parent)]
        cmd.append(str(mojo_src))
        _run(cmd)

        ir = ll.read_text()
        syms = [s for s in exported_symbols(ir) if not s.startswith("KGEN")]
        wir = work / "mod.w.ll"
        wir.write_text(retarget_ir(ir))
        if keep_ir and out:
            Path(out).with_suffix(".ll").write_text(wir.read_text())

        obj = work / "mod.o"
        _run([clang, f"--target={WASM32_TRIPLE}", f"-O{opt}", "-nostdlib", "-c", str(wir), "-o", str(obj)])

        rt = _runtime_object(clang, opt, work)
        wasm = work / "mod.wasm"
        link = [wasm_ld, "--no-entry", "--export-dynamic", "--allow-undefined",
                f"-z stack-size={stack_size}".replace(" ", "="),
                f"--initial-memory={initial_memory}", "--stack-first",
                "-o", str(wasm), str(obj), str(rt)]
        link = [a for a in link if a]
        for s in RUNTIME_EXPORTS:
            link.insert(1, f"--export={s}")
        _run(link)

        data = wasm.read_bytes()

    if cache:
        cached_wasm.write_bytes(data)
    dest = Path(out) if out else cached_wasm
    if out:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return BuildResult(data, dest, symbols=syms, cached=False)
