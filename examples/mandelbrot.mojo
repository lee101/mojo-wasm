@export("mandelbrot")
def mandelbrot(addr: Int32, w: Int32, h: Int32, max_iter: Int32,
               cx: Float64, cy: Float64, scale: Float64) abi("C") -> Int32:
    comptime Ptr = UnsafePointer[UInt8, AnyOrigin[mut=True]]
    var p = Ptr(unsafe_from_address=Int(addr))
    var width = Int(w)
    var height = Int(h)
    var iters = Int(max_iter)
    var total = 0
    for y in range(height):
        var im = cy + (Float64(y) - Float64(height) / 2.0) * scale
        for x in range(width):
            var re = cx + (Float64(x) - Float64(width) / 2.0) * scale
            var zr = Float64(0)
            var zi = Float64(0)
            var i = 0
            while i < iters:
                var zr2 = zr * zr
                var zi2 = zi * zi
                if zr2 + zi2 > 4.0:
                    break
                zi = 2.0 * zr * zi + im
                zr = zr2 - zi2 + re
                i += 1
            total += i
            p[y * width + x] = UInt8((i * 255) // iters)
    return Int32(total)
