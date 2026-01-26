"""
阶段4测试脚本 - 自适应优化

测试内容:
1. 阈值管理器基本功能
2. 历史数据收集和存储
3. 负载模式分析
4. 自适应阈值调整
5. 峰值预测
"""
import time
import os
import redis
import logging
from gpu_balance.threshold_manager import ThresholdManager
from gpu_balance.history import LoadHistory
from gpu_balance.task_scheduler import TaskScheduler
from gpu_balance.gpu_monitor import GPUMonitor
from gpu_balance.config import get_config


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)
logger = logging.getLogger('test_adaptive')


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


def test_threshold_manager(manager):
    """测试2: 阈值管理器"""
    print("\n" + "=" * 60)
    print("测试2: 阈值管理器")
    print("=" * 60)

    # 获取当前阈值
    thresholds = manager.get_current_thresholds()
    print(f"\n当前阈值:")
    print(f"  最小内存: {thresholds.min_memory_mb}MB")
    print(f"  最大利用率: {thresholds.max_utilization}%")
    print(f"  过载阈值: {thresholds.util_high_threshold}%")
    print(f"  空闲阈值: {thresholds.util_low_threshold}%")
    print(f"  自适应: {thresholds.adaptive}")
    print(f"  原因: {thresholds.reason}")

    # 启用自适应阈值
    print("\n启用自适应阈值...")
    success = manager.enable_adaptive(enabled=True)
    if success:
        print("✅ 自适应阈值已启用")
    else:
        print("❌ 启用失败")

    # 获取自适应阈值
    adaptive = manager.get_adaptive_thresholds()
    print(f"\n自适应阈值:")
    print(f"  最小内存: {adaptive.min_memory_mb}MB")
    print(f"  过载阈值: {adaptive.util_high_threshold:.1f}%")
    print(f"  空闲阈值: {adaptive.util_low_threshold:.1f}%")
    print(f"  原因: {adaptive.reason}")

    return True


def test_data_collection(manager, history):
    """测试3: 数据收集"""
    print("\n" + "=" * 60)
    print("测试3: 数据收集")
    print("=" * 60)

    # 获取当前GPU指标
    monitor = GPUMonitor(redis_client=manager.redis_client, config=manager.config)
    metrics_dict = monitor.monitor_once()

    if not metrics_dict:
        print("⚠️  无法获取GPU指标")
        return False

    print(f"收集了 {len(metrics_dict)} 个GPU的指标")

    # 收集到阈值管理器
    success = manager.collect_metrics(metrics_dict)
    if success:
        print("✅ 指标已收集到阈值管理器")
    else:
        print("❌ 收集失败")

    # 收集到历史管理器
    collected = 0
    for gpu_id, metrics in metrics_dict.items():
        data_point = {
            'utilization': str(metrics.utilization),
            'memory_used_mb': str(metrics.memory_used_mb),
            'memory_total_mb': str(metrics.memory_total_mb),
            'memory_free_mb': str(metrics.memory_free_mb),
            'temperature': str(metrics.temperature),
            'num_processes': str(metrics.num_processes)
        }
        if history.add_data_point(gpu_id, data_point):
            collected += 1

    print(f"✅ 收集了 {collected} 个数据点到历史管理器")

    return True


def test_pattern_analysis(manager):
    """测试4: 模式分析"""
    print("\n" + "=" * 60)
    print("测试4: 负载模式分析")
    print("=" * 60)

    from .utils import get_gpu_count
    gpu_count = get_gpu_count()

    for gpu_id in range(min(gpu_count, 2)):  # 测试前2个GPU
        print(f"\nGPU {gpu_id} 的负载模式:")

        patterns = manager.analyze_patterns(gpu_id, days=7)
        if patterns:
            print(f"  检测到 {len(patterns)} 个时段模式")

            # 显示部分时段
            for hour in sorted(patterns.keys())[:5]:
                pattern = patterns[hour]
                print(f"    {hour:02d}:00 - 平均: {pattern.avg_utilization:.1f}%, "
                      f"峰值: {pattern.peak_utilization:.1f}%, "
                      f"样本: {pattern.sample_count}")
        else:
            print(f"  ⚠️  暂无足够的模式数据")

    return True


def test_peak_prediction(manager):
    """测试5: 峰值预测"""
    print("\n" + "=" * 60)
    print("测试5: 峰值预测")
    print("=" * 60)

    from .utils import get_gpu_count
    gpu_count = get_gpu_count()

    for gpu_id in range(min(gpu_count, 2)):  # 测试前2个GPU
        print(f"\nGPU {gpu_id} 的峰值时段预测:")

        peaks = manager.predict_peak_hours(gpu_id, days=7)
        if peaks:
            print("  负载最高的5个时段:")
            for hour, util in peaks[:5]:
                print(f"    {hour:02d}:00 - {util:.1f}%")
        else:
            print("  ⚠️  暂无预测数据")

    return True


