#!/bin/bash
# 监控Collect运行状态

# 清屏函数
clear_screen() {
    clear
}

# 主监控循环
while true; do
    clear_screen
    echo "========================================"
    echo "📊 Collect监控 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
    echo ""

    # 1. 检查进程
    echo "🖥️  进程状态:"
    if ps aux | grep -v grep | grep "collect.py" > /dev/null; then
        echo "   ✅ 运行中"
        ps aux | grep -v grep | grep "collect.py" | awk '{printf "   PID: %s, CPU: %s%%, MEM: %s%%, 运行时间: %s\n", $2, $3, $4, $10}'
    else
        echo "   ❌ 未运行"
    fi

    echo ""

    # 2. 检查Redis数据
    echo "📈 数据进度:"
    iters=$(redis-cli GET iters 2>/dev/null || echo "0")
    samples=$(redis-cli LLEN train_data_buffer 2>/dev/null || echo "0")
    echo "   游戏局数: $iters"
    echo "   训练样本: $samples"

    # 3. 进度条（假设目标5000局）
    if [ "$iters" -gt 0 ]; then
        progress=$((iters * 100 / 5000))
        echo "   进度: ${progress}% (目标: 5000局)"
        echo -n "   "
        for i in $(seq 1 $((progress / 2))); do echo -n "█"; done
        echo ""
    fi

    echo ""

    # 4. GPU状态
    echo "🎮 GPU状态:"
    nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | head -4 | awk 'BEGIN {print ""} {printf "   GPU "$1": "$2" - 利用率 "$3"%, 显存 "$4"M/"$5"M\n"}'
    if [ $? -ne 0 ]; then
        echo "   (无法获取GPU信息)"
    fi

    echo ""

    # 5. 最新日志
    echo "📝 最新日志（最后5行）:"
    if [ -f nohup_collect.log ]; then
        tail -5 nohup_collect.log 2>/dev/null | grep -E "✅|🎮|Game completed|局完成" | tail -3
        if [ ${PIPESTATUS[0]} -ne 0 ]; then
            tail -3 nohup_collect.log 2>/dev/null
        fi
    else
        echo "   日志文件不存在"
    fi

    echo ""
    echo "========================================"
    echo "按 Ctrl+C 退出监控（不影响collect运行）"
    echo "========================================"

    sleep 5
done
