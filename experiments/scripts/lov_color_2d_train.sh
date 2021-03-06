#!/bin/bash

set -x
set -e

export PYTHONUNBUFFERED="True"
export CUDA_VISIBLE_DEVICES=$1

LOG="experiments/logs/lov_color_2d_train.txt.`date +'%Y-%m-%d_%H-%M-%S'`"
exec &> >(tee -a "$LOG")
echo Logging output to "$LOG"

# train FCN for single frames
export LD_PRELOAD=/usr/lib/libtcmalloc.so.4

time ./tools/train_net.py --gpu 0 \
  --network vgg16_convs \
  --weights data/imagenet_models/vgg16.npy \
  --imdb lov_train \
  --cfg experiments/cfgs/lov_color_2d.yml \
  --cad data/LOV/models.txt \
  --pose data/LOV/poses.txt \
  --iters 160000
  # --ckpt data/demo_models/vgg16_fcn_color_single_frame_2d_pose_add_lov_iter_160000.ckpt
