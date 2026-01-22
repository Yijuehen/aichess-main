#!/bin/bash
# 多进程并行数据收集脚本 - 智能GPU检测版本

# 配置区域
MIN_GPU_MEMORY_MB=2000  # 最小需要GPU内存（MB），低于此值不使用
MAX_GPU_UTIL=90         # 最大GPU利用率（%），超过此值不使用
BATCH_SIZE=512

echo "=================================="
echo "多进程并行数据收集（智能GPU检测）"
echo "=================================="
echo "最小GPU内存要求: ${MIN_GPU_MEMORY_MB}MB"
echo "最大GPU利用率: ${MAX_GPU_UTIL}%"
echo "数据存储: Redis"
echo "=================================="

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 检测可用GPU
echo ""
echo "正在检测GPU状态..."

# 获取GPU数量
NUM_GPUS=$(nvidia-smi --query-gpu=count --format=csv,noheader,nounits | head -1)
if [ -z "$NUM_GPUS" ]; then
    echo "错误: 未检测到GPU，请确保安装了nvidia-smi"
    exit 1
fi

echo "检测到 $NUM_GPUS 个GPU"

# 检测每个GPU的状态并筛选可用的GPU
AVAILABLE_GPUS=()
for gpu_id in $(seq 0 $(($NUM_GPUS - 1))); do
    # 获取GPU内存使用情况（MB）
    MEMORY_USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i $gpu_id | head -1)
    MEMORY_TOTAL=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i $gpu_id | head -1)
    MEMORY_FREE=$((MEMORY_TOTAL - MEMORY_USED))

    # 获取GPU利用率
    GPU_UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits -i $gpu_id | head -1)

    # GPU名称
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader -i $gpu_id | head -1)

    echo ""
    echo "GPU $gpu_id: $GPU_NAME"
    echo "  内存: 已用 ${MEMORY_USED}MB / 总计 ${MEMORY_TOTAL}MB = 空闲 ${MEMORY_FREE}MB"
    echo "  利用率: ${GPU_UTIL}%"

    # 判断GPU是否可用
    if [ $MEMORY_FREE -lt $MIN_GPU_MEMORY_MB ]; then
        echo "  ❌ 不可用: 空闲内存不足 (${MEMORY_FREE}MB < ${MIN_GPU_MEMORY_MB}MB)"
    elif [ $GPU_UTIL -gt $MAX_GPU_UTIL ]; then
        echo "  ❌ 不可用: 利用率过高 (${GPU_UTIL}% > ${MAX_GPU_UTIL}%)"
    else
        echo "  ✅ 可用: 空闲内存充足，利用率低"
        AVAILABLE_GPUS+=($gpu_id)
    fi
done

echo ""
echo "=================================="
echo "检测结果总结"
echo "=================================="
echo "可用GPU数量: ${#AVAILABLE_GPUS[@]}"
echo "可用GPU编号: ${AVAILABLE_GPUS[@]}"

if [ ${#AVAILABLE_GPUS[@]} -eq 0 ]; then
    echo ""
    echo "❌ 没有可用的GPU！"
    echo "建议:"
    echo "  1. 降低 MIN_GPU_MEMORY_MB 要求（当前: ${MIN_GPU_MEMORY_MB}MB）"
    echo "  2. 关闭其他使用GPU的程序"
    echo "  3. 等待GPU释放"
    exit 1
fi

# 设置环境变量
export DISTIBUTED_TRAINING=false
export BATCH_SIZE=$BATCH_SIZE

echo ""
echo "启动 ${#AVAILABLE_GPUS[@]} 个数据收集进程..."
echo "=================================="

# 启动collect进程
PIDS=()
PROCESS_COUNT=0
for gpu_id in "${AVAILABLE_GPUS[@]}"; do
    echo "启动进程 $PROCESS_COUNT 使用 GPU $gpu_id"

    # 使用CUDA_VISIBLE_DEVICES绑定GPU
    CUDA_VISIBLE_DEVICES=$gpu_id python $SCRIPT_DIR/collect.py > collect_${gpu_id}.log 2>&1 &

    # 保存进程ID
    PID=$!
    PIDS+=($PID)
    PROCESS_COUNT=$((PROCESS_COUNT + 1))

    # 稍微延迟，避免同时启动导致资源竞争
    sleep 1
done

echo ""
echo "=================================="
echo "所有进程已启动！"
echo "=================================="
echo "进程数量: $PROCESS_COUNT"
echo "进程ID: ${PIDS[@]}"
echo "GPU编号: ${AVAILABLE_GPUS[@]}"
echo ""
echo "日志文件:"
for gpu_id in "${AVAILABLE_GPUS[@]}"; do
    echo "  - collect_${gpu_id}.log"
done
echo ""
echo "监控命令："
echo "  查看GPU: watch -n 1 nvidia-smi"
echo "  查看Redis: redis-cli LLEN train_data_buffer"
echo "  查看日志: tail -f collect_*.log"
echo ""
echo "停止所有进程: kill ${PIDS[@]}"
echo "或按 Ctrl+C"
echo "=================================="

# 等待所有进程完成
wait ${PIDS[@]}

echo ""
echo "=================================="
echo "所有进程已完成！"
echo "=================================="

# 清理日志文件（可选）
# rm -f collect_*.log
