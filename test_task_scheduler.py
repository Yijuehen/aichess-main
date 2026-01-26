"""
阶段2测试脚本 - 智能任务分配

测试内容:
1. 进程注册和追踪
2. 任务分配 (collect/train)
3. 心跳机制
4. GPU评分和推荐
5. 状态汇总
"""
import time
import os
import redis
import logging
from gpu_balance.process_tracker import ProcessTracker
from gpu_balance.task_scheduler import TaskScheduler
from gpu_balance.config import get_config
from gpu_balance.gpu_monitor import GPUMonitor


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)
logger = logging.getLogger('test_task_scheduler')


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


def test_process_registration(tracker):
    """测试2: 进程注册"""
    print("\n" + "=" * 60)
    print("测试2: 进程注册")
    print("=" * 60)

    # 模拟注册collect进程
    pid = os.getpid()
    success = tracker.register_process(
        pid=pid,
        gpu_id=0,
        proc_type='collect',
        priority=5
    )

    if success:
        print(f"✅ 进程注册成功: PID={pid}, GPU=0, 类型=collect")
    else:
        print(f"❌ 进程注册失败")
        return False

    # 验证注册信息
    info = tracker.get_process_info(pid)
    if info:
        print(f"✅ 进程信息获取成功:")
        print(f"   PID: {info.pid}")
        print(f"   GPU: {info.gpu_id}")
        print(f"   类型: {info.proc_type}")
        print(f"   状态: {info.status}")
        print(f"   优先级: {info.priority}")
        return True
    else:
        print("❌ 进程信息获取失败")
        return False


def test_heartbeat(tracker):
    """测试3: 心跳机制"""
    print("\n" + "=" * 60)
    print("测试3: 心跳机制")
    print("=" * 60)

    pid = os.getpid()

    # 发送心跳
    success = tracker.update_heartbeat(
        pid=pid,
        games_completed=10,
        status='running'
    )

    if success:
        print("✅ 心跳更新成功")

        # 获取更新后的进程信息
        info = tracker.get_process_info(pid)
        if info:
            heartbeat_age = info.heartbeat_age
            print(f"   距离上次心跳: {heartbeat_age:.2f}秒")
            print(f"   完成游戏数: {info.games_completed}")
            return True
    else:
        print("❌ 心跳更新失败")
        return False


def test_gpu_allocation(scheduler):
    """测试4: GPU分配"""
    print("\n" + "=" * 60)
    print("测试4: GPU分配")
    print("=" * 60)

    # 测试为单个collect任务分配GPU
    print("\n4.1: 为单个collect任务分配GPU")
    gpu_id = scheduler.allocate_gpu('collect')
    if gpu_id is not None:
        print(f"✅ 分配GPU: {gpu_id}")
    else:
        print("⚠️  无可用GPU")

    # 测试为多个train任务分配GPU
    print("\n4.2: 为3个train任务分配GPU")
    gpu_ids = scheduler.allocate_gpus('train', count=3)
    if gpu_ids:
        print(f"✅ 分配GPU: {gpu_ids}")
    else:
        print("⚠️  无可用GPU")

    # 测试分配所有可用GPU
    print("\n4.3: 分配所有可用GPU")
    all_gpus = scheduler.allocate_gpus('collect', count=-1)
    if all_gpus:
        print(f"✅ 可用GPU: {all_gpus}")
    else:
        print("⚠️  无可用GPU")

    return True


def test_gpu_scoring(scheduler):
    """测试5: GPU评分"""
    print("\n" + "=" * 60)
    print("测试5: GPU评分")
    print("=" * 60)

    # 获取可用GPU列表
    from gpu_balance.utils import get_available_gpus
    config = get_config()
    available = get_available_gpus(
        scheduler.redis_client,
        min_memory_mb=config.gpu_balancing['thresholds']['min_memory_mb'],
        max_utilization=config.gpu_balancing['thresholds']['max_utilization']
    )

    if not available:
        print("⚠️  无可用GPU进行评分")
        return True

    print(f"\n为 {len(available)} 个可用GPU评分:")

    for gpu_id in available:
        score = scheduler.score_gpu(gpu_id, 'collect')
        print(f"\nGPU {gpu_id}:")
        print(f"  总分: {score.score:.1f}/100")
        print(f"  利用率: {score.utilization:.1f}%")
        print(f"  可用内存: {score.memory_free_mb}MB")
        print(f"  进程数: {score.num_processes}")
        print(f"  评分详情:")
        for reason in score.reasons:
            print(f"    - {reason}")

    return True


