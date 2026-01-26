"""
历史数据管理模块

管理GPU负载数据的存储、聚合和分析
提供数据查询和统计功能
"""
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

from .config import get_config
from .utils import get_redis_client


logger = logging.getLogger('gpu_balance')


class LoadHistory:
    """
    负载历史类

    职责:
    1. 存储和检索历史负载数据
    2. 数据聚合（按小时/天/周）
    3. 统计分析
    4. 数据清理
    """

    def __init__(self, redis_client=None, config=None):
        """
        初始化历史数据管理器

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

        # 数据保留策略
        self.raw_data_retention_days = 7  # 原始数据保留7天
        self.hourly_data_retention_days = 30  # 小时聚合数据保留30天
        self.daily_data_retention_days = 365  # 日聚合数据保留1年

    def add_data_point(
        self,
        gpu_id: int,
        metrics: Dict[str, Any],
        timestamp: Optional[float] = None
    ) -> bool:
        """
        添加单个数据点

        Args:
            gpu_id: GPU ID
            metrics: 指标字典
            timestamp: 时间戳（可选，默认当前时间）

        Returns:
            是否成功
        """
        try:
            if timestamp is None:
                timestamp = time.time()

            dt = datetime.fromtimestamp(timestamp)
            date_str = dt.strftime('%Y-%m-%d')
            hour_str = dt.strftime('%Y-%m-%d-%H')

            # 存储原始数据
            raw_key = f"load:raw:{gpu_id}:{int(timestamp)}"
            self.redis_client.hset(raw_key, mapping={
                'timestamp': timestamp,
                'datetime': dt.isoformat(),
                'date': date_str,
                'hour': hour_str,
                **metrics
            })
            self.redis_client.expire(raw_key, self.raw_data_retention_days * 24 * 3600)

            # 添加到时间序列索引
            timeline_key = f"load:timeline:{gpu_id}"
            self.redis_client.zadd(timeline_key, {raw_key: timestamp})
            self.redis_client.expire(timeline_key, self.raw_data_retention_days * 24 * 3600)

            return True

        except Exception as e:
            logger.error(f"添加数据点失败: {e}")
            return False

    def get_data_range(
        self,
        gpu_id: int,
        start_time: float,
        end_time: float,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        获取时间范围内的数据

        Args:
            gpu_id: GPU ID
            start_time: 开始时间戳
            end_time: 结束时间戳
            limit: 最大返回数量

        Returns:
            数据点列表
        """
        try:
            timeline_key = f"load:timeline:{gpu_id}"
            raw_keys = self.redis_client.zrangebyscore(
                timeline_key,
                start_time,
                end_time,
                start=0,
                num=limit,
                withscores=True
            )

            data_points = []
            for key, score in raw_keys:
                data = self.redis_client.hgetall(key)
                if data:
                    data_points.append(data)

            return data_points

        except Exception as e:
            logger.error(f"获取数据范围失败: {e}")
            return []

    def aggregate_hourly(self, gpu_id: int, hour_str: str) -> Optional[Dict[str, Any]]:
        """
        按小时聚合数据

        Args:
            gpu_id: GPU ID
            hour_str: 小时字符串（格式: YYYY-MM-DD-HH）

        Returns:
            聚合数据字典
        """
        try:
            # 获取该小时的所有原始数据
            pattern = f"load:raw:{gpu_id}*"
            keys = self.redis_client.keys(pattern)

            utilization_values = []
            memory_used_values = []
            memory_free_values = []
            temperature_values = []

            count = 0
            for key in keys:
                data = self.redis_client.hgetall(key)
                if data.get('hour') == hour_str:
                    utilization_values.append(float(data['utilization']))
                    memory_used_values.append(int(data['memory_used_mb']))
                    memory_free_values.append(int(data['memory_free_mb']))
                    if data.get('temperature'):
                        temperature_values.append(int(data['temperature']))
                    count += 1

            if count == 0:
                return None

            # 计算统计值
            aggregated = {
                'gpu_id': gpu_id,
                'hour': hour_str,
                'count': count,
                'avg_utilization': sum(utilization_values) / len(utilization_values),
                'max_utilization': max(utilization_values),
                'min_utilization': min(utilization_values),
                'avg_memory_used_mb': sum(memory_used_values) / len(memory_used_values),
                'avg_memory_free_mb': sum(memory_free_values) / len(memory_free_values),
            }

            if temperature_values:
                aggregated['avg_temperature'] = sum(temperature_values) / len(temperature_values)
                aggregated['max_temperature'] = max(temperature_values)

            # 存储聚合数据
            agg_key = f"load:hourly:{gpu_id}:{hour_str}"
            self.redis_client.hset(agg_key, mapping={
                'count': str(aggregated['count']),
                'avg_utilization': str(aggregated['avg_utilization']),
                'max_utilization': str(aggregated['max_utilization']),
                'min_utilization': str(aggregated['min_utilization']),
                'avg_memory_used_mb': str(aggregated['avg_memory_used_mb']),
                'avg_memory_free_mb': str(aggregated['avg_memory_free_mb']),
            })
            self.redis_client.expire(agg_key, self.hourly_data_retention_days * 24 * 3600)

            return aggregated

        except Exception as e:
            logger.error(f"小时聚合失败: {e}")
            return None

    def get_hourly_stats(
        self,
        gpu_id: int,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        获取小时统计

        Args:
            gpu_id: GPU ID
            hours: 获取最近多少小时

        Returns:
            小时统计数据列表
        """
        try:
            stats = []
            now = datetime.now()

            for i in range(hours):
                dt = now - timedelta(hours=i)
                hour_str = dt.strftime('%Y-%m-%d-%H')

                agg_key = f"load:hourly:{gpu_id}:{hour_str}"
                data = self.redis_client.hgetall(agg_key)

                if data:
                    stats.append({
                        'hour': hour_str,
                        'avg_utilization': float(data['avg_utilization']),
                        'max_utilization': float(data['max_utilization']),
                        'min_utilization': float(data['min_utilization']),
                        'avg_memory_used_mb': float(data['avg_memory_used_mb']),
                        'count': int(data['count'])
                    })

            return stats

        except Exception as e:
            logger.error(f"获取小时统计失败: {e}")
            return []

    def get_daily_summary(self, gpu_id: int, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取每日摘要

        Args:
            gpu_id: GPU ID
            days: 获取最近几天

        Returns:
            每日摘要列表
        """
        try:
            summaries = []
            now = datetime.now()

            for i in range(days):
                dt = now - timedelta(days=i)
                date_str = dt.strftime('%Y-%m-%d')

                # 获取该天的所有小时数据
                daily_utils = []
                daily_memory = []

                for hour in range(24):
                    hour_str = f"{date_str}-{hour:02d}"
                    agg_key = f"load:hourly:{gpu_id}:{hour_str}"
                    data = self.redis_client.hgetall(agg_key)

                    if data:
                        daily_utils.append(float(data['avg_utilization']))
                        daily_memory.append(float(data['avg_memory_used_mb']))

                if daily_utils:
                    summaries.append({
                        'date': date_str,
                        'avg_utilization': sum(daily_utils) / len(daily_utils),
                        'max_utilization': max(daily_utils),
                        'min_utilization': min(daily_utils),
                        'avg_memory_used_mb': sum(daily_memory) / len(daily_memory),
                        'data_points': len(daily_utils)
                    })

            return summaries

        except Exception as e:
            logger.error(f"获取每日摘要失败: {e}")
            return []

    def get_peak_hours(
        self,
        gpu_id: int,
        days: int = 7,
        top_n: int = 5
    ) -> List[Tuple[str, float]]:
        """
        获取负载最高的时段

        Args:
            gpu_id: GPU ID
            days: 分析最近几天
            top_n: 返回前N个峰值时段

        Returns:
            [(hour_str, avg_utilization)] 列表
        """
        try:
            hourly_stats = self.get_hourly_stats(gpu_id, hours=days * 24)

            # 按平均利用率排序
            peaks = [
                (stat['hour'], stat['avg_utilization'])
                for stat in hourly_stats
            ]
            peaks.sort(key=lambda x: x[1], reverse=True)

            return peaks[:top_n]

        except Exception as e:
            logger.error(f"获取峰值时段失败: {e}")
            return []

    def cleanup_old_data(self) -> int:
        """
        清理过期数据

        Returns:
            清理的数据点数量
        """
        try:
            cleaned = 0
            now = time.time()

            # 清理原始数据
            raw_keys = self.redis_client.keys("load:raw:*")
            for key in raw_keys:
                ttl = self.redis_client.ttl(key)
                if ttl == -1:  # 没有设置过期时间
                    self.redis_client.expire(key, self.raw_data_retention_days * 24 * 3600)

            # 清理时间线索引中的过期成员
            from .utils import get_gpu_count
            gpu_count = get_gpu_count()

            for gpu_id in range(gpu_count):
                timeline_key = f"load:timeline:{gpu_id}"
                # 删除7天前的数据
                cutoff_time = now - (self.raw_data_retention_days * 24 * 3600)
                removed = self.redis_client.zremrangebyscore(
                    timeline_key,
                    0,
                    cutoff_time
                )
                cleaned += removed

            if cleaned > 0:
                logger.info(f"清理了 {cleaned} 条过期历史数据")

            return cleaned

        except Exception as e:
            logger.error(f"清理数据失败: {e}")
            return 0

    def export_data(
        self,
        gpu_id: int,
        start_time: float,
        end_time: float,
        filepath: str
    ) -> bool:
        """
        导出历史数据到文件

        Args:
            gpu_id: GPU ID
            start_time: 开始时间戳
            end_time: 结束时间戳
            filepath: 输出文件路径

        Returns:
            是否成功
        """
        try:
            import json

            data_points = self.get_data_range(gpu_id, start_time, end_time, limit=10000)

            with open(filepath, 'w') as f:
                json.dump(data_points, f, indent=2)

            logger.info(f"导出了 {len(data_points)} 条数据到 {filepath}")
            return True

        except Exception as e:
            logger.error(f"导出数据失败: {e}")
            return False


def main():
    """主函数 - 用于测试"""
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(levelname)s] - %(message)s'
    )

    print("=" * 60)
    print("历史数据管理测试")
    print("=" * 60)

    history = LoadHistory()

    # 测试1: 获取每日摘要
    print("\n测试1: 获取每日摘要（GPU 0）")
    print("-" * 60)
    summaries = history.get_daily_summary(0, days=7)
    if summaries:
        print(f"最近 {len(summaries)} 天的摘要:")
        for summary in reversed(summaries[:3]):  # 显示最近3天
            print(f"  {summary['date']}:")
            print(f"    平均利用率: {summary['avg_utilization']:.1f}%")
            print(f"    峰值利用率: {summary['max_utilization']:.1f}%")
            print(f"    平均内存: {summary['avg_memory_used_mb']:.0f}MB")
    else:
        print("⚠️  暂无历史数据")

    # 测试2: 获取峰值时段
    print("\n测试2: 获取峰值时段（GPU 0）")
    print("-" * 60)
    peaks = history.get_peak_hours(0, days=7, top_n=5)
    if peaks:
        print("负载最高的5个时段:")
        for hour, util in peaks:
            print(f"  {hour}: {util:.1f}%")
    else:
        print("⚠️  暂无峰值数据")

    # 测试3: 清理过期数据
    print("\n测试3: 清理过期数据")
    print("-" * 60)
    cleaned = history.cleanup_old_data()
    print(f"清理了 {cleaned} 条过期数据")

    print("\n✅ 所有测试完成")


if __name__ == '__main__':
    main()
