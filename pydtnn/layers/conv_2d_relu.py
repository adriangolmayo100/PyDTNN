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
#  with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from contextlib import suppress

from .conv_2d import Conv2D
from ..model import TRAIN_MODE
from ..tracers import PYDTNN_OPS_EVENT, PYDTNN_OPS_EVENTS, PYDTNN_OPS_FORWARD_CONVGEMM, PYDTNN_OPS_FORWARD_RESHAPE_Y


class Conv2DRelu(Conv2D):

    def __init__(self, nfilters=1, filter_shape=(3, 3), padding=0, stride=1,
                 activation="", use_bias=True, weights_initializer="glorot_uniform",
                 biases_initializer="zeros", from_parent=None):
        if from_parent is None:
            super().__init__(nfilters, filter_shape, padding, stride,
                             activation, use_bias, weights_initializer, biases_initializer)
        else:
            with suppress(KeyError):
                from_parent.__dict__.pop("forward")
            self.__dict__.update(from_parent.__dict__)

    def forward(self, x):
        """Version of the forward function that uses the convGemm + Relu"""

        if self.model.mode == TRAIN_MODE:
            raise RuntimeError("Fused layers cannot be used in training mode!")

        biases_vector = self.biases if self.use_bias else None

        self.model.tracer.emit_event(PYDTNN_OPS_EVENT, self.id * PYDTNN_OPS_EVENTS + PYDTNN_OPS_FORWARD_CONVGEMM)
        # @todo: Replace ConvGemm by the actual fused layer
        res = self.cg.conv_gemm(self.weights, x, biases=None,
                                vpadding=self.vpadding, hpadding=self.hpadding,
                                vstride=self.vstride, hstride=self.hstride,
                                biases_vector=biases_vector)
        self.model.tracer.emit_event(PYDTNN_OPS_EVENT, 0)

        self.model.tracer.emit_event(PYDTNN_OPS_EVENT, self.id * PYDTNN_OPS_EVENTS + PYDTNN_OPS_FORWARD_RESHAPE_Y)
        y = res.reshape(self.co, -1, self.ho, self.wo).transpose(1, 0, 2, 3)
        self.model.tracer.emit_event(PYDTNN_OPS_EVENT, 0)

        # @todo: Remove once ConvGemm+Relu is implemented !!
        y[y < 0] = 0

        return y