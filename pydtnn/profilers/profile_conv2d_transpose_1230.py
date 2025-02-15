"""
Performance tests for transposing matrices

For running the tests run:
    python profile_conv2d_transpose_1230.py

"""

import ctypes
import os
import platform
from ctypes.util import find_library
from timeit import timeit

import numpy as np
from prettytable import PrettyTable

from pydtnn.cython_modules import transpose_1230_ij_cython, transpose_1230_ji_cython


class D:
    # def __init__(self):
    #     """Default parameters"""
    #     self.b = 1  # Batch size
    #     self.c = 1  # Channels per layer
    #     self.h = 128  # Layers height
    #     self.w = 100  # Layers width
    #     self.kn = 1  # Number of filters
    #     self.kh = 16  # Filters weights height
    #     self.kw = 10  # Filters weights width
    #     self.vpadding = 1  # Vertical padding
    #     self.hpadding = 1  # Horizontal padding
    #     self.vstride = 1  # Vertical stride
    #     self.hstride = 1  # Horizontal stride
    #     self.vdilation = 1  # Vertical dilation
    #     self.hdilation = 1  # Horizontal dilation

    def __init__(self, b, c, h, w, kn, kh, kw, vpadding, hpadding,
                 vstride, hstride, vdilation, hdilation):
        self.b = b  # Batch size
        self.c = c  # Channels per layer
        self.h = h  # Layers height
        self.w = w  # Layers width
        self.kn = kn  # Number of filters
        self.kh = kh  # Filters weights height
        self.kw = kw  # Filters weights width
        self.vpadding = vpadding  # Vertical padding
        self.hpadding = hpadding  # Horizontal padding
        self.vstride = vstride  # Vertical stride
        self.hstride = hstride  # Horizontal stride
        self.vdilation = vdilation  # Vertical dilation
        self.hdilation = hdilation  # Horizontal dilation

    @property
    def ho(self):
        return (self.h + 2 * self.vpadding - self.vdilation * (self.kh - 1) - 1) // self.vstride + 1

    @property
    def wo(self):
        return (self.w + 2 * self.hpadding - self.hdilation * (self.kw - 1) - 1) // self.hstride + 1

    def __repr__(self):
        return f"""\
x, weights, and y parameters:
  (b, c, h, w)    = {self.b} {self.c} {self.h} {self.w}
  (kn, c, kh, kw) = {self.kn} {self.c} {self.kh} {self.kw}
  (kn, b, ho, wo) = {self.kn} {self.b} {self.ho} {self.wo}
  padding         = {self.vpadding} {self.hpadding}
  stride          = {self.vstride} {self.hstride}
  dilation        = {self.vdilation} {self.hdilation}
"""


class Params:
    pass


def numpy_transpose_1230(original, transposed):
    transposed[...] = original.transpose((1, 2, 3, 0))


# @njit(parallel=True)
# def transpose_1230_numba(original, transposed):
#     n0, n1, n2, n3 = original.shape
#     for d0 in prange(n0):
#         for d1 in range(n1):
#             for d2 in range(n2):
#                 for d3 in range(n3):
#                     transposed[d1, d2, d3, d0] = original[d0, d1, d2, d3]
#
#
# @njit(parallel=True)
# def transpose_1230_2nd_numba(original, transposed):
#     n0, n1, n2, n3 = original.shape
#     for d0 in range(n0):
#         for d1 in prange(n1):
#             for d2 in range(n2):
#                 for d3 in range(n3):
#                     transposed[d1, d2, d3, d0] = original[d0, d1, d2, d3]


def transpose_1230_conv_gemm(original, transposed, lib):
    n0, n1, n2, n3 = original.shape
    lib.sreshapeWeights_pydtnn(ctypes.c_uint(n0), ctypes.c_uint(n1), ctypes.c_uint(n3), ctypes.c_uint(n2),
                               ctypes.c_void_p(original.ctypes.data), ctypes.c_void_p(transposed.ctypes.data))


