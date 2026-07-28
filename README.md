# mojo-wasm

Compile [Mojo](https://www.modular.com/mojo) to WebAssembly and run it in the browser.

Mojo's compiler ships no wasm backend, so this drives one out of the parts that are
there: emit LLVM IR from `mojo build`, retarget that IR to `wasm32`, compile it with a
modern clang, and link it against a small freestanding runtime that supplies the handful
of host symbols Mojo expects (allocator, `write`, stdio veneer). The result is a plain
`.wasm` module with no glue, no emscripten, no JS shims around the calls themselves.

```bash
pixi install
pixi run mojowasm build examples/kernels.mojo -o build/kernels.wasm
pixi run serve            # http://127.0.0.1:8770 — edit Mojo, compile, run in the tab
```

```js
import { loadMojo } from "./js/mojowasm.js";

const m = await loadMojo("kernels.wasm");
const a = m.allocF64(1 << 20).set(data);
m.exports.sum(a.ptr, 1 << 20);
```

## What it does

| stage | tool |
| --- | --- |
| Mojo → LLVM IR | `mojo build --emit llvm` |
| IR → wasm32 IR | `retarget_ir()` — swaps datalayout/triple, drops x86 cpu/feature attrs |
| IR → object | `clang --target=wasm32-unknown-unknown -O3` (clang ≥ 20) |
| link | `wasm-ld --no-entry --export-dynamic` + `runtime/mwrt.c` |

`runtime/mwrt.c` is ~90 lines: a bump allocator behind `KGEN_CompilerRT_AlignedAlloc`
(so Mojo's `List`, `String` and friends work), `memcpy`/`memset`/`memmove`, and a
`write()` that forwards to an imported `env.mw_write` — that is how `print` reaches
`console.log`.

## Writing kernels

Exported functions must use the C ABI and pass buffers as **32-bit addresses**:

```mojo
comptime Ptr = UnsafePointer[Float64, AnyOrigin[mut=True]]

@export("sum")
def sum(addr: Int32, n: Int32) abi("C") -> Float64:
    var p = Ptr(unsafe_from_address=Int(addr))
    var acc = SIMD[DType.float64, 4](0)
    var i = 0
    while i + 4 <= Int(n):
        acc += p.load[width=4](i)
        i += 4
    return acc.reduce_add()
```

Use `Int32`, not `Int`: Mojo's `Int` is 64-bit, which crosses to JS as `BigInt` and makes
every call site awkward. On the JS side `m.allocF64(n)` returns `{ ptr, view, set() }`
where `ptr` is what you hand to the kernel.

## Benchmarks

Node 22, wasm vs. hand-written JS on the same data (`pixi run bench`):

| kernel | mojo-wasm | JS |
| --- | --- | --- |
| `sum` 2²⁰ f64 (SIMD) | 0.58 ms | 2.59 ms |
| `dot` 2²⁰ f64 (SIMD) | 2.02 ms | 4.08 ms |
| `matmul` 128³ | 1.90 ms | 8.63 ms |
| mandelbrot 800×600 @300 | 186 ms | 167 ms |

Vectorizable array work wins 2–4×, because `SIMD[DType.float64, 4]` lowers to real wasm
SIMD and TurboFan won't vectorize the JS loop. Scalar branchy float code (mandelbrot) is
a wash or slightly behind — the JIT is already good at that, and this pipeline gives up
`-march=native` when it leaves the host.

Module sizes are small: 1.3 KB for mandelbrot, 13 KB for the whole kernel set.

## Limits

This is a *numeric subset* of Mojo, not the whole language:

- **No threads, no GPU, no filesystem, no networking.** Anything reaching for those
  produces undefined symbols at link time (they are reported, not silently stubbed).
- **`--allow-undefined` is on** so a stray host symbol becomes a runtime trap rather than
  a link error; check the module's imports if a call traps.
- **Pointer width is reinterpreted.** The IR is generated believing pointers are 8 bytes
  and consumed believing they are 4. Layouts stay self-consistent (all offsets are
  constants baked in by the same compiler) but structures containing pointers waste
  4 bytes per pointer. Round-tripping a pointer through `Int` and back works; casting a
  pointer to `Int64`, storing it, and expecting the top half to survive does not.
- **`free` is a no-op.** The bump allocator only grows. Call `m.heapReset()` between
  independent runs, or reinstantiate the module.
- **Exceptions/`raises` are not supported**; a Mojo `abort` path lands on `unreachable`.

## Playground

`pixi run serve` starts a stdlib-only HTTP server: `POST /compile` takes `{"source": ...}`
and returns `application/wasm` (compiles are content-addressed and cached, so a repeat
build is a disk hit). The page ships three samples — a SIMD reduction, a mandelbrot that
renders to a canvas, and one using Mojo's heap — and shows compile size, compile time,
and kernel time.

Compilation happens on the server; the Mojo compiler is a native toolchain and cannot
itself run in the browser. The *execution* is entirely client-side.

## Layout

```
runtime/mwrt.c            freestanding wasm runtime (allocator + host shims)
python/mojowasm/          compiler driver, CLI, playground server
js/mojowasm.js            ESM loader and memory helpers
examples/                 kernels.mojo, mandelbrot.mojo
playground/index.html     browser editor
bench/, tests/
```

## Related

- [mojosub](https://github.com/lee101/mojosub) — Python subset → Mojo transpiler with a JIT
- [mojo-sklearn](https://github.com/lee101/mojo-sklearn) — scikit-learn API on Mojo kernels
- [mojo-arrow](https://github.com/lee101/mojo-arrow) — Arrow compute kernels

Apache-2.0.
