#!/bin/bash
# 停止负载均衡守护进程

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================"
echo "停止负载均衡守护进程"
echo "========================================"

# 检查PID文件
if [ ! -f "balance_daemon.pid" ]; then
    echo "⚠️  负载均衡守护进程未运行（无PID文件）"
    exit 0
fi

PID=$(cat balance_daemon.pid)

# 检查进程是否存在
if ! ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  进程不存在 (PID: $PID)"
    rm -f balance_daemon.pid
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
rm -f balance_daemon.pid

# 清理Redis中的负载均衡标志（可选）
read -p "是否清除负载平衡标志? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "清理Redis数据..."
    redis-cli DEL gpu:paused_new_tasks > /dev/null 2>&1
    redis-cli DEL gpu:preferred_for_new_tasks > /dev/null 2>&1
    redis-cli HSET balance:daemon:status status stopped > /dev/null 2>&1
    echo "✅ Redis数据已清理"
fi

echo ""
echo "========================================"