def time_transpose_1230(shape, dtype=np.float32):
    d0, d1, d2, d3 = shape
    original = np.random.rand(d0, d1, d2, d3).astype(dtype, order="C")
    numpy_transposed = np.empty((d1, d2, d3, d0), dtype, order="C")
    numba_transposed = np.empty((d1, d2, d3, d0), dtype, order="C")
    conv_gemm_transposed = np.empty((d1, d2, d3, d0), dtype, order="C")
    cython_transposed = np.empty((d1, d2, d3, d0), dtype, order="C")
    # Load convGemm library
    path = find_library('convGemm')
    if not path:
        for current_path in os.environ.get('LD_LIBRARY_PATH', '').split(':'):
            if os.path.exists(os.path.join(current_path, 'libconvGemm.so')):
                path = os.path.join(current_path, 'libconvGemm.so')
                break
    if not path:
        raise ImportError("Library 'libconvGemm.so' could not be found. Please add its path to LD_LIBRARY_PATH "
                          "using 'export LD_LIBRARY_PATH=libconvGemm_path:$LD_LIBRARY_PATH' before calling this "
                          "application.")
    lib = ctypes.cdll.LoadLibrary(path)
    #
    # First run
    #
    print(f"First pass {shape} (checking outputs)", sep="", end="")
    #
    print(".", sep="", end="")
    numpy_transpose_1230(original, numpy_transposed)
    # #
    # print(".", sep="", end="")
    # transpose_1230_numba(original, numba_transposed)
    # assert np.allclose(numpy_transposed, numba_transposed), "numpy and numba outer differ"
    # #
    # print(".", sep="", end="")
    # transpose_1230_2nd_numba(original, numba_transposed)
    # assert np.allclose(numpy_transposed, numba_transposed), "numpy and numba 2nd loop differ"
    #
    print(".", sep="", end="")
    transpose_1230_conv_gemm(original, conv_gemm_transposed, lib)
    try:
        assert np.allclose(numpy_transposed, conv_gemm_transposed), "numpy and convGemm differ"
    except AssertionError as err:
        print()
        print(err)
        print("Numpy sum:", numpy_transposed.sum())
        print("convGemm sum:", conv_gemm_transposed.sum())
        print("np.where(numpy != conv_gemm):")
        print(np.where(numpy_transposed != conv_gemm_transposed))
    #
    print(".", sep="", end="")
    transpose_1230_ij_cython(original, cython_transposed)
    assert np.allclose(numpy_transposed, cython_transposed), "numpy and cython outer differ"
    #
    print(".", sep="", end="")
    transpose_1230_ji_cython(original, cython_transposed)
    assert np.allclose(numpy_transposed, cython_transposed), "numpy and cython 2nd loop differ"
    print()
    #
    # Second run
    #
    print(f"Second pass {shape} (getting times)", sep="", end="")
    print(".", sep="", end="")
    numpy_transpose_1230_t = timeit(lambda: numpy_transpose_1230(original, numpy_transposed),
                                    number=10) / 10
    # print(".", sep="", end="")
    # numba_outer_transposed_1230_t = timeit(lambda: transpose_1230_numba(original, numpy_transposed),
    #                                        number=10) / 10
    # print(".", sep="", end="")
    # numba_2nd_transposed_1230_t = timeit(lambda: transpose_1230_2nd_numba(original, numpy_transposed),
    #                                      number=10) / 10
    print(".", sep="", end="")
    conv_gemm_transposed_1230_t = timeit(lambda: transpose_1230_conv_gemm(original, numpy_transposed, lib),
                                         number=10) / 10
    print(".", sep="", end="")
    cython_transposed_1230_ji_t = timeit(lambda: transpose_1230_ji_cython(original, numpy_transposed),
                                         number=10) / 10
    print(".", sep="", end="")
    cython_transposed_1230_ij_t = timeit(lambda: transpose_1230_ij_cython(original, numpy_transposed),
                                         number=10) / 10
    print()
    min_t = np.min([numpy_transpose_1230_t, conv_gemm_transposed_1230_t,
                    cython_transposed_1230_ij_t, cython_transposed_1230_ji_t])
    a = "*" if conv_gemm_transposed_1230_t == min_t else ""
    b = "*" if cython_transposed_1230_ji_t == min_t else ""
    c = "*" if cython_transposed_1230_ij_t == min_t else ""
    return [["numpy", "a", "convGemm", "b", "cython ji", "c", "cython ij"],
            # ["numpy", "numba outer", "numba 2nd loop", "convGemm", "cython outer", "cython 2nd loop"],
            ["{:6.4f}".format(numpy_transpose_1230_t),
             # numba_outer_transposed_1230_t - numpy_transpose_1230_t,
             # numba_2nd_transposed_1230_t - numpy_transpose_1230_t,
             a,
             "{:6.4f}".format(conv_gemm_transposed_1230_t - numpy_transpose_1230_t),
             b,
             "{:6.4f}".format(cython_transposed_1230_ji_t - numpy_transpose_1230_t),
             c,
             "{:6.4f}".format(cython_transposed_1230_ij_t - numpy_transpose_1230_t),
             ]]


