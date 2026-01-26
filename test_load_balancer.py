"""
阶段3测试脚本 - 动态负载均衡

测试内容:
1. 负载不均衡检测
2. 重新平衡计划生成
3. 平衡动作执行
4. 守护进程基本功能
"""
import time
import os
import redis
import logging
from gpu_balance.load_balancer import LoadBalancer, BalanceStrategy, RebalanceAction
from gpu_balance.balance_daemon import BalanceDaemon
from gpu_balance.config import get_config
from gpu_balance.process_tracker import ProcessTracker


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)
logger = logging.getLogger('test_load_balancer')


def test_redis_connection():
    """测试1: Redis连接"""
    print("\n" + "=" * 60)
    print("测试1: Redis连接")
    print("=" * 60)

    try:
        config = get_config()
        r = redis.StrictRedis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
            decode_responses=True
        )
        r.ping()
        print("✅ Redis连接成功")
        return r
    except Exception as e:
        print(f"❌ Redis连接失败: {e}")
        return None


def test_gpu_status(balancer):
    """测试2: GPU状态获取"""
    print("\n" + "=" * 60)
    print("测试2: GPU状态获取")
    print("=" * 60)

    # 先启动GPU监控获取指标
    from gpu_balance.gpu_monitor import GPUMonitor
    monitor = GPUMonitor(redis_client=balancer.redis_client, config=balancer.config)
    metrics_dict = monitor.monitor_once()

    if not metrics_dict:
        print("⚠️  无法获取GPU指标")
        return False

    print(f"检测到 {len(metrics_dict)} 个GPU")

    # 获取每个GPU的状态
    for gpu_id in metrics_dict.keys():
        status = balancer.get_gpu_status(gpu_id)
        if status:
            print(f"\nGPU {gpu_id}:")
            print(f"  利用率: {status.metrics.utilization:.1f}%")
            print(f"  内存: {status.metrics.memory_used_mb}MB / {status.metrics.memory_total_mb}MB")
            print(f"  空闲内存: {status.metrics.memory_free_mb}MB")
            print(f"  进程数: {len(status.processes)}")
            print(f"  负载评分: {status.load_score:.1f}/100")
            print(f"  是否过载: {status.is_overloaded}")
            print(f"  是否空闲: {status.is_idle}")
        else:
            print(f"⚠️  GPU {gpu_id} 状态获取失败")

    return True


def test_imbalance_detection(balancer):
    """测试3: 负载不均衡检测"""
    print("\n" + "=" * 60)
    print("测试3: 负载不均衡检测")
    print("=" * 60)

    imbalance_info = balancer.detect_imbalance()

    print(f"是否不均衡: {imbalance_info['is_imbalanced']}")
    print(f"过载GPU: {imbalance_info['overloaded_gpus']}")
    print(f"空闲GPU: {imbalance_info['idle_gpus']}")
    print(f"负载方差: {imbalance_info['load_variance']:.2f}")
    print(f"平均负载: {imbalance_info.get('avg_load', 0):.2f}")

    if imbalance_info['details']:
        print("\nGPU详细信息:")
        for gpu_id, details in imbalance_info['details'].items():
            print(f"\n  GPU {gpu_id}:")
            print(f"    利用率: {details['utilization']:.1f}%")
            print(f"    内存: {details['memory_used_mb']}MB / {details['memory_total_mb']}MB")
            print(f"    进程数: {details['num_processes']}")
            print(f"    负载评分: {details['load_score']:.1f}")
            print(f"    过载: {details['is_overloaded']}")
            print(f"    空闲: {details['is_idle']}")

    return True


def test_rebalance_planning(balancer):
    """测试4: 重新平衡计划生成"""
    print("\n" + "=" * 60)
    print("测试4: 重新平衡计划生成")
    print("=" * 60)

    # 获取不均衡状态
    imbalance_info = balancer.detect_imbalance()

    if not imbalance_info['is_imbalanced']:
        print("当前负载均衡，测试重新平衡计划生成...")

        # 模拟不均衡状态
        print("\n模拟不均衡状态:")
        imbalance_info = {
            'is_imbalanced': True,
            'overloaded_gpus': [0],
            'idle_gpus': [1],
            'load_variance': 50.0,
            'details': {
                0: {'load_score': 90.0, 'utilization': 95.0, 'memory_used_mb': 9000},
                1: {'load_score': 20.0, 'utilization': 30.0, 'memory_used_mb': 1000}
            }
        }

    # 测试两种策略
    strategies = [
        BalanceStrategy.NO_MIGRATION,
        BalanceStrategy.PROCESS_MIGRATION
    ]

    for strategy in strategies:
        print(f"\n策略: {strategy.value}")
        print("-" * 60)

        actions = balancer.create_rebalance_plan(imbalance_info, strategy)

        print(f"生成动作数量: {len(actions)}")

        for i, action in enumerate(actions, 1):
            print(f"\n  动作 {i}:")
            print(f"    类型: {action.action_type}")
            print(f"    源GPU: {action.source_gpu}")
            print(f"    目标GPU: {action.target_gpu}")
            print(f"    进程ID: {action.process_id}")
            print(f"    优先级: {action.priority}")
            print(f"    原因: {action.reason}")

    return True


