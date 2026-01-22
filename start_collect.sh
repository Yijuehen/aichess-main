#!/bin/bash
# 快速启动Collect数据收集

echo "========================================"
echo "🚀 启动Collect数据收集"
echo "========================================"
echo ""

# 检查是否已在运行
if ps aux | grep -v grep | grep "collect.py" > /dev/null; then
    echo "⚠️  Collect已在运行！"
    echo ""
    ps aux | grep -v grep | grep "collect.py"
    echo ""
    echo "如需重启，请先运行: ./stop_collect.sh"
    exit 1
fi

# 检查Redis是否运行
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis未运行！"
    echo "请先启动Redis: sudo systemctl start redis"
    exit 1
fi

echo "✅ Redis运行正常"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 启动collect
echo "启动collect..."
cd "$SCRIPT_DIR"
nohup bash run_parallel_collect.sh > nohup_collect.log 2>&1 &
echo $! > collect.pid

echo ""
echo "✅ Collect已启动！"
echo ""
echo "进程ID: $(cat collect.pid)"
echo "日志文件: nohup_collect.log"
echo ""
echo "常用命令:"
echo "  查看日志: tail -f nohup_collect.log"
echo "  查看进度: redis-cli GET iters"
echo "  监控状态: ./monitor.sh"
echo "  停止程序: ./stop_collect.sh"
echo ""
echo "========================================"
