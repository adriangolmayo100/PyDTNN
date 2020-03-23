""" Python Distributed Training of Neural Networks - PyDTNN

PyDTNN is a light-weight library for distributed Deep Learning training and 
inference that offers an initial starting point for interaction with 
distributed training of (and inference with) deep neural networks. PyDTNN 
priorizes simplicity over efficiency, providing an amiable user interface 
which enables a flat accessing curve. To perform the training and inference 
processes, PyDTNN exploits distributed inter-process parallelism (via MPI) 
for clusters and intra-process (via multi-threading) parallelism to leverage 
the presence of multicore processors at node level.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.

"""

__author__ = "Manuel F. Dolz, Enrique S. Quintana, \
              Mar Catalan, Adrian Castello"
__contact__ = "dolzm@uji.es"
__copyright__ = "Copyright 2020, Universitat Jaume I"
__credits__ = ["Manuel F. Dolz, Enrique S. Quintana", \
               "Mar Catalan", "Adrian Castello"]
__date__ = "2020/03/22"

__email__ =  "dolzm@uji.es"
__license__ = "GPLv3"
__maintainer__ = "Manuel F. Dolz"
__status__ = "Production"
__version__ = "1.0.0"


import numpy as np
import importlib
import random, os, struct

class Dataset:

    def __init__(self, X_train, Y_train,
                       X_val=np.array([]),   Y_val=np.array([]),
                       X_test=np.array([]),  Y_test=np.array([]) ):
        self.X_train, self.Y_train = X_train, Y_train
        self.X_val, self.Y_val = X_val, Y_val
        self.X_test, self.Y_test = X_test, Y_test
        self.train_val_nsamples = X_train.shape[0] + X_val.shape[0]
        self.train_nsamples = self.X_train.shape[0]
        self.test_as_validation = False

    def make_train_val_partitions(self, val_split=0.2):
        pass

    def train_data_generator(self):
        yield (self.X_train, self.Y_train)

    def val_data_generator(self):
        yield (self.X_val, self.Y_val)

    def test_data_generator(self):
        yield (self.X_test, self.Y_test)

    def get_train_val_generator(self, local_batch_size=64, rank=0, nprocs=1, val_split=0.2):
        if val_split > 0 and not self.test_as_validation:
            self.make_train_val_partitions(val_split)
        return ( self.train_batch_generator(self.train_data_generator(), 
                                            local_batch_size, rank, nprocs),
                 self.val_test_batch_generator(self.val_data_generator(), 
                                            rank, nprocs) )

    def get_test_generator(self, local_batch_size=64, rank=0, nprocs=1):
        return self.test_batch_generator(self.test_data_generator(), 
                                            local_batch_size, rank, nprocs)

    def train_batch_generator(self, generator, local_batch_size=64, rank=0, nprocs=1):
        for X_data, Y_data in generator:
            nsamples = X_data.shape[0]
            s = np.arange(nsamples)
            np.random.shuffle(s)
    
            batch_size = local_batch_size * nprocs
            remaining = nsamples % batch_size
            if remaining < (batch_size / 4):
                end_for  = nsamples - batch_size - remaining
                last_batch_size = batch_size + remaining
            else:
                end_for  = nsamples - remaining 
                last_batch_size = remaining
                
            for batch_num in range(0, end_for, batch_size):
                start = batch_num +  rank    * local_batch_size 
                end   = batch_num + (rank+1) * local_batch_size 
                indices = s[start:end]  
                X_local_batch = X_data[indices,...]
                Y_local_batch = Y_data[indices,...]
                yield (X_local_batch, Y_local_batch, batch_size)
    
            local_batch_size = last_batch_size // nprocs
            start = end_for + local_batch_size * rank
            end   = start + local_batch_size
            if rank == nprocs - 1: end = nsamples

            indices = s[start:end]
            X_local_batch = X_data[indices,...]
            Y_local_batch = Y_data[indices,...]
            yield (X_local_batch, Y_local_batch, last_batch_size)

    def val_test_batch_generator(self, generator, rank=0, nprocs=1):
        for X_data, Y_data in generator:
            nsamples = X_data.shape[0]
            batch_size = nsamples // nprocs
            remaining  = nsamples % nprocs

            if rank < remaining:
               start =  rank    * (batch_size+1)
               end   = (rank+1) * (batch_size+1)
            else:
               start = remaining * (batch_size+1) + (rank-remaining) * batch_size
               end   = remaining * (batch_size+1) + (rank-remaining+1) * batch_size

            X_local_batch = X_data[start:end,...]
            Y_local_batch = Y_data[start:end,...]
            yield (X_local_batch, Y_local_batch, nsamples)


