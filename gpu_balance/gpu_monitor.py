"""
GPU监控模块

实时监控GPU状态并发布指标到Redis
"""
import time
import threading
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

import redis

from .config import get_config
from .utils import (
    get_redis_client,
    get_gpu_count,
    get_gpu_memory,
    get_gpu_utilization,
    get_gpu_temperature,
    get_gpu_name,
    get_processes_on_gpu,
    publish_gpu_metrics,
    format_timestamp
)


logger = logging.getLogger('gpu_balance')


@dataclass
class GPUMetrics:
    """GPU指标数据类"""
    gpu_id: int
    name: str
    utilization: float  # 0-100
    memory_used_mb: int
    memory_total_mb: int
    memory_free_mb: int
    temperature: int = 0
    power_usage: int = 0
    num_processes: int = 0
    timestamp: float = 0.0

    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)


class GPUMonitor:
    """GPU监控器类"""

    def __init__(self, redis_client: Optional[redis.Redis] = None,
                 config=None):
        """
        初始化GPU监控器

        Args:
            redis_client: Redis客户端（可选）
            config: 配置对象（可选）
        """
        self.config = config or get_config()
        self.redis_client = redis_client or get_redis_client(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_db
        )
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.gpu_count = 0

    def collect_gpu_metrics(self, gpu_id: int) -> Optional[GPUMetrics]:
        """
        收集单个GPU的指标

        Args:
            gpu_id: GPU ID

        Returns:
            GPU指标对象
        """
        try:
            # 获取内存信息
            memory = get_gpu_memory(gpu_id)

            # 获取利用率
            utilization = get_gpu_utilization(gpu_id)

            # 获取GPU名称
            name = get_gpu_name(gpu_id)

            # 可选：获取温度
            temperature = 0
            if self.config.enable_temperature:
                temperature = get_gpu_temperature(gpu_id)

            # 获取进程信息
            processes = get_processes_on_gpu(gpu_id)
            num_processes = len(processes)

            metrics = GPUMetrics(
                gpu_id=gpu_id,
                name=name,
                utilization=utilization,
                memory_used_mb=memory['used'],
                memory_total_mb=memory['total'],
                memory_free_mb=memory['free'],
                temperature=temperature,
                num_processes=num_processes,
                timestamp=time.time()
            )

            return metrics
        except Exception as e:
            logger.error(f"收集GPU {gpu_id}指标失败: {e}")
            return None

    def collect_all_gpus(self) -> Dict[int, GPUMetrics]:
        """
        收集所有GPU的指标

        Returns:
            GPU ID到指标的映射
        """
        metrics_dict = {}

        # 检测GPU数量
        self.gpu_count = get_gpu_count()
        if self.gpu_count == 0:
            logger.warning("未检测到GPU")
            return metrics_dict

        # 收集每个GPU的指标
        for gpu_id in range(self.gpu_count):
            metrics = self.collect_gpu_metrics(gpu_id)
            if metrics:
                metrics_dict[gpu_id] = metrics

        return metrics_dict

    def publish_metrics(self, metrics_dict: Dict[int, GPUMetrics]) -> bool:
        """
        发布所有GPU指标到Redis

        Args:
            metrics_dict: GPU指标字典

        Returns:
            是否全部成功
        """
        all_success = True

        for gpu_id, metrics in metrics_dict.items():
            success = publish_gpu_metrics(
                self.redis_client,
                gpu_id,
                metrics.to_dict(),
                ttl=self.config.metrics_ttl
            )
            if not success:
                all_success = False

        return all_success

    def update_available_gpus(self, metrics_dict: Dict[int, GPUMetrics]) -> List[int]:
        """
        更新可用GPU列表

        Args:
            metrics_dict: GPU指标字典

        Returns:
            可用GPU ID列表
        """
        available_gpus = []
        min_memory = self.config.thresholds['min_memory_mb']
        max_util = self.config.thresholds['max_utilization']

        for gpu_id, metrics in metrics_dict.items():
            # 检查是否可用
            if metrics.memory_free_mb >= min_memory and metrics.utilization <= max_util:
                available_gpus.append(gpu_id)

        # 发布到Redis
        try:
            key = "gpu:available"
            if available_gpus:
                self.redis_client.delete(key)
                self.redis_client.sadd(key, *available_gpus)
                self.redis_client.expire(key, 15)  # 15秒过期
            else:
                self.redis_client.delete(key)

            logger.debug(f"可用GPU: {available_gpus}")
        except Exception as e:
            logger.error(f"更新可用GPU列表失败: {e}")

        return available_gpus

    def monitor_once(self) -> Dict[int, GPUMetrics]:
        """
        执行一次监控（收集+发布）

        Returns:
            GPU指标字典
        """
        logger.debug("执行GPU监控...")

        # 收集所有GPU指标
        metrics_dict = self.collect_all_gpus()

        if not metrics_dict:
            logger.warning("未收集到任何GPU指标")
            return metrics_dict

        # 发布到Redis
        self.publish_metrics(metrics_dict)

        # 更新可用GPU列表
        self.update_available_gpus(metrics_dict)

        # 记录汇总信息
        self._log_summary(metrics_dict)

        return metrics_dict

    def _log_summary(self, metrics_dict: Dict[int, GPUMetrics]):
        """
        记录监控汇总信息

        Args:
            metrics_dict: GPU指标字典
        """
        if not metrics_dict:
            return

        avg_util = sum(m.utilization for m in metrics_dict.values()) / len(metrics_dict)
        total_free = sum(m.memory_free_mb for m in metrics_dict.values())
        total_processes = sum(m.num_processes for m in metrics_dict.values())

        logger.info(
            f"GPU监控: {len(metrics_dict)}个GPU, "
            f"平均利用率: {avg_util:.1f}%, "
            f"总空闲内存: {total_free_mb}MB, "
            f"总进程数: {total_processes}"
        )

        for gpu_id, metrics in metrics_dict.items():
            logger.debug(
                f"  GPU {gpu_id}: {metrics.name} - "
                f"{metrics.utilization}%, "
                f"{metrics.memory_used_mb}MB/{metrics.memory_total_mb}MB, "
                f"{metrics.num_processes}进程"
            )

    def start(self):
        """启动监控守护进程"""
        if self.running:
            logger.warning("监控器已在运行")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"GPU监控已启动 (轮询间隔: {self.config.monitor_interval}秒)")

    def stop(self):
        """停止监控守护进程"""
        if not self.running:
            logger.warning("监控器未运行")
            return

        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("GPU监控已停止")

    def _monitor_loop(self):
        """监控循环（在后台线程中运行）"""
        while self.running:
            try:
                self.monitor_once()
                time.sleep(self.config.monitor_interval)
            except Exception as e:
                logger.error(f"监控循环错误: {e}", exc_info=True)
                time.sleep(5)  # 错误后等待5秒再重试