def test_balance_execution(balancer):
    """测试5: 平衡动作执行"""
    print("\n" + "=" * 60)
    print("测试5: 平衡动作执行")
    print("=" * 60)

    # 创建测试动作
    test_actions = [
        RebalanceAction(
            action_type='pause_new_tasks',
            source_gpu=0,
            target_gpu=None,
            process_id=None,
            reason='测试: 暂停GPU 0上的新任务',
            priority=7
        ),
        RebalanceAction(
            action_type='encourage_new_tasks',
            source_gpu=None,
            target_gpu=1,
            process_id=None,
            reason='测试: 鼓励在GPU 1上启动新任务',
            priority=5
        )
    ]

    executed = 0
    for action in test_actions:
        print(f"\n执行动作: {action.action_type}")
        success = balancer.execute_action(action)
        if success:
            print(f"  ✅ 成功: {action.reason}")
            executed += 1
        else:
            print(f"  ❌ 失败: {action.reason}")

    print(f"\n执行结果: {executed}/{len(test_actions)} 个动作成功")

    # 清理测试标志
    print("\n清理测试标志...")
    balancer.clear_balance_flags()
    print("✅ 测试标志已清理")

    return executed > 0


def test_balance_once(balancer):
    """测试6: 执行一次完整平衡"""
    print("\n" + "=" * 60)
    print("测试6: 执行一次完整平衡")
    print("=" * 60)

    print("\n执行负载平衡...")
    result = balancer.balance_once(strategy=BalanceStrategy.NO_MIGRATION)

    print(f"\n平衡结果:")
    print(f"  是否平衡: {result['balanced']}")
    print(f"  执行动作数: {result.get('actions_taken', 0)}")
    if 'actions_total' in result:
        print(f"  总动作数: {result['actions_total']}")

    # 清理标志
    balancer.clear_balance_flags()

    return result['balanced']


def test_daemon_status():
    """测试7: 守护进程状态"""
    print("\n" + "=" * 60)
    print("测试7: 守护进程状态")
    print("=" * 60)

    try:
        config = get_config()
        r = redis.StrictRedis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
            decode_responses=True
        )

        daemon_status = r.hgetall('balance:daemon:status')

        if daemon_status:
            print("守护进程状态:")
            print(f"  PID: {daemon_status.get('pid', 'N/A')}")
            print(f"  状态: {daemon_status.get('status', 'N/A')}")
            print(f"  策略: {daemon_status.get('strategy', 'N/A')}")
            print(f"  间隔: {daemon_status.get('interval', 'N/A')}秒")

            if 'start_time' in daemon_status:
                import time
                uptime = time.time() - float(daemon_status['start_time'])
                print(f"  运行时间: {uptime:.0f}秒")
        else:
            print("⚠️  守护进程未运行")

        return True

    except Exception as e:
        print(f"❌ 获取守护进程状态失败: {e}")
        return False


def test_balance_history():
    """测试8: 平衡历史记录"""
    print("\n" + "=" * 60)
    print("测试8: 平衡历史记录")
    print("=" * 60)

    try:
        config = get_config()
        r = redis.StrictRedis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
            decode_responses=True
        )

        # 获取最近的平衡历史
        history_keys = r.zrevrange('balance:history:index', 0, 4, withscores=True)

        if not history_keys:
            print("⚠️  暂无平衡历史记录")
            return True

        print(f"最近的 {len(history_keys)} 次平衡记录:\n")

        for key, score in history_keys:
            history = r.hgetall(key)
            if history:
                print(f"时间: {history.get('datetime', 'N/A')}")
                print(f"  执行动作: {history.get('actions_taken', 0)}")
                print(f"  总动作: {history.get('actions_total', 0)}")
                print()

        return True

    except Exception as e:
        print(f"❌ 获取平衡历史失败: {e}")
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("阶段3测试: 动态负载均衡")
    print("=" * 60)

    # 测试Redis连接
    redis_client = test_redis_connection()
    if not redis_client:
        print("\n❌ Redis未运行，无法继续测试")
        print("\n启动方法:")
        print("  sudo systemctl start redis")
        print("  或")
        print("  redis-server --daemonize yes")
        return

    # 初始化
    config = get_config()
    balancer = LoadBalancer(redis_client=redis_client, config=config)

    # 运行所有测试
    tests = [
        ("GPU状态获取", lambda: test_gpu_status(balancer)),
        ("负载不均衡检测", lambda: test_imbalance_detection(balancer)),
        ("重新平衡计划生成", lambda: test_rebalance_planning(balancer)),
        ("平衡动作执行", lambda: test_balance_execution(balancer)),
        ("完整平衡执行", lambda: test_balance_once(balancer)),
        ("守护进程状态", lambda: test_daemon_status()),
        ("平衡历史记录", lambda: test_balance_history()),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            time.sleep(0.5)  # 短暂延迟
        except Exception as e:
            print(f"\n❌ 测试 '{test_name}' 出错: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # 测试结果汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过!")
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")

    print("\n使用说明:")
    print("  启动守护进程: ./start_balance_daemon.sh")
    print("  停止守护进程: ./stop_balance_daemon.sh")
    print("  单次平衡检查: python gpu_balance/balance_daemon.py --once")
    print("  查看日志: tail -f balance_daemon.log")
    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
