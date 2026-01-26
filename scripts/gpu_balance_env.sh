#!/bin/bash
# GPU负载均衡环境设置脚本
#
# 功能:
# 1. 调用Python调度器获取可用GPU
# 2. 设置CUDA_VISIBLE_DEVICES环境变量
# 3. 输出分配的GPU ID列表
#
# 使用方法:
#   source gpu_balance_env.sh  # 在当前shell中执行
#   export COLLECT_GPUS=$(gpu_balance_env.sh)  # 或获取GPU列表

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 检查GPU负载均衡是否启用
if [ "$GPU_BALANCING_ENABLED" != "true" ]; then
    # 未启用时返回所有可用GPU
    if command -v nvidia-smi &> /dev/null; then
        GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader | head -n 1)
        if [ -n "$GPU_COUNT" ] && [ "$GPU_COUNT" -gt 0 ]; then
            # 生成GPU列表: 0,1,2,...
            GPUS=$(seq 0 $((GPU_COUNT - 1)) | tr '\n' ',' | sed 's/,$//')
            echo "$GPUS"
            exit 0
        fi
    fi
    echo "0"  # 默认使用GPU 0
    exit 0
fi

# 检查Python环境
if ! command -v python &> /dev/null; then
    echo "❌ Python未找到" >&2
    echo "0"  # 降级到GPU 0
    exit 1
fi

# 检查gpu_balance模块
if ! python -c "import gpu_balance" 2>/dev/null; then
    echo "⚠️  gpu_balance模块未找到，使用静态分配" >&2
    # 降级到静态检测
    if command -v nvidia-smi &> /dev/null; then
        GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader | head -n 1)
        if [ -n "$GPU_COUNT" ] && [ "$GPU_COUNT" -gt 0 ]; then
            GPUS=$(seq 0 $((GPU_COUNT - 1)) | tr '\n' ',' | sed 's/,$//')
            echo "$GPUS"
            exit 0
        fi
    fi
    echo "0"
    exit 1
fi

# 检查Redis连接
if ! redis-cli ping &> /dev/null; then
    echo "⚠️  Redis未运行，使用静态分配" >&2
    # 降级到静态检测
    if command -v nvidia-smi &> /dev/null; then
        GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader | head -n 1)
        if [ -n "$GPU_COUNT" ] && [ "$GPU_COUNT" -gt 0 ]; then
            GPUS=$(seq 0 $((GPU_COUNT - 1)) | tr '\n' ',' | sed 's/,$//')
            echo "$GPUS"
            exit 0
        fi
    fi
    echo "0"
    exit 1
fi

# 调用Python调度器获取GPU分配
# 参数:
#   $1: 任务类型 (collect/train)
#   $2: 需要的GPU数量 (可选，默认=-1表示全部可用)
TASK_TYPE="${1:-collect}"
GPU_COUNT="${2:--1}"

ALLOCATED_GPUS=$(python -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
from gpu_balance.task_scheduler import TaskScheduler

try:
    scheduler = TaskScheduler()
    gpus = scheduler.allocate_gpus('$TASK_TYPE', count=$GPU_COUNT)
    if gpus:
        print(','.join(map(str, gpus)))
    else:
        print('0')  # 无可用GPU
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    print('0')
" 2>&1)

# 检查返回值
if echo "$ALLOCATED_GPUS" | grep -q "^Error:"; then
    echo "⚠️  GPU分配失败: $ALLOCATED_GPUS" >&2
    echo "0"
    exit 1
fi

if [ -z "$ALLOCATED_GPUS" ]; then
    echo "⚠️  无可用GPU" >&2
    echo "0"
    exit 1
fi

# 输出分配的GPU列表
echo "$ALLOCATED_GPUS"

# 如果脚本被source（而非执行），设置环境变量
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    # 脚本被source，设置CUDA_VISIBLE_DEVICES
    export CUDA_VISIBLE_DEVICES="$ALLOCATED_GPUS"
    echo "✅ GPU已分配: CUDA_VISIBLE_DEVICES=$ALLOCATED_GPUS" >&2
fi