if __name__ == '__main__':
    # D(b, c, h, w, kn, kh, kw, vpadding, hpadding, vstride, hstride, vdilation, hdilation):
    layersAl = [
        # AlexNet Cifar
        D(64, 3, 32, 32, 64, 3, 3, 1, 1, 2, 2, 1, 1),
        D(64, 64, 8, 8, 192, 3, 3, 1, 1, 1, 1, 1, 1),
        D(64, 192, 4, 4, 384, 3, 3, 1, 1, 1, 1, 1, 1),
        D(64, 384, 4, 4, 256, 3, 3, 1, 1, 1, 1, 1, 1),
        D(64, 256, 4, 4, 256, 3, 3, 1, 1, 1, 1, 1, 1),
        # AlexNet ImageNet
        D(64, 3, 227, 227, 96, 11, 11, 1, 1, 4, 4, 1, 1),
        D(64, 96, 27, 27, 256, 5, 5, 1, 1, 1, 1, 1, 1),
        D(64, 256, 13, 13, 384, 3, 3, 1, 1, 1, 1, 1, 1),
        D(64, 384, 13, 13, 384, 3, 3, 1, 1, 1, 1, 1, 1),
        D(64, 384, 13, 13, 256, 3, 3, 1, 1, 1, 1, 1, 1),
    ]

    b = 1
    layers = [
        D(b, 3, 224, 224, 64, 7, 7, 3, 3, 2, 2, 1, 1),
        D(b, 64, 56, 56, 64, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 64, 56, 56, 64, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 64, 56, 56, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 64, 56, 56, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 56, 56, 64, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 64, 56, 56, 64, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 64, 56, 56, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 56, 56, 64, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 64, 56, 56, 64, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 64, 56, 56, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 56, 56, 128, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 128, 56, 56, 128, 3, 3, 1, 1, 2, 2, 1, 1),
        D(b, 128, 28, 28, 512, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 56, 56, 512, 1, 1, 0, 0, 2, 2, 1, 1),
        D(b, 512, 28, 28, 128, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 128, 28, 28, 128, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 128, 28, 28, 512, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 512, 28, 28, 128, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 128, 28, 28, 128, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 128, 28, 28, 512, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 512, 28, 28, 128, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 128, 28, 28, 128, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 128, 28, 28, 512, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 512, 28, 28, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 28, 28, 256, 3, 3, 1, 1, 2, 2, 1, 1),
        D(b, 256, 14, 14, 1024, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 512, 28, 28, 1024, 1, 1, 0, 0, 2, 2, 1, 1),
        D(b, 1024, 14, 14, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 14, 14, 256, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 256, 14, 14, 1024, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 1024, 14, 14, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 14, 14, 256, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 256, 14, 14, 1024, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 1024, 14, 14, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 14, 14, 256, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 256, 14, 14, 1024, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 1024, 14, 14, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 14, 14, 256, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 256, 14, 14, 1024, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 1024, 14, 14, 256, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 256, 14, 14, 256, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 256, 14, 14, 1024, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 1024, 14, 14, 512, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 512, 14, 14, 512, 3, 3, 1, 1, 2, 2, 1, 1),
        D(b, 512, 7, 7, 2048, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 1024, 14, 14, 2048, 1, 1, 0, 0, 2, 2, 1, 1),
        D(b, 2048, 7, 7, 512, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 512, 7, 7, 512, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 512, 7, 7, 2048, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 2048, 7, 7, 512, 1, 1, 0, 0, 1, 1, 1, 1),
        D(b, 512, 7, 7, 512, 3, 3, 1, 1, 1, 1, 1, 1),
        D(b, 512, 7, 7, 2048, 1, 1, 0, 0, 1, 1, 1, 1),
    ]

    backward_layers = []
    for layer in layers:
        if layer.vstride != 1 or layer.hstride != 1:
            continue
        # w <- y (kn * b * ho * wo)
        backward_layers.append(D(layer.c, layer.b, layer.h, layer.w, layer.kn, layer.ho, layer.wo,
                                 layer.vpadding, layer.hpadding, layer.vstride, layer.hstride,
                                 layer.vdilation, layer.hdilation))
    layers += backward_layers
    t = None
    for layer in layers:
        shape = (layer.kn, layer.c, layer.kh, layer.kw)
        headers, values = time_transpose_1230(shape)
        if t is None:
            t = PrettyTable(['shape', ] + headers)
            # t.set_style(PLAIN_COLUMNS)
            t.align = "r"
        t.add_row([", ".join([str(x) for x in shape]), ] + values)
    print("*************************************************")
    print("** {}  OMP_NUM_THREADS: {}".format(platform.node(), os.environ.get("OMP_NUM_THREADS", 1)))
    print("** All times, except numpy, compared to numpy.")
    print(t)