class MNIST(Dataset):

    def __init__(self, train_path, test_path, model="", 
                 test_as_validation=False, dtype=np.float32):
        self.train_path = train_path
        self.test_path = test_path
        self.model = model
        self.test_as_validation = test_as_validation
        self.dtype = dtype
        self.nclasses = 10
        self.val_start = 0

        self.train_val_nsamples = 60000
        self.test_nsamples  = 10000

        mnist = None 
        #importlib.import_module("mnist")
        if mnist != None:
            self.X_train_val = mnist.train_images()
            self.Y_train_val = mnist.train_labels()
            self.X_test = mnist.test_images()
            self.Y_test = mnist.test_labels()

        else:
            X_train_filename = "train-images-idx3-ubyte"
            Y_train_filename = "train-labels-idx1-ubyte"       
            X_test_filename  = "t10k-images-idx3-ubyte"
            Y_test_filename  = "t10k-labels-idx1-ubyte"
    
            self.X_train_val = self.__read_file("%s/%s" % (self.train_path, X_train_filename))
            self.Y_train_val = self.__read_file("%s/%s" % (self.train_path, Y_train_filename))
            self.X_test = self.__read_file("%s/%s" % (self.test_path, X_test_filename))
            self.Y_test = self.__read_file("%s/%s" % (self.test_path, Y_test_filename))

        self.X_train_val = self.X_train_val.flatten().reshape(self.train_val_nsamples, 1, 28, 28).astype(self.dtype) / 255.0
        self.Y_train_val = self.__expand_labels(self.Y_train_val.astype(np.int16))
        self.X_train, self.Y_train = self.X_train_val, self.Y_train_val
        self.X_test = self.X_test.flatten().reshape(self.test_nsamples, 1, 28, 28).astype(self.dtype) / 255.0
        self.Y_test = self.__expand_labels(self.Y_test.astype(np.int16))
        self.train_nsamples = self.X_train_val.shape[0]

        if self.test_as_validation:
            print("  Using test as validation data - val_split parameter is ignored!")
            self.X_val, self.Y_val = self.X_test, self.Y_test
            self.X_train, self.Y_train = self.X_train_val, self.Y_train_val
            self.train_nsamples = self.X_train.shape[0]

    def __read_file(self, filename):
        with open(filename, 'rb') as f:
            zero, data_type, dims = struct.unpack('>HBB', f.read(4))
            shape = tuple(struct.unpack('>I', f.read(4))[0] for d in range(dims))
            return np.fromstring(f.read(), dtype=np.uint8).reshape(shape)

    def __expand_labels(self, Y):
        Y_expanded = np.zeros((Y.shape[0], self.nclasses))
        Y_expanded[np.arange(Y.shape[0]), Y] = 1
        return Y_expanded

    def make_train_val_partitions(self, val_split=0.2):
        assert 0 <= val_split < 1
        self.val_size = int(self.train_val_nsamples * val_split)

        end = self.val_start + self.val_size
        if end > self.X_train_val.shape[0]:
            val_indices = np.arange(self.val_start, self.X_train_val.shape[0])
            self.val_start = self.val_size - val_indices.shape[0]
            val_indices = np.concatenate((val_indices, np.arange(0, self.val_start)))
        else:
            val_indices = np.arange(self.val_start, end)
            self.val_start = end

        train_indices = np.setdiff1d(np.arange(self.train_val_nsamples), val_indices)

        self.X_train = self.X_train_val[train_indices,...]
        self.Y_train = self.Y_train_val[train_indices,...]
        self.X_val = self.X_train_val[val_indices,...]
        self.Y_val = self.Y_train_val[val_indices,...]
        self.train_nsamples = self.X_train.shape[0]

    def adjust_steps_per_epoch(self, steps_per_epoch, local_batch_size, nprocs):
        if steps_per_epoch > 0:
            subset_size = local_batch_size * nprocs * steps_per_epoch
            if subset_size > self.X_train_val.shape[0]:
                scale = math.ceil(subset_size/float(self.X_train_val.shape[0]))
                self.X_train_val = np.tile(self.X_train_val, scale)[:subset_size,...]
                self.Y_train_val = np.tile(self.Y_train_val, scale)[:subset_size,...]
            else:
                self.X_train_val = self.X_train_val[:subset_size,...]
                self.Y_train_val = self.Y_train_val[:subset_size,...]
            self.train_val_nsamples = self.X_train_val.shape[0]
            self.train_nsamples = self.train_val_nsamples

            self.X_train, self.Y_train = self.X_train_val, self.Y_train_val
            self.X_val, self.Y_val = np.array([]), self.np.array([])
 
