#!/bin/bash
# 多GPU分布式训练启动脚本
# 使用PyTorch的DistributedDataParallel进行多GPU训练

# 设置环境变量
export CUDA_VISIBLE_DEVICES=0,1,2,3  # 使用GPU 0-3，根据你的GPU数量调整
export MASTER_ADDR=localhost
export MASTER_PORT=29500

# 设置分布式训练环境变量（torch.distributed.launch会自动设置RANK、LOCAL_RANK等）
export DISTIBUTED_TRAINING=true
export BATCH_SIZE=512  # 总batch size

echo "=================================="
echo "多GPU分布式训练"
echo "=================================="
echo "GPU数量: 4"
echo "Batch size: $BATCH_SIZE"
echo "Master地址: $MASTER_ADDR:$MASTER_PORT"
echo "=================================="

# 启动分布式训练
# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

python -m torch.distributed.launch \
    --nproc_per_node=4 \
    --nnodes=1 \
    --node_rank=0 \
    --master_addr=$MASTER_ADDR \
    --master_port=$MASTER_PORT \
    $SCRIPT_DIR/train.py

echo "训练完成！"
