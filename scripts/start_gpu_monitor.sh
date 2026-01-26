#!/bin/bash
# 启动GPU监控守护进程

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================"
echo "启动GPU监控守护进程"
echo "========================================"

# 检查Redis是否运行
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis未运行！请先启动Redis服务"
    echo ""
    echo "启动方法:"
    echo "  sudo systemctl start redis"
    echo "  或"
    echo "  redis-server --daemonize yes"
    exit 1
fi

echo "✅ Redis连接正常"

# 检查是否已有监控进程在运行
if [ -f "gpu_monitor.pid" ]; then
    PID=$(cat gpu_monitor.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  GPU监控已在运行 (PID: $PID)"
        echo "如需重启，请先运行: ./stop_gpu_monitor.sh"
        exit 1
    else
        echo "⚠️  清理过期的PID文件"
        rm -f gpu_monitor.pid
    fi
fi

# 检查psutil依赖
if ! python -c "import psutil" 2>/dev/null; then
    echo "⚠️  psutil未安装，正在安装..."
    pip install psutil>=5.9.0
    if [ $? -ne 0 ]; then
        echo "❌ psutil安装失败"
        exit 1
    fi
    echo "✅ psutil安装成功"
fi

# 启动GPU监控守护进程
echo "启动GPU监控..."
nohup python -u gpu_balance/gpu_monitor.py --daemon \
    > gpu_monitor.log 2>&1 &

MONITOR_PID=$!
echo $MONITOR_PID > gpu_monitor.pid

echo "✅ GPU监控已启动"
echo ""
echo "进程信息:"
echo "  PID: $MONITOR_PID"
echo "  日志: $SCRIPT_DIR/gpu_monitor.log"
echo "  PID文件: $SCRIPT_DIR/gpu_monitor.pid"
echo ""
echo "查看日志:"
echo "  tail -f gpu_monitor.log"
echo ""
echo "停止监控:"
echo "  ./stop_gpu_monitor.sh"
echo ""
echo "========================================"