def main():
    """主函数 - 用于测试"""
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(levelname)s] - %(message)s'
    )

    # 创建监控器
    monitor = GPUMonitor()

    print("=" * 60)
    print("GPU监控测试")
    print("=" * 60)

    # 单次监控测试
    print("\n执行一次监控...")
    metrics_dict = monitor.monitor_once()

    if metrics_dict:
        print("\nGPU状态:")
        print("-" * 60)
        for gpu_id, metrics in metrics_dict.items():
            print(f"\nGPU {gpu_id}: {metrics.name}")
            print(f"  利用率: {metrics.utilization}%")
            print(f"  内存: {metrics.memory_used_mb}MB / {metrics.memory_total_mb}MB = {metrics.memory_free_mb}MB空闲")
            if metrics.temperature > 0:
                print(f"  温度: {metrics.temperature}°C")
            print(f"  进程数: {metrics.num_processes}")

        print("\n" + "-" * 60)
        print(f"可用GPU: {[gpu_id for gpu_id in metrics_dict.keys() if metrics_dict[gpu_id].memory_free_mb >= 2000 and metrics_dict[gpu_id].utilization <= 90]}")
        print("-" * 60)

    # 如果命令行参数包含 --daemon，启动守护进程
    if len(sys.argv) > 1 and sys.argv[1] == '--daemon':
        print("\n启动守护进程模式...")
        print("按Ctrl+C停止")

        try:
            monitor.start()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n接收到停止信号")
            monitor.stop()
    else:
        print("\n提示: 使用 --daemon 参数启动持续监控")


if __name__ == '__main__':
    main()
