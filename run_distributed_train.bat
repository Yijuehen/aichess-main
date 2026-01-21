@echo off
REM 多GPU分布式训练启动脚本 (Windows)
REM 使用PyTorch的DistributedDataParallel进行多GPU训练

REM 设置环境变量
set CUDA_VISIBLE_DEVICES=0,1
set MASTER_ADDR=localhost
set MASTER_PORT=29500

REM 设置分布式训练环境变量（torch.distributed.launch会自动设置RANK、LOCAL_RANK等）
set DISTIBUTED_TRAINING=true
set BATCH_SIZE=512

echo ==================================
echo 多GPU分布式训练
echo ==================================
echo GPU数量: 2
echo Batch size: %BATCH_SIZE%
echo Master地址: %MASTER_ADDR%:%MASTER_PORT%
echo ==================================

REM 启动分布式训练
REM 获取脚本所在目录
set SCRIPT_DIR=%~dp0

python -m torch.distributed.launch ^
    --nproc_per_node=2 ^
    --nnodes=1 ^
    --node_rank=0 ^
    --master_addr=%MASTER_ADDR% ^
    --master_port=%MASTER_PORT% ^
    %SCRIPT_DIR%train.py

echo 训练完成！
pause
