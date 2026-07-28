/* mojo-wasm runtime shim: the handful of symbols Mojo-generated LLVM IR
   expects from the host, implemented for a freestanding wasm32 module. */

typedef unsigned long long u64;
typedef long long i64;
typedef unsigned int u32;

extern unsigned char __heap_base;

static u32 mw_brk = 0;
static u32 mw_heap_start = 0;

__attribute__((import_module("env"), import_name("mw_write")))
extern void mw_host_write(u32 fd, u32 ptr, u32 len);

static void mw_init(void) {
  if (!mw_heap_start) {
    mw_heap_start = (u32)(unsigned long)&__heap_base;
    mw_brk = mw_heap_start;
  }
}

/* current heap top, exported so JS can inspect / reset between runs */
__attribute__((visibility("default"))) u32 mw_heap_used(void) {
  mw_init();
  return mw_brk - mw_heap_start;
}

__attribute__((visibility("default"))) void mw_heap_reset(void) {
  mw_init();
  mw_brk = mw_heap_start;
}

/* bump allocator; memory.grow on demand */
void *KGEN_CompilerRT_AlignedAlloc(u64 align, u64 size) {
  mw_init();
  u32 a = (u32)align;
  if (a < 8) a = 8;
  u32 p = (mw_brk + (a - 1)) & ~(a - 1);
  u32 end = p + (u32)size;
  u32 pages = (u32)__builtin_wasm_memory_size(0) * 65536u;
  if (end > pages) {
    u32 need = (end - pages + 65535u) / 65536u;
    if (__builtin_wasm_memory_grow(0, need) == (u32)-1) return 0;
  }
  mw_brk = end;
  return (void *)(unsigned long)p;
}

void KGEN_CompilerRT_AlignedFree(void *p) { (void)p; }

/* Mojo's stdout path: write(2) plus a stdio veneer we stub out. */
i64 write(i64 fd, const void *buf, i64 n) {
  mw_host_write((u32)fd, (u32)(unsigned long)buf, (u32)n);
  return n;
}
int dup(int fd) { return fd; }
i64 fdopen(int fd, const char *mode) { (void)mode; return (i64)fd; }
int fflush(i64 f) { (void)f; return 0; }
int fclose(i64 f) { (void)f; return 0; }
int KGEN_CompilerRT_fprintf(i64 f, const char *fmt, ...) { (void)f; (void)fmt; return 0; }

/* freestanding libc bits clang lowers to */
void *memcpy(void *d, const void *s, unsigned long n) {
  unsigned char *dp = d; const unsigned char *sp = s;
  for (unsigned long i = 0; i < n; i++) dp[i] = sp[i];
  return d;
}
void *memmove(void *d, const void *s, unsigned long n) {
  unsigned char *dp = d; const unsigned char *sp = s;
  if (dp < sp) { for (unsigned long i = 0; i < n; i++) dp[i] = sp[i]; }
  else { for (unsigned long i = n; i > 0; i--) dp[i-1] = sp[i-1]; }
  return d;
}
void *memset(void *d, int c, unsigned long n) {
  unsigned char *dp = d;
  for (unsigned long i = 0; i < n; i++) dp[i] = (unsigned char)c;
  return d;
}
int memcmp(const void *a, const void *b, unsigned long n) {
  const unsigned char *x = a, *y = b;
  for (unsigned long i = 0; i < n; i++) if (x[i] != y[i]) return x[i] < y[i] ? -1 : 1;
  return 0;
}

/* JS-facing allocator so hosts can hand buffers to Mojo without guessing
   at static-data layout. */
__attribute__((visibility("default"))) u32 mw_alloc(u32 size, u32 align) {
  return (u32)(unsigned long)KGEN_CompilerRT_AlignedAlloc(align ? align : 8, size);
}
