// Browser/Node loader for modules produced by `mojowasm build`.
// Usage:
//   const m = await loadMojo('mandelbrot.wasm', { onPrint: s => console.log(s) })
//   const buf = m.allocF64(1024)          // { ptr, view }
//   m.exports.myKernel(buf.ptr, 1024)

const dec = new TextDecoder();

export async function loadMojo(source, opts = {}) {
  const { onPrint = (s) => console.log(s), imports = {} } = opts;
  let bytes;
  if (source instanceof Uint8Array || source instanceof ArrayBuffer) {
    bytes = source;
  } else if (typeof source === "string") {
    const res = await fetch(source);
    bytes = new Uint8Array(await res.arrayBuffer());
  } else {
    bytes = source;
  }

  let mem = null;
  const env = {
    mw_write: (fd, ptr, len) => {
      if (!mem) return;
      onPrint(dec.decode(new Uint8Array(mem.buffer, ptr, len)));
    },
    ...imports,
  };
  const { instance } = await WebAssembly.instantiate(bytes, { env });
  const e = instance.exports;
  mem = e.memory;

  const alloc = (bytes_, align = 8) => e.mw_alloc(bytes_, align);

  const typed = (Ctor) => (n) => {
    const ptr = alloc(n * Ctor.BYTES_PER_ELEMENT, Ctor.BYTES_PER_ELEMENT);
    // memory.grow detaches the old buffer, so views are made on demand
    return {
      ptr,
      get view() {
        return new Ctor(mem.buffer, ptr, n);
      },
      set(data) {
        new Ctor(mem.buffer, ptr, n).set(data);
        return this;
      },
    };
  };

  return {
    instance,
    exports: e,
    memory: mem,
    alloc,
    allocF64: typed(Float64Array),
    allocF32: typed(Float32Array),
    allocI32: typed(Int32Array),
    allocU8: typed(Uint8Array),
    heapUsed: () => e.mw_heap_used(),
    heapReset: () => e.mw_heap_reset(),
    view: (Ctor, ptr, n) => new Ctor(mem.buffer, ptr, n),
  };
}

export default loadMojo;