def test_allocation_recommendation(scheduler):
    """测试6: 分配推荐"""
    print("\n" + "=" * 60)
    print("测试6: 分配推荐")
    print("=" * 60)

    test_cases = [
        (1, 'collect'),
        (4, 'collect'),
        (8, 'collect'),
        (1, 'train'),
        (3, 'train'),
    ]

    for num_tasks, task_type in test_cases:
        print(f"\n{num_tasks}个{task_type}任务:")
        rec = scheduler.recommend_allocation(task_type, num_tasks)
        print(f"  策略: {rec['strategy']}")
        print(f"  GPU: {rec['gpu_ids']}")
        print(f"  原因:")
        for reason in rec['reasons']:
            print(f"    - {reason}")

    return True


def test_status_summary(tracker, scheduler):
    """测试7: 状态汇总"""
    print("\n" + "=" * 60)
    print("测试7: 状态汇总")
    print("=" * 60)

    # 从process tracker获取汇总
    print("\n7.1: 进程追踪器状态汇总")
    summary = tracker.get_status_summary()

    if summary:
        print(f"总进程数: {summary.get('total_processes', 0)}")
        print(f"运行中: {summary.get('running', 0)}")
        print(f"卡住: {summary.get('stuck', 0)}")
        print(f"按GPU分布: {summary.get('by_gpu', {})}")
        print(f"按类型分布: {summary.get('by_type', {})}")

    # 从task scheduler获取汇总
    print("\n7.2: 任务调度器状态汇总")
    status = scheduler.get_allocation_status()

    if status:
        print(f"总进程数: {status.get('total_processes', 0)}")
        print(f"按类型: {status.get('by_type', {})}")
        print(f"按GPU: {status.get('by_gpu', {})}")
        print(f"可用GPU: {status.get('available_gpus', [])}")

    return True


def test_cleanup(tracker):
    """测试8: 清理测试数据"""
    print("\n" + "=" * 60)
    print("测试8: 清理测试数据")
    print("=" * 60)

    pid = os.getpid()
    success = tracker.unregister_process(pid)

    if success:
        print(f"✅ 测试进程已注销: PID={pid}")
    else:
        print(f"⚠️  进程注销失败: PID={pid}")

    return True


def main():
    """主测试函数"""
    print("=" * 60)
    print("阶段2测试: 智能任务分配")
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
    tracker = ProcessTracker(redis_client=redis_client, config=config)
    scheduler = TaskScheduler(redis_client=redis_client, config=config)

    # 先启动GPU监控（如果未运行）
    print("\n" + "=" * 60)
    print("启动GPU监控...")
    print("=" * 60)

    monitor = GPUMonitor(redis_client=redis_client, config=config)
    metrics_dict = monitor.monitor_once()

    if metrics_dict:
        print(f"✅ GPU监控成功，检测到 {len(metrics_dict)} 个GPU")
        for gpu_id, metrics in metrics_dict.items():
            print(f"   GPU {gpu_id}: {metrics.name}")
            print(f"     利用率: {metrics.utilization:.1f}%")
            print(f"     内存: {metrics.memory_used_mb}MB / {metrics.memory_total_mb}MB")
    else:
        print("⚠️  GPU监控失败，部分测试可能无法运行")

    # 运行所有测试
    tests = [
        ("进程注册", lambda: test_process_registration(tracker)),
        ("心跳机制", lambda: test_heartbeat(tracker)),
        ("GPU分配", lambda: test_gpu_allocation(scheduler)),
        ("GPU评分", lambda: test_gpu_scoring(scheduler)),
        ("分配推荐", lambda: test_allocation_recommendation(scheduler)),
        ("状态汇总", lambda: test_status_summary(tracker, scheduler)),
        ("清理测试数据", lambda: test_cleanup(tracker)),
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

    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
