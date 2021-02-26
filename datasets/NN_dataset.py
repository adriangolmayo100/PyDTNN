""" Python Distributed Training of Neural Networks - PyDTNN

PyDTNN is a light-weight library for distributed Deep Learning training and 
inference that offers an initial starting point for interaction with 
distributed training of (and inference with) deep neural networks. PyDTNN 
priorizes simplicity over efficiency, providing an amiable user interface 
which enables a flat accessing curve. To perform the training and inference 
processes, PyDTNN exploits distributed inter-process parallelism (via MPI) 
for clusters and intra-process (via multi-threading) parallelism to leverage 
the presence of multicore processors and GPUs at node level. For that, PyDTNN 
uses MPI4Py for message-passing, BLAS calls via NumPy for multicore processors
and PyCUDA+cuDNN+cuBLAS for NVIDIA GPUs.

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
__version__ = "1.1.0"


import numpy as np
import importlib, gc
import random, os, struct, math
from skimage.transform import resize

import threading
import sys

if sys.version_info >= (3, 0):
    import queue as Queue
else:
    import Queue


class BackgroundGenerator(threading.Thread):
    def __init__(self, generator, max_prefetch=1):
        threading.Thread.__init__(self)
        self.queue = Queue.Queue(max_prefetch)
        self.generator = generator
        self.daemon = True
        self.start()

    def run(self):
        for item in self.generator:
            self.queue.put(item)
        self.queue.put(None)

    def next(self):
        next_item = self.queue.get()
        if next_item is None:
            raise StopIteration
        return next_item

    # Python 3 compatibility
    def __next__(self):
        return self.next()

    def __iter__(self):
        return self

def flip_images(data, prob=0.5):
    n, c, h, w = data.shape
    limit = min(n, int(n * prob))
    s = np.arange(n)
    np.random.shuffle(s)
    s = s[:limit]
    data[s,...] = np.flip(data[s,...], axis=-1)
    return data

def crop_images(data, crop_size, prob=0.5):
    n, c, h, w = data.shape
    crop_size = min(crop_size, h, w)
    limit = min(n, int(n * prob))
    s = np.arange(n)
    np.random.shuffle(s)
    s = s[:limit]
    t = np.random.randint(0, h - crop_size, (limit,))
    l = np.random.randint(0, w - crop_size, (limit,))
    for i, ri in enumerate(s):
        b, r = t[i]+crop_size, l[i]+crop_size
        # batch[ri,...] = resize(batch[ri,:,t[i]:b,l[i]:r], (ri.size,c,h,w))
        data[ri,:,:t[i],:l[i]] = 0.0
        data[ri,:,b:,r:] = 0.0
        data[ri,...] = np.roll(data[ri,...], np.random.randint(-t[i],(h-b)), axis=1) 
        data[ri,...] = np.roll(data[ri,...], np.random.randint(-l[i],(w-r)), axis=2) 
    return data


class Dataset:

    def __init__(self, X_train=np.array([]), Y_train=np.array([]),
                       X_val=np.array([]),   Y_val=np.array([]),
                       X_test=np.array([]),  Y_test=np.array([])):
        self.X_train, self.Y_train = X_train, Y_train
        self.X_val, self.Y_val = X_val, Y_val
        self.X_test, self.Y_test = X_test, Y_test
        self.train_val_nsamples = X_train.shape[0] + X_val.shape[0]
        self.train_nsamples = self.X_train.shape[0]
        self.test_as_validation = False

    def make_train_val_partitions(self, val_split=0.2):
        pass

    def train_data_generator(self, batch_size):
        X_data, Y_data = self.X_train, self.Y_train
        # Use data augmentation, if used we preserve original data
        if self.flip_images or self.crop_images:
            X_data = X_data.copy()
        if self.flip_images:
            X_data = flip_images(X_data, self.flip_images_prob)
        if self.crop_images:
            X_data = crop_images(X_data, self.crop_images_size, self.crop_images_prob)
        yield X_data, Y_data

    def val_data_generator(self, batch_size):
        yield (self.X_val, self.Y_val)

    def test_data_generator(self, batch_size):
        yield (self.X_test, self.Y_test)

    def get_train_val_generator(self, local_batch_size=64, rank=0, nprocs=1, val_split=0.2):
        batch_size = local_batch_size * nprocs
        return ( self.batch_generator(self.train_data_generator(batch_size), 
                                      local_batch_size, rank, nprocs, shuffle=True),
                 self.batch_generator(self.val_data_generator(batch_size), 
                                      local_batch_size, rank, nprocs, shuffle=False) )

    def get_test_generator(self, local_batch_size=64, rank=0, nprocs=1):
        # Fixed batch size for testing:
        #   This is done to ensure that the returned X_data, Y_data to the
        #   val_test_batch_generator will be larger enough to feed all processes.
        # local_batch_size = 64
        batch_size = local_batch_size * nprocs
        return self.batch_generator(self.test_data_generator(batch_size), 
                                      local_batch_size, rank, nprocs, shuffle=False)

    def batch_generator(self, generator, local_batch_size=64, rank=0, nprocs=1, shuffle=True):
        batch_size = local_batch_size * nprocs

        for X_data, Y_data in BackgroundGenerator(generator):
            nsamples = X_data.shape[0]
            s = memoryview(np.arange(nsamples))
            if shuffle: np.random.shuffle(s)
            
            last_batch_size = nsamples % batch_size
            if last_batch_size < nprocs: last_batch_size += batch_size
            end_for = nsamples - last_batch_size

            # Generate batches
            for batch_num in range(0, end_for, batch_size):
                start = batch_num +  rank    * local_batch_size 
                end   = batch_num + (rank+1) * local_batch_size 
                indices = s[start:end]  
                X_local_batch = X_data[indices,...]
                Y_local_batch = Y_data[indices,...]
                yield (X_local_batch, Y_local_batch, batch_size)
    
            # Generate last batch
            if last_batch_size > 0:
                last_local_batch_size = last_batch_size // nprocs
                remaining = last_batch_size % nprocs
                start = end = end_for
                if rank < remaining:
                    start +=  rank    * (last_local_batch_size+1)
                    end   += (rank+1) * (last_local_batch_size+1)
                else:
                    start += remaining * (last_local_batch_size+1) + (rank-remaining) * last_local_batch_size
                    end   += remaining * (last_local_batch_size+1) + (rank-remaining+1) * last_local_batch_size
                indices = s[start:end]
                X_local_batch = X_data[indices,...]
                Y_local_batch = Y_data[indices,...]
                yield (X_local_batch, Y_local_batch, last_batch_size)

    #def val_test_batch_generator(self, generator, rank=0, nprocs=1):
    #    for X_data, Y_data in generator:
    #        batch_size = X_data.shape[0]
    #        local_batch_size = batch_size // nprocs
    #        remaining  = batch_size % nprocs
    #
    #        if rank < remaining:
    #           start =  rank    * (local_batch_size+1)
    #           end   = (rank+1) * (local_batch_size+1)
    #        else:
    #           start = remaining * (local_batch_size+1) + (rank-remaining) * local_batch_size
    #           end   = remaining * (local_batch_size+1) + (rank-remaining+1) * local_batch_size
    #
    #        X_local_batch = X_data[start:end,...]
    #        Y_local_batch = Y_data[start:end,...]
    #        yield (X_local_batch, Y_local_batch, batch_size)


class MNIST(Dataset):

    def __init__(self, train_path, test_path, model="", test_as_validation=False,
                 flip_images=False, flip_images_prob=0.5, 
                 crop_images=False, crop_images_size=14, crop_images_prob=0.5, 
                 dtype=np.float32, use_synthetic_data=False):
        self.train_path = train_path
        self.test_path = test_path
        self.model = model
        self.test_as_validation = test_as_validation
        self.flip_images = flip_images
        self.flip_images_prob = flip_images_prob
        self.crop_images = crop_images
        self.crop_images_size = crop_images_size
        self.crop_images_prob = crop_images_prob
        self.dtype = dtype
        self.use_synthetic_data = use_synthetic_data
        self.nclasses = 10
        #self.val_start = 0

        self.train_val_nsamples = 60000
        self.test_nsamples  = 10000
        self.shape = (1, 28, 28)

        self.val_start = np.random.randint(0, high=self.train_val_nsamples)

        if self.use_synthetic_data:
            self.X_train_val, self.Y_train_val = \
                np.empty( (self.train_val_nsamples * np.prod(self.shape) ), dtype=self.dtype), \
                np.zeros( (self.train_val_nsamples ), dtype=self.dtype)
            self.X_test, self.Y_test = \
                np.empty( (self.test_nsamples * np.prod(self.shape) ), dtype=self.dtype), \
                np.zeros( (self.test_nsamples ), dtype=self.dtype)           
        else:
            X_train_fname = "train-images-idx3-ubyte"
            Y_train_fname = "train-labels-idx1-ubyte"       
            X_test_fname  = "t10k-images-idx3-ubyte"
            Y_test_fname  = "t10k-labels-idx1-ubyte"
    
            self.X_train_val = self.__read_file("%s/%s" % (self.train_path, X_train_fname))
            self.Y_train_val = self.__read_file("%s/%s" % (self.train_path, Y_train_fname))
            self.X_test = self.__read_file("%s/%s" % (self.test_path, X_test_fname))
            self.Y_test = self.__read_file("%s/%s" % (self.test_path, Y_test_fname))

        self.X_train_val = self.X_train_val.flatten().reshape(self.train_val_nsamples, *self.shape).astype(self.dtype) / 255.0
        self.Y_train_val = self.__one_hot_encoder(self.Y_train_val.astype(np.int16))
        self.X_test = self.X_test.flatten().reshape(self.test_nsamples, *self.shape).astype(self.dtype) / 255.0
        self.Y_test = self.__one_hot_encoder(self.Y_test.astype(np.int16))

        if self.test_as_validation:
            # print("  Using test as validation data - val_split parameter is ignored!")
            self.X_val, self.Y_val = self.X_test, self.Y_test
            self.X_train, self.Y_train = self.X_train_val, self.Y_train_val
            self.train_nsamples = self.X_train.shape[0]

    def __read_file(self, fname):
        with open(fname, 'rb') as f:
            zero, data_type, dims = struct.unpack('>HBB', f.read(4))
            shape = tuple(struct.unpack('>I', f.read(4))[0] for d in range(dims))
            return np.fromstring(f.read(), dtype=np.uint8).reshape(shape)

    def __one_hot_encoder(self, Y):
        Y_one_hot = np.zeros((Y.shape[0], self.nclasses), dtype=self.dtype, order="C")
        Y_one_hot[np.arange(Y.shape[0]), Y] = 1
        return Y_one_hot

    def make_train_val_partitions(self, val_split=0.2):
        if self.test_as_validation: return
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
            if self.test_as_validation:
                self.X_train, self.Y_train = self.X_train_val, self.Y_train_val  

class CIFAR10(Dataset):

    def __init__(self, train_path, test_path, model="", test_as_validation=False, 
                 flip_images=False, flip_images_prob=0.5, 
                 crop_images=False, crop_images_size=16, crop_images_prob=0.5, 
                 dtype=np.float32, use_synthetic_data=False):
        self.train_path = train_path
        self.test_path = test_path
        self.model = model
        self.test_as_validation = test_as_validation
        self.flip_images = flip_images
        self.flip_images_prob = flip_images_prob
        self.crop_images = crop_images
        self.crop_images_size = crop_images_size
        self.crop_images_prob = crop_images_prob
        self.dtype = dtype
        self.use_synthetic_data = use_synthetic_data
        self.nclasses = 10
        self.val_start = 0

        self.train_val_nsamples = 50000
        self.test_nsamples  = 10000

        self.images_per_file = 10000
        self.shape = (3, 32, 32)

        XY_train_fname = "data_batch_%d.bin"
        XY_test_fname  = "test_batch.bin"

        for b in range(1, 6):
            if self.use_synthetic_data:
                self.X_train_val_aux, self.Y_train_val_aux = \
                    np.empty( (self.images_per_file * np.prod(self.shape) ), dtype=self.dtype), \
                    np.zeros( (self.images_per_file ), dtype=self.dtype)
            else:
                self.X_train_val_aux, self.Y_train_val_aux = \
                    self.__read_file("%s/%s" % (self.train_path, (XY_train_fname % (b))))
            if b == 1:
                self.X_train_val, self.Y_train_val = self.X_train_val_aux, self.Y_train_val_aux
            else:
                self.X_train_val = np.concatenate((self.X_train_val, self.X_train_val_aux), axis=0)
                self.Y_train_val = np.concatenate((self.Y_train_val, self.Y_train_val_aux), axis=0)

        if self.use_synthetic_data:
            self.X_test, self.Y_test = \
                np.empty( (self.images_per_file * np.prod(self.shape) ), dtype=self.dtype), \
                np.zeros( (self.images_per_file ), dtype=self.dtype)
        else:
            self.X_test, self.Y_test = self.__read_file("%s/%s" % (self.test_path, XY_test_fname))

        self.X_train_val = self.X_train_val.reshape(self.train_val_nsamples, *self.shape).astype(self.dtype) / 255.0
        # self.X_train_val = self.__normalize_image(self.X_train_val)
        self.Y_train_val = self.__one_hot_encoder(self.Y_train_val.astype(np.int16))
        self.X_test = self.X_test.reshape(self.test_nsamples, *self.shape).astype(self.dtype) / 255.0
        # self.X_test = self.__normalize_image(self.X_test)
        self.Y_test = self.__one_hot_encoder(self.Y_test.astype(np.int16))

        if self.test_as_validation:
            # print("  Using test as validation data - val_split parameter is ignored!")
            self.X_val, self.Y_val = self.X_test, self.Y_test
            self.X_train, self.Y_train = self.X_train_val, self.Y_train_val
            self.train_nsamples = self.X_train.shape[0]

    def __read_file(self, fname):
        with open(fname, 'rb') as f:
            im = np.frombuffer(f.read(), dtype=np.uint8).reshape(self.images_per_file, np.prod(self.shape)+1)
            Y, X = im[:,0].flatten(), im[:,1:].flatten()
            return X, Y

    def __normalize_image(self, X):
        mean = np.mean(X, axis=(0, 2, 3))
        std  = np.std(X, axis=(0, 2, 3))
        for c in range(3):
            X[:,c,...] = (X[:,c,...] - mean[c]) / std[c]
        return X

    def __one_hot_encoder(self, Y):
        Y_one_hot = np.zeros((Y.shape[0], self.nclasses), dtype=self.dtype, order="C")
        Y_one_hot[np.arange(Y.shape[0]), Y] = 1
        return Y_one_hot

    def make_train_val_partitions(self, val_split=0.2):
        if self.test_as_validation: return
        assert 0 <= val_split < 1
        val_size = int(self.train_val_nsamples * val_split)

        end = self.val_start + val_size
        if end > self.X_train_val.shape[0]:
            val_indices = np.arange(self.val_start, self.X_train_val.shape[0])
            self.val_start = val_size - val_indices.shape[0]
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
            if self.test_as_validation:
                self.X_train, self.Y_train = self.X_train_val, self.Y_train_val            

 
class ImageNet(Dataset):
        
    def __init__(self, train_path, test_path, model="", test_as_validation=False, 
                 flip_images=False, flip_images_prob=0.5, 
                 crop_images=False, crop_images_size=112, crop_images_prob=0.5, 
                 dtype=np.float32, use_synthetic_data=False):
        self.train_path = self.val_path = train_path
        self.test_path = test_path
        self.model = model
        self.flip_images = flip_images
        self.flip_images_prob = flip_images_prob
        self.crop_images = crop_images
        self.crop_images_size = crop_images_size
        self.crop_images_prob = crop_images_prob
        self.test_as_validation = test_as_validation
        self.dtype = dtype
        self.use_synthetic_data = use_synthetic_data
        self.nclasses = 1000
        self.val_start = 0
        
        self.images_per_train_file, self.images_per_test_file = 1251, 390
        self.shape = (3, 227, 227)

        # Variables for training + validation datasets
        if self.use_synthetic_data:
            self.n_train_val_files = 1024            
            self.train_val_files = [''] * self.n_train_val_files          
        else:
            self.train_val_files = os.listdir(self.train_path)
            self.train_val_files.sort()
            self.n_train_val_files = len(self.train_val_files)

        self.train_val_nsamples = self.n_train_val_files * self.images_per_train_file

        # Variables for testing dataset
        if self.use_synthetic_data:
            self.n_test_files = 128
            self.test_files = [''] * self.n_test_files
        else:
            self.test_files = os.listdir(self.test_path)
            self.test_files.sort()
            self.n_test_files = len(self.test_files)

        self.test_nsamples = self.n_test_files * self.images_per_test_file

        if self.test_as_validation:
            # print("  Using test as validation data - val_split parameter is ignored!")
            self.val_path, self.val_files = self.test_path, self.test_files
            self.train_files = self.train_val_files
            self.train_nsamples = self.train_val_nsamples

    def __normalize_image(self, X):
        if "alexnet" not in self.model: # for VGG, ResNet and other models input shape must be (3,224,224)
            return X[...,1:225,1:225]
        mean = np.array([0.485, 0.456, 0.406])
        std  = np.array([0.229, 0.224, 0.225])
        for c in range(3):
            X[:,c,...] = ((X[:,c,...] / 255.0) - mean[c]) / std[c]
        return X

    def __one_hot_encoder(self, Y):
        Y_one_hot = np.zeros((Y.shape[0], self.nclasses), dtype=self.dtype, order="C")
        Y_one_hot[np.arange(Y.shape[0]), Y] = 1
        return Y_one_hot

    def data_generator(self, path, files, batch_size, op="train"):
        # For batch sizes > 1251 it is needed to concatenate more than one file of 1251 samples
        # In this case we yield bigger chunks of size batch_size
        images_per_file = {"train": self.images_per_train_file, \
                           "test":  self.images_per_test_file}[op]
        in_files = files.copy()
        np.random.shuffle(in_files)

        if batch_size > self.images_per_train_file:
            X_buffer, Y_buffer = np.array([]), np.array([])
            
            for f in in_files:
                if self.use_synthetic_data:
                    images = {"train": self.images_per_train_file,
                              "test": self.images_per_test_file}[op]
                    values = {"x": np.empty( (images, *self.shape), dtype=self.dtype), 
                              "y": np.zeros( (images, 1), dtype=self.dtype)}
                else:
                    values = np.load("%s/%s" % (path, f))

                X_data = self.__normalize_image(values['x'].astype(self.dtype))
                Y_data = self.__one_hot_encoder(values['y'].astype(np.int16).flatten() - 1)
                if X_buffer.size == 0:
                    X_buffer, Y_buffer = X_data, Y_data
                else:
                    X_buffer = np.concatenate((X_buffer, X_data), axis=0)
                    Y_buffer = np.concatenate((Y_buffer, Y_data), axis=0)
    
                if X_buffer.shape[0] >= batch_size:
                    if self.flip_images:
                        X_buffer = flip_images(X_buffer, self.flip_images_prob)
                    if self.crop_images:
                        X_buffer = crop_images(X_buffer, self.crop_images_size, self.crop_images_prob)
                    yield (X_buffer[:batch_size,...], Y_buffer[:batch_size,...])
                    X_buffer = X_buffer[batch_size:,...]
                    Y_buffer = Y_buffer[batch_size:,...]
                    gc.collect()
    
            if X_buffer.shape[0] > 0:
                yield (X_buffer, Y_buffer)
                gc.collect()

        # For batch_sizes <= 1251, complete files of 1251 samples are yield
        else:
            for f in in_files:
                if self.use_synthetic_data:
                    images = {"train": self.images_per_train_file,
                              "test": self.images_per_test_file}[op]
                    values = {"x": np.empty( (images, *self.shape), dtype=self.dtype), 
                              "y": np.zeros( (images, 1), dtype=self.dtype)}
                else:
                    values = np.load("%s/%s" % (path, f))                

                X_data = self.__normalize_image(values['x'].astype(self.dtype))
                Y_data = self.__one_hot_encoder(values['y'].astype(np.int16).flatten() - 1)
                if self.flip_images:
                    X_data = flip_images(X_data, self.flip_images_prob)
                if self.crop_images:
                    X_data = crop_images(X_data, self.crop_images_size, self.crop_images_prob)
                yield (X_data, Y_data)
                gc.collect()

    def train_data_generator(self, batch_size):
        return self.data_generator(self.train_path, self.train_files, batch_size, op="train")

    def val_data_generator(self, batch_size):
        return self.data_generator(self.val_path, self.val_files, batch_size, op="train")

    def test_data_generator(self, batch_size):
        return self.data_generator(self.test_path, self.test_files, batch_size, op="test")

    def make_train_val_partitions(self, val_split=0.2):
        if self.test_as_validation:
            return
        assert 0 <= val_split < 1        
        self.val_size = int((self.train_val_nsamples * val_split) / self.images_per_train_file)

        end = self.val_start + self.val_size
        if end > self.n_train_val_files:
            val_idx_files = np.arange(self.val_start, self.n_train_val_files)
            self.val_start = self.val_size - val_idx_files.shape[0]
            val_idx_files = np.concatenate((val_idx_files, np.arange(0, self.val_start)))
        else:
            val_idx_files = np.arange(self.val_start, end)
            self.val_start = end

        train_idx_files = np.setdiff1d(np.arange(self.n_train_val_files), val_idx_files)
        self.train_files = [self.train_val_files[f] for f in train_idx_files]
        self.val_files = [self.train_val_files[f] for f in val_idx_files]
        self.train_nsamples = len(self.train_files) * self.images_per_train_file

    def adjust_steps_per_epoch(self, steps_per_epoch, local_batch_size, nprocs):
        if steps_per_epoch > 0:
            subset_size = local_batch_size * nprocs * steps_per_epoch
            if subset_size < self.train_val_nsamples:
                subset_files = max(1, subset_size // self.images_per_train_file)
                self.train_val_files = self.train_val_files[:subset_files]
                self.n_train_val_files = len(self.train_val_files)
                self.train_val_nsamples = self.n_train_val_files * self.images_per_train_file
                self.train_nsamples = self.train_val_nsamples
                subset_test_files = max(1, subset_size // self.images_per_test_file)
                self.test_files = self.test_files[:subset_test_files]
                self.n_test_files = len(self.test_files)
                self.test_nsamples = self.n_test_files * self.images_per_test_file
