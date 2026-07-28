"""Numeric kernels demonstrating scalars, buffers, SIMD and heap use."""

comptime Ptr = UnsafePointer[Float64, AnyOrigin[mut=True]]
comptime W = 4


@export("sum")
def sum(addr: Int32, n: Int32) abi("C") -> Float64:
    var p = Ptr(unsafe_from_address=Int(addr))
    var count = Int(n)
    var acc = SIMD[DType.float64, W](0)
    var i = 0
    while i + W <= count:
        acc += p.load[width=W](i)
        i += W
    var s = acc.reduce_add()
    while i < count:
        s += p[i]
        i += 1
    return s


@export("dot")
def dot(a_addr: Int32, b_addr: Int32, n: Int32) abi("C") -> Float64:
    var a = Ptr(unsafe_from_address=Int(a_addr))
    var b = Ptr(unsafe_from_address=Int(b_addr))
    var count = Int(n)
    var acc = SIMD[DType.float64, W](0)
    var i = 0
    while i + W <= count:
        acc += a.load[width=W](i) * b.load[width=W](i)
        i += W
    var s = acc.reduce_add()
    while i < count:
        s += a[i] * b[i]
        i += 1
    return s


@export("matmul")
def matmul(a_addr: Int32, b_addr: Int32, c_addr: Int32,
           m: Int32, k: Int32, n: Int32) abi("C") -> Int32:
    var a = Ptr(unsafe_from_address=Int(a_addr))
    var b = Ptr(unsafe_from_address=Int(b_addr))
    var c = Ptr(unsafe_from_address=Int(c_addr))
    var M = Int(m)
    var K = Int(k)
    var N = Int(n)
    for i in range(M):
        for j in range(N):
            c[i * N + j] = 0.0
        for kk in range(K):
            var av = a[i * K + kk]
            for j in range(N):
                c[i * N + j] += av * b[kk * N + j]
    return Int32(M * N)


@export("moving_average")
def moving_average(src_addr: Int32, dst_addr: Int32, n: Int32, window: Int32) abi("C") -> Int32:
    var src = Ptr(unsafe_from_address=Int(src_addr))
    var dst = Ptr(unsafe_from_address=Int(dst_addr))
    var count = Int(n)
    var w = Int(window)
    if w < 1:
        w = 1
    var acc = Float64(0)
    for i in range(count):
        acc += src[i]
        if i >= w:
            acc -= src[i - w]
        var denom = i + 1
        if denom > w:
            denom = w
        dst[i] = acc / Float64(denom)
    return Int32(count)


@export("heap_sum")
def heap_sum(n: Int32) abi("C") -> Float64:
    """Uses Mojo's allocator, which routes through the wasm bump heap."""
    var l = List[Float64]()
    for i in range(Int(n)):
        l.append(Float64(i) * 0.5)
    var s = Float64(0)
    for i in range(len(l)):
        s += l[i]
    return s
