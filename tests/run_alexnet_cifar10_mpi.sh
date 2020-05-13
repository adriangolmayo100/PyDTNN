#!/bin/bash

# set -x # Debugging flag
# export PYTHONPATH=/home/dolzm/install/extrae-3.6.0/libexec:$PYTHONPATH
# export EXTRAE_CONFIG_FILE=./extrae.xml
# export MKL_NUM_THREADS=12
# export EXTRAE_ON=1
# 
# EXTRAELIB=/home/dolzm/install/extrae-3.6.0/lib/libompitrace.so

NUMNODES=15
NUMPROCS=15
PROCS_PER_NODE=$(($PROCS / $NUMNODES))

NODETYPE=hexa
LASTH=`echo $NUMPR - 1 | bc`
HOSTS=$(for i in `seq 0 $LASTH`; do printf "%s%02d," ${NODETYPE} ${i}; done)

mpirun -genv LD_PRELOAD $EXTRAELIB -iface ib0 \
       -hosts $HOSTS -ppn $PROCS_PER_NODE -np $NUMPROCS \
   python3 -u benchmarks_CNN.py \
         --model=alexnet_cifar10 \
         --dataset=cifar10 \
         --dataset_train_path=/Users/mdolz/Downloads/cifar-10-batches-py/ \
         --dataset_test_path=/Users/mdolz/Downloads/cifar-10-batches-py/ \
         --test_as_validation=False \
         --batch_size=64 \
         --validation_split=0.2 \
         --steps_per_epoch=0 \
         --num_epochs=30 \
         --evaluate=True \
         --optimizer=SGDMomentum \
         --learning_rate=1 \
         --momentum=0.9 \
         --loss_func=categorical_accuracy,categorical_cross_entropy \
         --lr_schedulers=early_stopping,reduce_lr_on_plateau \
         --warm_up_batches=500 \
         --early_stopping_metric=val_categorical_cross_entropy \
         --early_stopping_patience=10 \
         --reduce_lr_on_plateau_metric=val_categorical_cross_entropy \
         --reduce_lr_on_plateau_factor=0.1 \
         --reduce_lr_on_plateau_patience=5 \
         --reduce_lr_on_plateau_min_lr=0 \
         --parallel=data \
         --non_blocking_mpi=False \
         --tracing=False \
         --profile=False \
         --enable_gpu=False \
         --dtype=float32
