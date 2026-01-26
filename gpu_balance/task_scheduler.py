"""
任务调度模块

基于GPU实时状态智能分配collect和train任务到最优GPU
"""
import time
import os
import redis
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict

from .config import get_config
from .utils import get_redis_client, get_available_gpus
from .process_tracker import ProcessTracker, ProcessInfo
from .threshold_manager import ThresholdManager


logger = logging.getLogger('gpu_balance')


@dataclass
class AllocationScore:
    """GPU分配评分"""
    gpu_id: int
    score: float  # 0-100, 越高越优
    utilization: float
    memory_free_mb: int
    num_processes: int
    reasons: List[str]  # 评分原因


class TaskScheduler:
    """
    任务调度器类

    职责:
    1. 从Redis读取GPU可用性
    2. 为collect/train任务分配最优GPU
    3. 均等对待collect和train任务
    4. 考虑负载均衡策略
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None,
                 config=None):
        """
        初始化任务调度器

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
        self.process_tracker = ProcessTracker(
            redis_client=self.redis_client,
            config=self.config
        )

        # 初始化阈值管理器
        self.threshold_manager = ThresholdManager(
            redis_client=self.redis_client,
            config=self.config
        )

    def get_gpu_metrics(self, gpu_id: int) -> Optional[Dict[str, Any]]:
        """
        从Redis获取GPU指标

        Args:
            gpu_id: GPU ID

        Returns:
            GPU指标字典，如果不存在返回None
        """
        try:
            metrics = self.redis_client.hgetall(f"gpu:metrics:{gpu_id}")
            if not metrics:
                return None

            # 转换数值类型
            result = {
                'gpu_id': int(metrics.get('gpu_id', gpu_id)),
                'utilization': float(metrics.get('utilization', 0)),
                'memory_used_mb': int(metrics.get('memory_used_mb', 0)),
                'memory_total_mb': int(metrics.get('memory_total_mb', 0)),
                'memory_free_mb': int(metrics.get('memory_free_mb', 0)),
                'temperature': int(metrics.get('temperature', 0)),
                'num_processes': int(metrics.get('num_processes', 0)),
                'timestamp': float(metrics.get('timestamp', 0))
            }

            return result

        except Exception as e:
            logger.error(f"获取GPU {gpu_id}指标失败: {e}")
            return None

    def score_gpu(self, gpu_id: int, task_type: str) -> AllocationScore:
        """
        为GPU打分

        评分标准:
        1. 利用率越低越好 (0-40分)
        2. 可用内存越大越好 (0-30分)
        3. 进程数越少越好 (0-20分)
        4. 温度越低越好 (0-10分)

        Args:
            gpu_id: GPU ID
            task_type: 任务类型 ('collect', 'train')

        Returns:
            分配评分对象
        """
        metrics = self.get_gpu_metrics(gpu_id)

        if not metrics:
            # GPU无指标数据，给予最低分
            return AllocationScore(
                gpu_id=gpu_id,
                score=0.0,
                utilization=100.0,
                memory_free_mb=0,
                num_processes=999,
                reasons=["无GPU指标数据"]
            )

        reasons = []
        score = 0.0

        # 获取自适应阈值（如果启用）
        thresholds = self.threshold_manager.get_adaptive_thresholds()
        min_memory = thresholds.min_memory_mb
        max_util = thresholds.max_utilization

        # 1. 利用率评分 (0-40分)
        util = metrics['utilization']
        util_score = max(0, 40 * (1 - util / 100))
        score += util_score
        reasons.append(f"利用率{util:.1f}%: +{util_score:.1f}分")

        # 2. 可用内存评分 (0-30分)
        mem_free = metrics['memory_free_mb']
        if mem_free >= min_memory:
            # 超过最小内存越多越好
            mem_score = min(30, 30 * (mem_free - min_memory) / (8000 - min_memory))
            score += mem_score
            reasons.append(f"可用内存{mem_free}MB: +{mem_score:.1f}分")
        else:
            reasons.append(f"可用内存不足{mem_free}MB < {min_memory}MB")

        # 3. 进程数评分 (0-20分)
        num_procs = metrics['num_processes']
        proc_score = max(0, 20 * (1 - num_procs / 5))  # 假设5个进程为满载
        score += proc_score
        reasons.append(f"进程数{num_procs}: +{proc_score:.1f}分")

        # 4. 温度评分 (0-10分)
        temp = metrics.get('temperature', 0)
        if temp > 0:
            max_temp = self.config.gpu_balancing['thresholds']['max_temperature']
            temp_score = max(0, 10 * (1 - temp / max_temp))
            score += temp_score
            reasons.append(f"温度{temp}°C: +{temp_score:.1f}分")

        return AllocationScore(
            gpu_id=gpu_id,
            score=score,
            utilization=util,
            memory_free_mb=mem_free,
            num_processes=num_procs,
            reasons=reasons
        )

    def allocate_gpu(self, task_type: str = 'collect',
                     constraints: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        为单个任务分配最优GPU

        Args:
            task_type: 任务类型 ('collect', 'train')
            constraints: 约束条件
                - min_memory_mb: 最小内存需求
                - max_utilization: 最大可接受利用率
                - specific_gpu: 指定GPU ID（优先使用）

        Returns:
            分配的GPU ID，如果没有可用GPU返回None
        """
        try:
            # 获取自适应阈值（如果启用）
            thresholds = self.threshold_manager.get_adaptive_thresholds()

            # 获取可用GPU列表（使用自适应阈值）
            min_memory = constraints.get('min_memory_mb', thresholds.min_memory_mb)
            max_util = constraints.get('max_utilization', thresholds.max_utilization)

            available_gpus = get_available_gpus(
                self.redis_client,
                min_memory_mb=min_memory,
                max_utilization=max_util
            )

            if not available_gpus:
                logger.warning(f"无可用GPU (task_type={task_type})")
                return None

            # 如果指定了特定GPU
            specific_gpu = constraints.get('specific_gpu') if constraints else None
            if specific_gpu is not None and specific_gpu in available_gpus:
                logger.info(
                    f"分配指定GPU {specific_gpu} 给 {task_type} 任务"
                )
                return specific_gpu

            # 为所有可用GPU打分
            scores = []
            for gpu_id in available_gpus:
                score = self.score_gpu(gpu_id, task_type)
                scores.append(score)

            # 按分数排序，选择最高分
            scores.sort(key=lambda x: x.score, reverse=True)
            best = scores[0]

            logger.info(
                f"为{task_type}任务分配GPU {best.gpu_id} "
                f"(评分: {best.score:.1f}, "
                f"利用率: {best.utilization:.1f}%, "
                f"可用内存: {best.memory_free_mb}MB)"
            )
            logger.debug(f"评分详情: {'; '.join(best.reasons)}")

            return best.gpu_id

        except Exception as e:
            logger.error(f"分配GPU失败 (task_type={task_type}): {e}")
            return None

    def allocate_gpus(self, task_type: str = 'collect',
                      count: int = 1,
                      constraints: Optional[Dict[str, Any]] = None) -> List[int]:
        """
        为多个任务分配GPU

        Args:
            task_type: 任务类型 ('collect', 'train')
            count: 需要的GPU数量
                - 正数: 分配指定数量的GPU
                - -1: 分配所有可用GPU
            constraints: 约束条件

        Returns:
            分配的GPU ID列表
        """
        try:
            # 获取自适应阈值（如果启用）
            thresholds = self.threshold_manager.get_adaptive_thresholds()

            # 获取可用GPU（使用自适应阈值）
            min_memory = constraints.get('min_memory_mb', thresholds.min_memory_mb)
            max_util = constraints.get('max_utilization', thresholds.max_utilization)

            available_gpus = get_available_gpus(
                self.redis_client,
                min_memory_mb=min_memory,
                max_utilization=max_util
            )

            if not available_gpus:
                logger.warning(f"无可用GPU (task_type={task_type})")
                return []

            # count=-1表示返回所有可用GPU
            if count == -1:
                count = len(available_gpus)

            # 为所有可用GPU打分
            scores = []
            for gpu_id in available_gpus:
                score = self.score_gpu(gpu_id, task_type)
                scores.append(score)

            # 按分数排序
            scores.sort(key=lambda x: x.score, reverse=True)

            # 返回前N个最优GPU
            allocated = [s.gpu_id for s in scores[:count]]

            logger.info(
                f"为{task_type}任务分配{len(allocated)}个GPU: {allocated}"
            )

            return allocated

        except Exception as e:
            logger.error(f"分配多个GPU失败 (task_type={task_type}, count={count}): {e}")
            return []

    def get_allocation_status(self) -> Dict[str, Any]:
        """
        获取当前分配状态

        Returns:
            分配状态字典
        """
        try:
            # 获取所有GPU的进程
            gpu_processes = self.process_tracker.get_process_count_by_gpu()

            # 获取所有进程
            all_processes = self.process_tracker.get_all_processes()

            # 按类型统计
            type_counts = defaultdict(int)
            for proc in all_processes:
                type_counts[proc.proc_type] += 1

            # 获取可用GPU
            available = self.redis_client.smembers("gpu:available")
            available_gpus = sorted([int(g) for g in available])

            status = {
                'total_processes': len(all_processes),
                'by_type': dict(type_counts),
                'by_gpu': gpu_processes,
                'available_gpus': available_gpus,
                'timestamp': time.time()
            }

            return status

        except Exception as e:
            logger.error(f"获取分配状态失败: {e}")
            return {}

    def recommend_allocation(self, task_type: str,
                           num_tasks: int = 1) -> Dict[str, Any]:
        """
        推荐任务分配策略

        Args:
            task_type: 任务类型 ('collect', 'train')
            num_tasks: 任务数量

        Returns:
            推荐分配字典
            {
                'strategy': 'spread' | 'concentrate',
                'gpu_ids': [0, 1, 2],
                'reasons': ['原因1', '原因2']
            }
        """
        try:
            available_gpus = get_available_gpus(
                self.redis_client,
                min_memory_mb=self.config.gpu_balancing['thresholds']['min_memory_mb'],
                max_utilization=self.config.gpu_balancing['thresholds']['max_utilization']
            )

            if not available_gpus:
                return {
                    'strategy': 'none',
                    'gpu_ids': [],
                    'reasons': ['无可用GPU']
                }

            num_available = len(available_gpus)
            reasons = []

            # 策略判断
            if num_tasks <= num_available:
                # 任务数 <= 可用GPU数，分散到不同GPU
                strategy = 'spread'
                gpu_ids = available_gpus[:num_tasks]
                reasons.append(
                    f"任务数({num_tasks}) <= 可用GPU数({num_available})，分散分配"
                )
            elif num_tasks <= num_available * 2:
                # 任务数 <= 2倍可用GPU数，每个GPU分配1-2个任务
                strategy = 'balanced'
                gpu_ids = available_gpus
                reasons.append(
                    f"任务数({num_tasks})适中，均衡使用{num_available}个GPU"
                )
            else:
                # 任务数很多，集中使用最优GPU
                strategy = 'concentrate'
                # 选择评分最高的GPU
                scores = []
                for gpu_id in available_gpus:
                    score = self.score_gpu(gpu_id, task_type)
                    scores.append(score)
                scores.sort(key=lambda x: x.score, reverse=True)
                gpu_ids = [s.gpu_id for s in scores[:max(1, num_available // 2)]]
                reasons.append(
                    f"任务数({num_tasks})较多，集中使用最优{len(gpu_ids)}个GPU"
                )

            return {
                'strategy': strategy,
                'gpu_ids': gpu_ids,
                'reasons': reasons
            }

        except Exception as e:
            logger.error(f"推荐分配失败: {e}")
            return {
                'strategy': 'error',
                'gpu_ids': [],
                'reasons': [str(e)]
            }


def main():
    """主函数 - 用于测试"""
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(levelname)s] - %(message)s'
    )

    print("=" * 60)
    print("任务调度器测试")
    print("=" * 60)

    scheduler = TaskScheduler()

    # 测试1: 为单个collect任务分配GPU
    print("\n测试1: 为单个collect任务分配GPU")
    print("-" * 60)
    gpu_id = scheduler.allocate_gpu('collect')
    if gpu_id is not None:
        print(f"✅ 分配GPU: {gpu_id}")
    else:
        print("❌ 无可用GPU")

    # 测试2: 为多个train任务分配GPU
    print("\n测试2: 为3个train任务分配GPU")
    print("-" * 60)
    gpu_ids = scheduler.allocate_gpus('train', count=3)
    print(f"分配GPU: {gpu_ids}")

    # 测试3: 获取分配状态
    print("\n测试3: 获取分配状态")
    print("-" * 60)
    status = scheduler.get_allocation_status()
    print(f"总进程数: {status.get('total_processes', 0)}")
    print(f"按类型: {status.get('by_type', {})}")
    print(f"按GPU: {status.get('by_gpu', {})}")
    print(f"可用GPU: {status.get('available_gpus', [])}")

    # 测试4: 推荐分配策略
    print("\n测试4: 推荐分配策略")
    print("-" * 60)
    for num_tasks in [1, 4, 8]:
        rec = scheduler.recommend_allocation('collect', num_tasks)
        print(f"{num_tasks}个collect任务:")
        print(f"  策略: {rec['strategy']}")
        print(f"  GPU: {rec['gpu_ids']}")
        print(f"  原因: {'; '.join(rec['reasons'])}")

    print("\n✅ 所有测试完成")


if __name__ == '__main__':
    main()