def test_history_stats(history):
    """测试6: 历史数据统计"""
    print("\n" + "=" * 60)
    print("测试6: 历史数据统计")
    print("=" * 60)

    from .utils import get_gpu_count
    gpu_count = get_gpu_count()

    for gpu_id in range(min(gpu_count, 2)):  # 测试前2个GPU
        print(f"\nGPU {gpu_id}:")

        # 每日摘要
        summaries = history.get_daily_summary(gpu_id, days=7)
        if summaries:
            print(f"  最近 {len(summaries)} 天的摘要:")
            for summary in reversed(summaries[:3]):  # 显示最近3天
                print(f"    {summary['date']}: "
                      f"平均负载 {summary['avg_utilization']:.1f}%, "
                      f"峰值 {summary['max_utilization']:.1f}%")
        else:
            print("  ⚠️  暂无历史数据")

        # 峰值时段
        peaks = history.get_peak_hours(gpu_id, days=7, top_n=3)
        if peaks:
            print(f"  峰值时段:")
            for hour, util in peaks:
                print(f"    {hour}: {util:.1f}%")

    return True


def test_scheduler_integration(scheduler):
    """测试7: 调度器集成"""
    print("\n" + "=" * 60)
    print("测试7: 调度器自适应集成")
    print("=" * 60)

    # 测试GPU分配是否使用自适应阈值
    print("\n测试GPU分配（应使用自适应阈值）:")
    gpu_id = scheduler.allocate_gpu('collect')

    if gpu_id is not None:
        print(f"✅ 分配GPU: {gpu_id}")

        # 检查使用的阈值
        thresholds = scheduler.threshold_manager.get_adaptive_thresholds()
        print(f"\n使用的自适应阈值:")
        print(f"  最小内存: {thresholds.min_memory_mb}MB")
        print(f"  过载阈值: {thresholds.util_high_threshold:.1f}%")
        print(f"  空闲阈值: {thresholds.util_low_threshold:.1f}%")
        print(f"  调整原因: {thresholds.reason}")
    else:
        print("⚠️  无可用GPU")

    return True


def test_status_summary(manager):
    """测试8: 状态摘要"""
    print("\n" + "=" * 60)
    print("测试8: 状态摘要")
    print("=" * 60)

    summary = manager.get_status_summary()

    if summary:
        print("\n阈值管理器状态:")

        current = summary.get('current_thresholds', {})
        if current:
            print("  当前阈值:")
            print(f"    最小内存: {current.get('min_memory_mb', 'N/A')}MB")
            print(f"    过载阈值: {current.get('util_high_threshold', 'N/A')}%")
            print(f"    空闲阈值: {current.get('util_low_threshold', 'N/A')}%")
            print(f"    自适应: {current.get('adaptive', False)}")
            print(f"    调整原因: {current.get('reason', 'N/A')}")

        history_stats = summary.get('history_stats', {})
        if history_stats:
            print("\n  历史数据:")
            print(f"    总样本数: {history_stats.get('total_samples', 0)}")
            print(f"    追踪GPU数: {history_stats.get('gpus_tracked', 0)}")
            print(f"    保留天数: {history_stats.get('retention_days', 0)}")

        prediction = summary.get('prediction')
        if prediction:
            print(f"\n  负载预测:")
            print(f"    峰值时段: {prediction['peak_hour']:02d}:00")
            print(f"    预期利用率: {prediction['peak_utilization']:.1f}%")

        print(f"\n  当前时间: {summary.get('current_hour', 'N/A')}点")

    return True


def main():
    """主测试函数"""
    print("=" * 60)
    print("阶段4测试: 自适应优化")
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

    # 初始化组件
    config = get_config()
    manager = ThresholdManager(redis_client=redis_client, config=config)
    history = LoadHistory(redis_client=redis_client, config=config)
    scheduler = TaskScheduler(redis_client=redis_client, config=config)

    # 运行所有测试
    tests = [
        ("阈值管理器", lambda: test_threshold_manager(manager)),
        ("数据收集", lambda: test_data_collection(manager, history)),
        ("负载模式分析", lambda: test_pattern_analysis(manager)),
        ("峰值预测", lambda: test_peak_prediction(manager)),
        ("历史数据统计", lambda: test_history_stats(history)),
        ("调度器集成", lambda: test_scheduler_integration(scheduler)),
        ("状态摘要", lambda: test_status_summary(manager)),
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
    print("  启用自适应阈值: python -c \"from gpu_balance.threshold_manager import ThresholdManager; tm = ThresholdManager(); tm.enable_adaptive(True)\"")
    print("  查看当前阈值: python -c \"from gpu_balance.threshold_manager import ThresholdManager; tm = ThresholdManager(); print(tm.get_current_thresholds())\"")
    print("  查看历史统计: python -c \"from gpu_balance.history import LoadHistory; lh = LoadHistory(); print(lh.get_daily_summary(0, days=7))\"")
    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
