#!/bin/bash
# 启动负载均衡守护进程

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================"
echo "启动负载均衡守护进程"
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

# 检查GPU监控是否运行
if [ ! -f "gpu_monitor.pid" ]; then
    echo "⚠️  GPU监控未运行！"
    echo ""
    echo "建议先启动GPU监控:"
    echo "  ./start_gpu_monitor.sh"
    echo ""
    read -p "是否继续启动负载均衡? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 检查是否已有均衡守护进程在运行
if [ -f "balance_daemon.pid" ]; then
    PID=$(cat balance_daemon.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  负载均衡守护进程已在运行 (PID: $PID)"
        echo "如需重启，请先运行: ./stop_balance_daemon.sh"
        exit 1
    else
        echo "⚠️  清理过期的PID文件"
        rm -f balance_daemon.pid
    fi
fi

# 读取配置
BALANCE_INTERVAL=${BALANCE_INTERVAL:-60}  # 默认60秒
BALANCE_STRATEGY=${BALANCE_STRATEGY:-no_migration}  # 默认不迁移进程

echo "配置参数:"
echo "  检查间隔: ${BALANCE_INTERVAL}秒"
echo "  平衡策略: ${BALANCE_STRATEGY}"
echo ""

# 启动负载均衡守护进程
echo "启动负载均衡守护进程..."
nohup python -u gpu_balance/balance_daemon.py \
    --daemon \
    --interval $BALANCE_INTERVAL \
    --strategy $BALANCE_STRATEGY \
    > balance_daemon.log 2>&1 &

DAEMON_PID=$!
echo $DAEMON_PID > balance_daemon.pid

echo "✅ 负载均衡守护进程已启动"
echo ""
echo "进程信息:"
echo "  PID: $DAEMON_PID"
echo "  日志: $SCRIPT_DIR/balance_daemon.log"
echo "  PID文件: $SCRIPT_DIR/balance_daemon.pid"
echo ""
echo "查看日志:"
echo "  tail -f balance_daemon.log"
echo ""
echo "查看状态:"
echo "  python -c \"from gpu_balance.balance_daemon import BalanceDaemon; import redis; r = redis.Redis(host='localhost', port=6379, db=0); print(r.hgetall('balance:daemon:status'))\""
echo ""
echo "停止守护进程:"
echo "  ./stop_balance_daemon.sh"
echo ""
echo "执行单次平衡检查:"
echo "  python gpu_balance/balance_daemon.py --once"
echo ""
echo "========================================"
