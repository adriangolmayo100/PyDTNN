#!/bin/bash

export PYTHONOPTIMIZE=2
export PYTHONUNBUFFERED="True"
pydtnn_benchmark \
  --model=alexnet_imagenet \
  --dataset=imagenet \
  --dataset_train_path=/path/to/imagenet \
  --dataset_test_path=/path/to/imagenet \
  --use_synthetic_data=True \
  --test_as_validation=False \
  --batch_size=64 \
  --validation_split=0.2 \
  --steps_per_epoch=0 \
  --num_epochs=30 \
  --evaluate=True \
  --optimizer=sgd \
  --learning_rate=0.01 \
  --momentum=0.9 \
  --loss_func=categorical_cross_entropy \
  --metrics=categorical_accuracy \
  --lr_schedulers=early_stopping,reduce_lr_on_plateau \
  --warm_up_epochs=5 \
  --early_stopping_metric=val_categorical_cross_entropy \
  --early_stopping_patience=10 \
  --reduce_lr_on_plateau_metric=val_categorical_cross_entropy \
  --reduce_lr_on_plateau_factor=0.1 \
  --reduce_lr_on_plateau_patience=5 \
  --reduce_lr_on_plateau_min_lr=0 \
  --parallel=sequential \
  --non_blocking_mpi=False \
  --tracing=False \
  --profile=False \
  --enable_gpu=False \
  --dtype=float32
