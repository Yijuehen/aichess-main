#!/bin/bash
# 停止Collect数据收集

echo "========================================"
echo "🛑 停止Collect"
echo "========================================"
echo ""

# 检查PID文件
if [ -f collect.pid ]; then
    pid=$(cat collect.pid)
    echo "停止进程: $pid"
    kill $pid 2>/dev/null
    rm collect.pid
    echo "✅ 已停止"
else
    echo "未找到PID文件，尝试查找进程..."
fi

# 强制停止所有collect进程（防止有遗漏）
if ps aux | grep -v grep | grep "collect.py" > /dev/null; then
    echo ""
    echo "发现残留进程，正在清理..."
    pkill -9 -f "collect.py"
    echo "✅ 已清理所有进程"
fi

echo ""
echo "验证:"
if ps aux | grep -v grep | grep "collect.py" > /dev/null; then
    echo "⚠️  进程仍在运行"
    ps aux | grep -v grep | grep "collect.py"
else
    echo "✅ 所有进程已停止"
fi

echo ""
echo "数据状态:"
iters=$(redis-cli GET iters 2>/dev/null || echo "0")
samples=$(redis-cli LLEN train_data_buffer 2>/dev/null || echo "0")
echo "  已收集局数: $iters"
echo "  训练样本数: $samples"

echo ""
echo "========================================"
