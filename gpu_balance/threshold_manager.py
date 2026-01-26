"""
阈值管理模块

基于历史负载数据动态调整GPU分配阈值
检测周期性模式，预测负载峰值，优化阈值设置
"""
import time
import os
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

from .config import get_config
from .utils import get_redis_client
from .gpu_monitor import GPUMonitor


logger = logging.getLogger('gpu_balance')


@dataclass
class LoadPattern:
    """负载模式数据类"""
    hour: int  # 0-23
    day_of_week: int  # 0-6 (Monday=0)
    avg_utilization: float
    avg_memory_used_mb: int
    peak_utilization: float
    sample_count: int
    last_updated: float


@dataclass
class ThresholdConfig:
    """阈值配置数据类"""
    min_memory_mb: int
    max_utilization: float
    util_high_threshold: float  # 过载阈值
    util_low_threshold: float   # 空闲阈值
    adaptive: bool
    last_adjusted: float
    reason: str = ""


class ThresholdManager:
    """
    阈值管理器类

    职责:
    1. 收集历史负载数据
    2. 检测周期性模式
    3. 动态调整阈值
    4. 预测负载峰值
    """

    def __init__(self, redis_client=None, config=None):
        """
        初始化阈值管理器

        Args:
            redis_client: Redis客户端（可选）
            config: 配置对象（可选）
        """
        self.config = config or get_config()
        self.redis_client = redis_client or get_redis_client(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_db,
            decode_responses=True
        )

        self.gpu_monitor = GPUMonitor(
            redis_client=self.redis_client,
            config=self.config
        )

        # 历史数据配置
        self.history_retention_days = 30  # 保留30天历史
        self.pattern_min_samples = 5  # 最少样本数才能形成模式

    def get_current_thresholds(self) -> ThresholdConfig:
        """
        获取当前阈值配置

        Returns:
            阈值配置对象
        """
        try:
            # 从Redis获取当前阈值
            thresholds = self.redis_client.hgetall('thresholds:current')

            if thresholds:
                return ThresholdConfig(
                    min_memory_mb=int(thresholds['min_memory_mb']),
                    max_utilization=float(thresholds['max_utilization']),
                    util_high_threshold=float(thresholds['util_high_threshold']),
                    util_low_threshold=float(thresholds['util_low_threshold']),
                    adaptive=thresholds['adaptive'] == 'True',
                    last_adjusted=float(thresholds.get('last_adjusted', 0)),
                    reason=thresholds.get('reason', '')
                )
            else:
                # 使用默认配置
                return self._get_default_thresholds()

        except Exception as e:
            logger.error(f"获取当前阈值失败: {e}")
            return self._get_default_thresholds()

    def _get_default_thresholds(self) -> ThresholdConfig:
        """
        获取默认阈值配置

        Returns:
            默认阈值配置
        """
        defaults = self.config.gpu_balancing['thresholds']
        return ThresholdConfig(
            min_memory_mb=defaults['min_memory_mb'],
            max_utilization=defaults['max_utilization'],
            util_high_threshold=defaults['util_high_threshold'],
            util_low_threshold=defaults['util_low_threshold'],
            adaptive=defaults.get('adaptive', False),
            last_adjusted=0.0,
            reason="默认配置"
        )

    def collect_metrics(self, metrics_dict: Dict[int, Any]) -> bool:
        """
        收集GPU指标到历史数据库

        Args:
            metrics_dict: GPU指标字典 {gpu_id: GPUMetrics}

        Returns:
            是否成功
        """
        try:
            now = time.time()
            dt = datetime.fromtimestamp(now)
            hour = dt.hour
            day_of_week = dt.weekday()

            for gpu_id, metrics in metrics_dict.items():
                # 存储历史数据点
                key = f"load:history:{gpu_id}"
                timestamp = now

                data_point = {
                    'timestamp': timestamp,
                    'datetime': dt.isoformat(),
                    'hour': hour,
                    'day_of_week': day_of_week,
                    'utilization': metrics.utilization,
                    'memory_used_mb': metrics.memory_used_mb,
                    'memory_total_mb': metrics.memory_total_mb,
                    'memory_free_mb': metrics.memory_free_mb,
                    'temperature': metrics.temperature,
                    'num_processes': metrics.num_processes
                }

                # 使用sorted set存储，按时间排序
                self.redis_client.zadd(key, {f"{timestamp}:{gpu_id}": timestamp})

                # 存储详细数据
                detail_key = f"load:history:{gpu_id}:{int(timestamp)}"
                self.redis_client.hset(detail_key, mapping=data_point)

                # 设置过期时间（30天）
                self.redis_client.expire(detail_key, 30 * 24 * 3600)

                # 保留最多10000个数据点
                self.redis_client.zremrangebyrank(key, 0, -10001)

            return True

        except Exception as e:
            logger.error(f"收集指标失败: {e}")
            return False

    def analyze_patterns(self, gpu_id: int, days: int = 7) -> Dict[int, LoadPattern]:
        """
        分析GPU负载模式（按小时）

        Args:
            gpu_id: GPU ID
            days: 分析最近几天的数据

        Returns:
            {hour: LoadPattern} 字典
        """
        try:
            patterns = {}
            now = time.time()
            start_time = now - (days * 24 * 3600)

            # 获取历史数据
            key = f"load:history:{gpu_id}"
            data_points = self.redis_client.zrangebyscore(
                key,
                start_time,
                now,
                withscores=True
            )

            # 按小时分组统计
            hour_stats = defaultdict(lambda: {
                'utilizations': [],
                'memory_used': [],
                'days': set()
            })

            for member, score in data_points:
                # member格式: "timestamp:gpu_id"
                timestamp = float(member.split(':')[0])
                detail_key = f"load:history:{gpu_id}:{int(timestamp)}"

                details = self.redis_client.hgetall(detail_key)
                if not details:
                    continue

                hour = int(details['hour'])
                day_of_week = int(details['day_of_week'])
                utilization = float(details['utilization'])
                memory_used = int(details['memory_used_mb'])

                hour_stats[hour]['utilizations'].append(utilization)
                hour_stats[hour]['memory_used'].append(memory_used)
                hour_stats[hour]['days'].add(day_of_week)

            # 生成模式
            for hour, stats in hour_stats.items():
                if len(stats['utilizations']) >= self.pattern_min_samples:
                    utilizations = stats['utilizations']
                    memory_used_list = stats['memory_used']

                    patterns[hour] = LoadPattern(
                        hour=hour,
                        day_of_week=0,  # 简化：不区分星期
                        avg_utilization=sum(utilizations) / len(utilizations),
                        avg_memory_used_mb=int(sum(memory_used_list) / len(memory_used_list)),
                        peak_utilization=max(utilizations),
                        sample_count=len(utilizations),
                        last_updated=now
                    )

            return patterns

        except Exception as e:
            logger.error(f"分析模式失败 (GPU {gpu_id}): {e}")
            return {}

    def predict_peak_hours(self, gpu_id: int, days: int = 7) -> List[Tuple[int, float]]:
        """
        预测负载峰值时段

        Args:
            gpu_id: GPU ID
            days: 分析最近几天的数据

        Returns:
            [(hour, avg_utilization)] 列表，按利用率降序排列
        """
        try:
            patterns = self.analyze_patterns(gpu_id, days)

            # 按平均利用率排序
            peaks = [
                (hour, pattern.avg_utilization)
                for hour, pattern in patterns.items()
            ]
            peaks.sort(key=lambda x: x[1], reverse=True)

            return peaks

        except Exception as e:
            logger.error(f"预测峰值时段失败: {e}")
            return []

    def get_adaptive_thresholds(self) -> ThresholdConfig:
        """
        获取自适应阈值配置

        根据当前时段的历史模式动态调整阈值

        Returns:
            优化的阈值配置
        """
        try:
            current_thresholds = self.get_current_thresholds()

            # 如果未启用自适应，直接返回当前阈值
            if not current_thresholds.adaptive:
                return current_thresholds

            now = time.time()
            dt = datetime.fromtimestamp(now)
            current_hour = dt.hour

            # 获取所有GPU的历史数据
            from .utils import get_gpu_count
            gpu_count = get_gpu_count()

            # 收集当前时段的负载数据
            hour_loads = []
            for gpu_id in range(gpu_count):
                patterns = self.analyze_patterns(gpu_id, days=7)

                if current_hour in patterns:
                    pattern = patterns[current_hour]
                    hour_loads.append({
                        'gpu_id': gpu_id,
                        'avg_util': pattern.avg_utilization,
                        'peak_util': pattern.peak_utilization,
                        'avg_memory': pattern.avg_memory_used_mb
                    })

            if not hour_loads:
                # 无历史数据，使用默认阈值
                return current_thresholds

            # 计算统计数据
            avg_utilization = sum(l['avg_util'] for l in hour_loads) / len(hour_loads)
            peak_utilization = max(l['peak_util'] for l in hour_loads)
            avg_memory = sum(l['avg_memory'] for l in hour_loads) / len(hour_loads)

            # 根据时段特性调整阈值
            # 白天（8-20点）：允许更高利用率
            # 夜间（20-8点）：更保守
            is_daytime = 8 <= current_hour <= 20

            if is_daytime:
                # 白天：提高阈值以允许更高利用率
                util_high = min(95.0, avg_utilization + 15.0)
                util_low = max(40.0, avg_utilization - 20.0)
                min_memory = max(1500, int(avg_memory * 0.2))  # 20%内存作为最小要求
                reason = f"白天时段({current_hour}点)，基于历史负载({avg_utilization:.1f}%)调整阈值"
            else:
                # 夜间：降低阈值，更保守
                util_high = min(90.0, avg_utilization + 10.0)
                util_low = max(50.0, avg_utilization - 15.0)
                min_memory = max(2000, int(avg_memory * 0.3))  # 30%内存作为最小要求
                reason = f"夜间时段({current_hour}点)，基于历史负载({avg_utilization:.1f}%)调整阈值"

            # 确保阈值在合理范围内
            util_high = max(70.0, min(95.0, util_high))
            util_low = max(30.0, min(60.0, util_low))
            min_memory = max(1000, min(4000, min_memory))

            new_thresholds = ThresholdConfig(
                min_memory_mb=min_memory,
                max_utilization=95.0,
                util_high_threshold=util_high,
                util_low_threshold=util_low,
                adaptive=True,
                last_adjusted=now,
                reason=reason
            )

            # 保存到Redis
            self._save_thresholds(new_thresholds)

            logger.info(f"自适应阈值调整: {reason}")
            logger.info(
                f"  过载阈值: {util_high:.1f}%, "
                f"空闲阈值: {util_low:.1f}%, "
                f"最小内存: {min_memory}MB"
            )

            return new_thresholds

        except Exception as e:
            logger.error(f"获取自适应阈值失败: {e}")
            return self.get_current_thresholds()

    def _save_thresholds(self, thresholds: ThresholdConfig) -> bool:
        """
        保存阈值配置到Redis

        Args:
            thresholds: 阈值配置

        Returns:
            是否成功
        """
        try:
            data = {
                'min_memory_mb': str(thresholds.min_memory_mb),
                'max_utilization': str(thresholds.max_utilization),
                'util_high_threshold': str(thresholds.util_high_threshold),
                'util_low_threshold': str(thresholds.util_low_threshold),
                'adaptive': str(thresholds.adaptive),
                'last_adjusted': str(thresholds.last_adjusted),
                'reason': thresholds.reason
            }

            self.redis_client.hset('thresholds:current', mapping=data)
            return True

        except Exception as e:
            logger.error(f"保存阈值失败: {e}")
            return False

    def adjust_thresholds(
        self,
        min_memory_mb: Optional[int] = None,
        max_utilization: Optional[float] = None,
        util_high_threshold: Optional[float] = None,
        util_low_threshold: Optional[float] = None,
        reason: str = "手动调整"
    ) -> bool:
        """
        手动调整阈值

        Args:
            min_memory_mb: 最小内存要求
            max_utilization: 最大利用率
            util_high_threshold: 过载阈值
            util_low_threshold: 空闲阈值
            reason: 调整原因

        Returns:
            是否成功
        """
        try:
            current = self.get_current_thresholds()

            new_thresholds = ThresholdConfig(
                min_memory_mb=min_memory_mb if min_memory_mb is not None else current.min_memory_mb,
                max_utilization=max_utilization if max_utilization is not None else current.max_utilization,
                util_high_threshold=util_high_threshold if util_high_threshold is not None else current.util_high_threshold,
                util_low_threshold=util_low_threshold if util_low_threshold is not None else current.util_low_threshold,
                adaptive=current.adaptive,
                last_adjusted=time.time(),
                reason=reason
            )

            return self._save_thresholds(new_thresholds)

        except Exception as e:
            logger.error(f"调整阈值失败: {e}")
            return False

    def get_status_summary(self) -> Dict[str, Any]:
        """
        获取阈值管理器状态摘要

        Returns:
            状态字典
        """
        try:
            current = self.get_current_thresholds()

            # 获取历史数据统计
            from .utils import get_gpu_count
            gpu_count = get_gpu_count()

            total_samples = 0
            for gpu_id in range(gpu_count):
                key = f"load:history:{gpu_id}"
                count = self.redis_client.zcard(key)
                total_samples += count

            # 预测下一个时段的负载
            now = datetime.now()
            next_hour = (now.hour + 1) % 24

            peak_prediction = None
            if gpu_count > 0:
                peaks = self.predict_peak_hours(0, days=7)
                if peaks:
                    peak_hour, peak_util = peaks[0]
                    peak_prediction = {
                        'peak_hour': peak_hour,
                        'peak_utilization': peak_util
                    }

            return {
                'current_thresholds': {
                    'min_memory_mb': current.min_memory_mb,
                    'max_utilization': current.max_utilization,
                    'util_high_threshold': current.util_high_threshold,
                    'util_low_threshold': current.util_low_threshold,
                    'adaptive': current.adaptive,
                    'last_adjusted': current.last_adjusted,
                    'reason': current.reason
                },
                'history_stats': {
                    'total_samples': total_samples,
                    'retention_days': self.history_retention_days,
                    'gpus_tracked': gpu_count
                },
                'prediction': peak_prediction,
                'current_hour': now.hour,
                'current_day': now.weekday()
            }

        except Exception as e:
            logger.error(f"获取状态摘要失败: {e}")
            return {}

    def enable_adaptive(self, enabled: bool = True) -> bool:
        """
        启用/禁用自适应阈值

        Args:
            enabled: 是否启用

        Returns:
            是否成功
        """
        return self.adjust_thresholds(
            reason=f"{'启用' if enabled else '禁用'}自适应阈值"
        )


