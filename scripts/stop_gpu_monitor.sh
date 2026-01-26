#!/bin/bash
# 停止GPU监控守护进程

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================"
echo "停止GPU监控守护进程"
echo "========================================"

# 检查PID文件
if [ ! -f "gpu_monitor.pid" ]; then
    echo "⚠️  GPU监控未运行（无PID文件）"
    exit 0
fi

PID=$(cat gpu_monitor.pid)

# 检查进程是否存在
if ! ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  进程不存在 (PID: $PID)"
    rm -f gpu_monitor.pid
    exit 0
fi

# 停止进程
echo "停止进程 (PID: $PID)..."
kill $PID 2>/dev/null

# 等待进程结束
for i in {1..10}; do
    if ! ps -p $PID > /dev/null 2>&1; then
        echo "✅ 进程已停止"
        break
    fi
    sleep 1
done

# 如果进程仍未停止，强制杀死
if ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  进程未响应，强制终止..."
    kill -9 $PID 2>/dev/null
    sleep 1
    if ! ps -p $PID > /dev/null 2>&1; then
        echo "✅ 进程已强制停止"
    else
        echo "❌ 无法停止进程 (PID: $PID)"
        exit 1
    fi
fi

# 清理PID文件
rm -f gpu_monitor.pid

# 清理Redis中的GPU指标
echo "清理Redis数据..."
redis-cli --scan --pattern "gpu:metrics:*" | while read key; do
    redis-cli DEL "$key" > /dev/null 2>&1
done
redis-cli DEL gpu:available > /dev/null 2>&1

echo "✅ Redis数据已清理"
echo ""
echo "========================================"
