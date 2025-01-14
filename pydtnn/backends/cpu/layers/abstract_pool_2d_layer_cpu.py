#
#  This file is part of Python Distributed Training of Neural Networks (PyDTNN)
#
#  Copyright (C) 2021 Universitat Jaume I
#
#  PyDTNN is free software: you can redistribute it and/or modify it under the
#  terms of the GNU General Public License as published by the Free Software
#  Foundation, either version 3 of the License, or (at your option) any later
#  version.
#
#  This program is distributed in the hope that it will be useful, but WITHOUT
#  ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
#  or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
#  License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program. If not, see <https://www.gnu.org/licenses/>.
#

from abc import ABC

from pydtnn.backends.cpu.layers import LayerCPU
from pydtnn.layers import AbstractPool2DLayer
from pydtnn.performance_models import im2col_time, col2im_time
from pydtnn.utils import PYDTNN_TENSOR_FORMAT_NCHW

class AbstractPool2DLayerCPU(LayerCPU, AbstractPool2DLayer, ABC):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def initialize(self, prev_shape, need_dx=True):
        super().initialize(prev_shape, need_dx)

        if self.model.tensor_format == PYDTNN_TENSOR_FORMAT_NCHW:
            setattr(self, "forward", self._forward_nchw_cython)
            setattr(self, "backward", self._backward_nchw_cython)
            # I2C-based implementations have been temporarily discarded
            # setattr(self, "forward", self._forward_nchw_i2c)
            # setattr(self, "backward", self._backward_nchw_i2c)
        else: # Assuming PYDTNN_TENSOR_FORMAT_NHWC
            setattr(self, "forward", self._forward_nhwc_cython)
            setattr(self, "backward", self._backward_nhwc_cython)
            # I2C-based implementations have been temporarily discarded
            # setattr(self, "forward", self._forward_nhwc_i2c)
            # setattr(self, "backward", self._backward_nhwc_i2c)

        self.fwd_time = \
            im2col_time(m=(self.kh * self.kw), n=(self.model.batch_size * self.ho * self.wo * self.ci),
                        cpu_speed=self.model.cpu_speed, memory_bw=self.model.memory_bw,
                        dtype=self.model.dtype)
        self.bwd_time = \
            col2im_time(m=(self.kh * self.kw), n=(self.model.batch_size * self.ho * self.wo * self.ci),
                        cpu_speed=self.model.cpu_speed, memory_bw=self.model.memory_bw,
                        dtype=self.model.dtype) if need_dx else 0

    def forward(self, x):
        """This is a fake forward function. It will be masked on initialization by _forward_i2c or _forward_cg"""
        pass

    def backward(self, dy):
        """This is a fake backward function. It will be masked on initialization by _backward_i2c or _backward_cg"""
        pass