class ImageNet(Dataset):
        
    def __init__(self, train_path, test_path, model="", 
                 test_as_validation=False, dtype=np.float32):
        self.train_path = self.val_path = train_path
        self.test_path = test_path
        self.model = model
        self.test_as_validation = test_as_validation
        self.dtype = dtype
        self.nclasses = 1000
        self.val_start = 0

        self.train_val_files = os.listdir(self.train_path)
        self.images_per_file = 1251
        self.train_val_nsamples = len(self.train_val_files) * self.images_per_file
        self.train_files = self.train_val_files

        self.test_files  = os.listdir(self.test_path)
        self.test_nfiles = len(self.test_files)
        self.test_nsamples  = 10000

        self.train_nsamples = self.train_val_nsamples

        if self.test_as_validation:
            print("  Using test as validation data - val_split parameter is ignored!")
            self.val_path, self.val_files = self.test_path, self.test_files
            self.train_files = self.train_val_files
            self.train_nsamples = self.train_val_nsamples

    def __trim_image(self, X):
        if "vgg" in self.model: # for VGG models input shape must be (3,224,224)
            return X[...,1:225,1:225]
        else: return X

    def __expand_labels(self, Y):
        Y_expanded = np.zeros((Y.shape[0], self.nclasses))
        Y_expanded[np.arange(Y.shape[0]), (Y.flatten()-1)] = 1
        return Y_expanded

    def train_data_generator(self):
        for f in range(len(self.train_files)):
            values = np.load("%s/%s" % (self.train_path, self.train_files[f]))
            x = self.__trim_image(values['x'].astype(self.dtype)) / 255.0
            y = self.__expand_labels(values['y'].astype(np.int16))
            yield (x, y)

    def val_data_generator(self):
        for f in range(len(self.val_files)):
            values = np.load("%s/%s" % (self.val_path, self.val_files[f]))
            x = self.__trim_image(values['x'].astype(self.dtype)) / 255.0
            y = self.__expand_labels(values['y'].astype(np.int16))        
            yield (x, y)

    def test_data_generator(self):
        for f in range(len(self.test_files)):
            values = np.load("%s/%s" % (self.test_path, self.test_files[f]))
            x = self.__trim_image(values['x'].astype(self.dtype)) / 255.0
            y = self.__expand_labels(values['y'].astype(np.int16))  
            yield (x, y)

    def make_train_val_partitions(self, val_split=0.2):
        assert 0 <= val_split < 1        
        self.val_size = int((self.train_val_nsamples * val_size) / self.images_per_file)

        end = self.val_start + self.val_size
        if end > self.nfiles:
            val_indices = np.arange(self.val_start, self.nfiles)
            self.val_start = self.val_size - val_indices.shape[0]
            self.val_files = np.concatenate((val_indices, np.arange(0, self.val_start)))
        else:
            self.val_files = np.arange(self.val_start, end)
            self.val_start = end

        self.train_files = np.setdiff1d(np.arange(self.train_val_files), val_indices)
        self.train_nsamples = self.train_files * self.images_per_file

    def adjust_steps_per_epoch(self, steps_per_epoch, local_batch_size, nprocs):
        if steps_per_epoch > 0:
            subset_size = local_batch_size * nprocs * steps_per_epoch
            if subset_size < self.train_val_nsamples:
                subset_files = subset_size // self.images_per_file
                self.train_val_files = self.train_val_files[:subset_files]
                self.train_val_nsamples = len(self.train_val_files) * self.images_per_file
                self.train_nsamples = self.train_val_nsamples
                self.train_files = self.train_val_files
                self.val_files = []

