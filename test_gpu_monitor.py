"""
GPU监控模块测试脚本

验证GPU监控功能的完整性
"""
import sys
import time
import redis
from gpu_balance.config import get_config
from gpu_balance.gpu_monitor import GPUMonitor


def test_redis_connection():
    """测试Redis连接"""
    print("=" * 60)
    print("测试1: Redis连接")
    print("=" * 60)

    try:
        config = get_config()
        client = redis.StrictRedis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db
        )
        client.ping()
        print("✅ Redis连接成功")
        print(f"   地址: {config.redis_host}:{config.redis_port}")
        return True
    except Exception as e:
        print(f"❌ Redis连接失败: {e}")
        print("\n请检查:")
        print("  1. Redis服务是否启动")
        print("  2. 配置是否正确 (config.py)")
        return False


def test_gpu_detection():
    """测试GPU检测"""
    print("\n" + "=" * 60)
    print("测试2: GPU检测")
    print("=" * 60)

    from gpu_balance.utils import get_gpu_count

    gpu_count = get_gpu_count()
    print(f"检测到 {gpu_count} 个GPU")

    if gpu_count == 0:
        print("❌ 未检测到GPU")
        print("\n可能原因:")
        print("  1. NVIDIA驱动未安装")
        print("  2. nvidia-smi不可用")
        print("  3. 没有GPU硬件")
        return False
    else:
        print(f"✅ GPU检测成功")

        # 显示每个GPU的信息
        from gpu_balance.utils import get_gpu_name, get_gpu_memory
        for gpu_id in range(gpu_count):
            name = get_gpu_name(gpu_id)
            memory = get_gpu_memory(gpu_id)
            print(f"\n  GPU {gpu_id}: {name}")
            print(f"    内存: {memory['used']}MB / {memory['total']}MB = {memory['free']}MB 空闲")

        return True


def test_monitor_once():
    """测试单次监控"""
    print("\n" + "=" * 60)
    print("测试3: 单次监控")
    print("=" * 60)

    try:
        config = get_config()
        monitor = GPUMonitor()

        print("执行单次GPU监控...")
        metrics_dict = monitor.monitor_once()

        if not metrics_dict:
            print("❌ 未收集到GPU指标")
            return False

        print(f"✅ 成功收集 {len(metrics_dict)} 个GPU的指标")

        # 显示详细信息
        print("\nGPU状态:")
        for gpu_id, metrics in metrics_dict.items():
            print(f"\n  GPU {gpu_id}: {metrics.name}")
            print(f"    利用率: {metrics.utilization}%")
            print(f"    内存: {metrics.memory_used_mb}MB / {metrics.memory_total_mb}MB")
            print(f"    空闲: {metrics.memory_free_mb}MB")
            if metrics.temperature > 0:
                print(f"    温度: {metrics.temperature}°C")
            print(f"    进程数: {metrics.num_processes}")

        # 验证Redis中的数据
        print("\n验证Redis数据...")
        client = redis.StrictRedis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db
        )

        for gpu_id in metrics_dict.keys():
            key = f"gpu:metrics:{gpu_id}"
            data = client.hgetall(key)
            if data:
                print(f"  ✅ GPU {gpu_id} 指标已发布到Redis")
            else:
                print(f"  ❌ GPU {gpu_id} 指标未发布到Redis")
                return False

        # 检查可用GPU列表
        available_key = "gpu:available"
        available = client.smembers(available_key)
        print(f"\n✅ 可用GPU列表: {sorted([int(x) for x in available])}")

        return True

    except Exception as e:
        print(f"❌ 单次监控失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_continuous_monitoring():
    """测试持续监控（短时间）"""
    print("\n" + "=" * 60)
    print("测试4: 持续监控 (5秒)")
    print("=" * 60)

    try:
        monitor = GPUMonitor()
        monitor.start()

        print("监控已启动，运行5秒...")
        for i in range(5):
            time.sleep(1)
            print(f"  {i+1}秒...")

        monitor.stop()
        print("✅ 持续监控测试通过")
        return True

    except Exception as e:
        print(f"❌ 持续监控失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_available_gpu_filtering():
    """测试可用GPU过滤"""
    print("\n" + "=" * 60)
    print("测试5: 可用GPU过滤")
    print("=" * 60)

    try:
        from gpu_balance.utils import get_available_gpus
        config = get_config()
        client = redis.StrictRedis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db
        )

        # 先执行一次监控以收集数据
        monitor = GPUMonitor()
        monitor.monitor_once()

        # 测试不同阈值
        thresholds = [
            (2000, 90, "默认阈值"),
            (4000, 80, "严格阈值"),
            (1000, 95, "宽松阈值")
        ]

        for min_mem, max_util, desc in thresholds:
            available = get_available_gpus(
                client,
                min_memory_mb=min_mem,
                max_utilization=max_util
            )
            print(f"\n{desc} (内存>={min_mem}MB, 利用率<={max_util}%):")
            print(f"  可用GPU: {available}")

        print("\n✅ 可用GPU过滤测试通过")
        return True

    except Exception as e:
        print(f"❌ 可用GPU过滤失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n🧪 GPU监控功能测试")
    print("=" * 60)
    print("")

    results = []

    # 运行测试
    results.append(("Redis连接", test_redis_connection()))
    results.append(("GPU检测", test_gpu_detection()))
    results.append(("单次监控", test_monitor_once()))
    results.append(("持续监控", test_continuous_monitoring()))
    results.append(("可用GPU过滤", test_available_gpu_filtering()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status} - {name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n🎉 所有测试通过!")
        print("\n下一步:")
        print("  1. 启动GPU监控守护进程:")
        print("     ./start_gpu_monitor.sh")
        print("  2. 查看监控日志:")
        print("     tail -f gpu_monitor.log")
        print("  3. 检查Redis中的GPU指标:")
        print("     redis-cli HGETALL gpu:metrics:0")
        return 0
    else:
        print("\n⚠️  部分测试失败")
        print("\n建议:")
        print("  1. 确保Redis服务运行中")
        print("  2. 确保GPU可用且nvidia-smi工作正常")
        print("  3. 检查config.py配置")
        return 1


if __name__ == '__main__':
    sys.exit(main())