def main():
    """主函数 - 用于测试"""
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(levelname)s] - %(message)s'
    )

    print("=" * 60)
    print("阈值管理器测试")
    print("=" * 60)

    manager = ThresholdManager()

    # 测试1: 获取当前阈值
    print("\n测试1: 获取当前阈值")
    print("-" * 60)
    thresholds = manager.get_current_thresholds()
    print(f"最小内存: {thresholds.min_memory_mb}MB")
    print(f"最大利用率: {thresholds.max_utilization}%")
    print(f"过载阈值: {thresholds.util_high_threshold}%")
    print(f"空闲阈值: {thresholds.util_low_threshold}%")
    print(f"自适应: {thresholds.adaptive}")
    print(f"原因: {thresholds.reason}")

    # 测试2: 收集当前指标
    print("\n测试2: 收集当前指标")
    print("-" * 60)
    metrics_dict = manager.gpu_monitor.monitor_once()
    if metrics_dict:
        success = manager.collect_metrics(metrics_dict)
        print(f"✅ 指标收集{'成功' if success else '失败'}")
    else:
        print("⚠️  无法获取GPU指标")

    # 测试3: 分析负载模式
    print("\n测试3: 分析负载模式（GPU 0）")
    print("-" * 60)
    patterns = manager.analyze_patterns(0, days=7)
    if patterns:
        print(f"检测到 {len(patterns)} 个时段模式:")
        for hour in sorted(patterns.keys())[:5]:  # 显示前5个
            pattern = patterns[hour]
            print(f"  {hour:02d}:00 - 平均负载: {pattern.avg_utilization:.1f}%, "
                  f"峰值: {pattern.peak_utilization:.1f}%, "
                  f"样本数: {pattern.sample_count}")
    else:
        print("⚠️  暂无足够的模式数据")

    # 测试4: 预测峰值时段
    print("\n测试4: 预测峰值时段（GPU 0）")
    print("-" * 60)
    peaks = manager.predict_peak_hours(0, days=7)
    if peaks:
        print("峰值时段预测（按负载降序）:")
        for hour, util in peaks[:5]:
            print(f"  {hour:02d}:00 - {util:.1f}%")
    else:
        print("⚠️  暂无预测数据")

    # 测试5: 获取自适应阈值
    print("\n测试5: 获取自适应阈值")
    print("-" * 60)
    adaptive = manager.get_adaptive_thresholds()
    print(f"过载阈值: {adaptive.util_high_threshold:.1f}%")
    print(f"空闲阈值: {adaptive.util_low_threshold:.1f}%")
    print(f"最小内存: {adaptive.min_memory_mb}MB")
    print(f"原因: {adaptive.reason}")

    # 测试6: 状态摘要
    print("\n测试6: 状态摘要")
    print("-" * 60)
    summary = manager.get_status_summary()
    print(f"总样本数: {summary.get('history_stats', {}).get('total_samples', 0)}")
    print(f"追踪GPU数: {summary.get('history_stats', {}).get('gpus_tracked', 0)}")
    if summary.get('prediction'):
        pred = summary['prediction']
        print(f"预测峰值: {pred['peak_hour']:02d}:00 - {pred['peak_utilization']:.1f}%")

    print("\n✅ 所有测试完成")


if __name__ == '__main__':
    main()
