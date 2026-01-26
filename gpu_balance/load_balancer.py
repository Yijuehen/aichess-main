"""
负载均衡模块

检测GPU负载不均衡状态，生成重新平衡计划
支持两种策略:
1. 不迁移进程 (推荐，简单) - 暂停过载GPU上的新任务，在空闲GPU上启动新任务
2. 进程迁移 (可选，复杂) - 优雅终止进程，在空闲GPU上重启
"""
import time
import os
import signal
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .config import get_config
from .utils import get_redis_client
from .process_tracker import ProcessTracker, ProcessInfo
from .gpu_monitor import GPUMonitor, GPUMetrics


logger = logging.getLogger('gpu_balance')


class BalanceStrategy(Enum):
    """负载均衡策略"""
    NO_MIGRATION = "no_migration"  # 不迁移进程，只影响新任务
    PROCESS_MIGRATION = "process_migration"  # 迁移进程（可选）


@dataclass
class GPUStatus:
    """GPU状态数据类"""
    gpu_id: int
    metrics: GPUMetrics
    processes: List[ProcessInfo] = field(default_factory=list)

    @property
    def is_overloaded(self) -> bool:
        """是否过载"""
        return (
            self.metrics.utilization > 85.0 or
            (self.metrics.memory_used_mb / self.metrics.memory_total_mb) > 0.9
        )

    @property
    def is_idle(self) -> bool:
        """是否空闲"""
        return (
            self.metrics.utilization < 50.0 and
            self.metrics.memory_free_mb > 2000  # 至少2GB空闲
        )

    @property
    def load_score(self) -> float:
        """负载评分 (0-100, 越高负载越大)"""
        util_score = self.metrics.utilization
        mem_ratio = self.metrics.memory_used_mb / self.metrics.memory_total_mb
        mem_score = mem_ratio * 100
        return (util_score + mem_score) / 2


@dataclass
class RebalanceAction:
    """重新平衡动作"""
    action_type: str  # 'pause_new_tasks', 'migrate_process', 'start_new_task'
    source_gpu: Optional[int]
    target_gpu: Optional[int]
    process_id: Optional[int]
    reason: str
    priority: int  # 0-10, 越高越优先


class LoadBalancer:
    """
    负载均衡器类

    职责:
    1. 检测GPU负载不均衡
    2. 生成重新平衡计划
    3. 执行平衡动作（可选）
    """

    def __init__(self, redis_client=None, config=None):
        """
        初始化负载均衡器

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
        self.gpu_monitor = GPUMonitor(
            redis_client=self.redis_client,
            config=self.config
        )

    def get_gpu_status(self, gpu_id: int) -> Optional[GPUStatus]:
        """
        获取GPU状态

        Args:
            gpu_id: GPU ID

        Returns:
            GPU状态对象，如果获取失败返回None
        """
        try:
            # 获取GPU指标
            metrics_dict = self.gpu_monitor.monitor_once()
            if gpu_id not in metrics_dict:
                return None

            metrics = metrics_dict[gpu_id]

            # 获取GPU上的进程
            processes = self.process_tracker.get_processes_by_gpu(gpu_id)

            return GPUStatus(
                gpu_id=gpu_id,
                metrics=metrics,
                processes=processes
            )

        except Exception as e:
            logger.error(f"获取GPU {gpu_id}状态失败: {e}")
            return None

    def detect_imbalance(self) -> Dict[str, Any]:
        """
        检测负载不均衡状态

        Returns:
            不均衡状态字典:
            {
                'is_imbalanced': bool,
                'overloaded_gpus': List[int],
                'idle_gpus': List[int],
                'load_variance': float,
                'details': Dict
            }
        """
        try:
            # 获取所有GPU状态
            metrics_dict = self.gpu_monitor.monitor_once()
            if not metrics_dict:
                return {
                    'is_imbalanced': False,
                    'overloaded_gpus': [],
                    'idle_gpus': [],
                    'load_variance': 0.0,
                    'details': {}
                }

            gpu_statuses = []
            load_scores = []

            for gpu_id, metrics in metrics_dict.items():
                processes = self.process_tracker.get_processes_by_gpu(gpu_id)
                status = GPUStatus(
                    gpu_id=gpu_id,
                    metrics=metrics,
                    processes=processes
                )
                gpu_statuses.append(status)
                load_scores.append(status.load_score)

            # 检测过载和空闲GPU
            overloaded = [s.gpu_id for s in gpu_statuses if s.is_overloaded]
            idle = [s.gpu_id for s in gpu_statuses if s.is_idle]

            # 计算负载方差
            if len(load_scores) > 1:
                avg_load = sum(load_scores) / len(load_scores)
                variance = sum((x - avg_load) ** 2 for x in load_scores) / len(load_scores)
            else:
                variance = 0.0

            # 判断是否不均衡
            is_imbalanced = len(overloaded) > 0 and len(idle) > 0

            # 详细信息
            details = {
                gpu_id: {
                    'utilization': s.metrics.utilization,
                    'memory_used_mb': s.metrics.memory_used_mb,
                    'memory_total_mb': s.metrics.memory_total_mb,
                    'memory_free_mb': s.metrics.memory_free_mb,
                    'num_processes': len(s.processes),
                    'load_score': s.load_score,
                    'is_overloaded': s.is_overloaded,
                    'is_idle': s.is_idle
                }
                for s in gpu_statuses
            }

            result = {
                'is_imbalanced': is_imbalanced,
                'overloaded_gpus': overloaded,
                'idle_gpus': idle,
                'load_variance': variance,
                'avg_load': avg_load if load_scores else 0.0,
                'details': details
            }

            if is_imbalanced:
                logger.warning(
                    f"检测到负载不均衡: 过载GPU={overloaded}, 空闲GPU={idle}, "
                    f"方差={variance:.2f}"
                )

            return result

        except Exception as e:
            logger.error(f"检测负载不均衡失败: {e}")
            return {
                'is_imbalanced': False,
                'overloaded_gpus': [],
                'idle_gpus': [],
                'load_variance': 0.0,
                'details': {}
            }

    def create_rebalance_plan(
        self,
        imbalance_info: Dict[str, Any],
        strategy: BalanceStrategy = BalanceStrategy.NO_MIGRATION
    ) -> List[RebalanceAction]:
        """
        创建重新平衡计划

        Args:
            imbalance_info: 不均衡状态信息
            strategy: 平衡策略

        Returns:
            重新平衡动作列表
        """
        actions = []
        overloaded = imbalance_info['overloaded_gpus']
        idle = imbalance_info['idle_gpus']

        if not overloaded or not idle:
            logger.info("负载均衡，无需重新平衡")
            return actions

        logger.info(f"创建重新平衡计划: 策略={strategy.value}")

        if strategy == BalanceStrategy.NO_MIGRATION:
            # 策略1: 不迁移进程
            # 动作: 标记过载GPU，暂停新任务分配
            for gpu_id in overloaded:
                actions.append(RebalanceAction(
                    action_type='pause_new_tasks',
                    source_gpu=gpu_id,
                    target_gpu=None,
                    process_id=None,
                    reason=f'GPU {gpu_id} 过载，暂停新任务分配',
                    priority=7
                ))

            # 动作: 标记空闲GPU，鼓励新任务分配
            for gpu_id in idle:
                actions.append(RebalanceAction(
                    action_type='encourage_new_tasks',
                    source_gpu=None,
                    target_gpu=gpu_id,
                    process_id=None,
                    reason=f'GPU {gpu_id} 空闲，鼓励新任务分配',
                    priority=5
                ))

        elif strategy == BalanceStrategy.PROCESS_MIGRATION:
            # 策略2: 迁移进程
            # 为每个空闲GPU分配一个过载GPU的进程
            for idle_gpu in idle:
                if not overloaded:
                    break

                # 选择负载最高的过载GPU
                source_gpu = max(overloaded, key=lambda g: imbalance_info['details'][g]['load_score'])

                # 获取该GPU上的进程
                processes = self.process_tracker.get_processes_by_gpu(source_gpu)
                if not processes:
                    overloaded.remove(source_gpu)
                    continue

                # 选择优先级最低的进程进行迁移
                process_to_migrate = min(processes, key=lambda p: p.priority)

                actions.append(RebalanceAction(
                    action_type='migrate_process',
                    source_gpu=source_gpu,
                    target_gpu=idle_gpu,
                    process_id=process_to_migrate.pid,
                    reason=(
                        f'将进程 {process_to_migrate.pid} 从过载GPU {source_gpu} '
                        f'迁移到空闲GPU {idle_gpu}'
                    ),
                    priority=8
                ))

                # 从过载列表中移除（每个源GPU只迁移一个进程）
                overloaded.remove(source_gpu)

        # 按优先级排序
        actions.sort(key=lambda a: a.priority, reverse=True)

        logger.info(f"生成了 {len(actions)} 个平衡动作")
        for action in actions:
            logger.info(f"  - {action.action_type}: {action.reason}")

        return actions

    def execute_action(self, action: RebalanceAction) -> bool:
        """
        执行平衡动作

        Args:
            action: 平衡动作

        Returns:
            是否成功
        """
        try:
            if action.action_type == 'pause_new_tasks':
                # 标记过载GPU，暂停新任务分配
                # 通过Redis设置标志
                self.redis_client.sadd('gpu:paused_new_tasks', action.source_gpu)
                logger.info(f"✅ 已暂停GPU {action.source_gpu}上的新任务分配")
                return True

            elif action.action_type == 'encourage_new_tasks':
                # 标记空闲GPU，鼓励新任务分配
                self.redis_client.sadd('gpu:preferred_for_new_tasks', action.target_gpu)
                logger.info(f"✅ 已标记GPU {action.target_gpu}为优先分配")
                return True

            elif action.action_type == 'migrate_process':
                # 进程迁移（可选）
                if not self.config.gpu_balancing['enable_migration']:
                    logger.warning("进程迁移未启用，跳过迁移动作")
                    return False

                return self._migrate_process(
                    action.process_id,
                    action.source_gpu,
                    action.target_gpu
                )

            else:
                logger.warning(f"未知动作类型: {action.action_type}")
                return False

        except Exception as e:
            logger.error(f"执行动作失败: {e}")
            return False

    def _migrate_process(self, pid: int, source_gpu: int, target_gpu: int) -> bool:
        """
        迁移进程（谨慎操作！）

        Args:
            pid: 进程ID
            source_gpu: 源GPU
            target_gpu: 目标GPU

        Returns:
            是否成功
        """
        try:
            # 1. 检查进程是否存在
            process = self.process_tracker.get_process_info(pid)
            if not process:
                logger.warning(f"进程不存在: PID={pid}")
                return False

            # 2. 仅在collect进程的游戏结束时迁移
            if process.proc_type == 'collect':
                logger.info(
                    f"等待进程 {pid} (collect) 完成当前游戏后迁移... "
                    f"(不建议强制终止)"
                )
                # 实际实现中，应该等待游戏自然结束
                # 这里只记录建议，不强制迁移
                return False

            elif process.proc_type == 'train':
                # 训练进程不建议迁移（状态复杂）
                logger.warning(f"训练进程不建议迁移: PID={pid}")
                return False

            else:
                logger.warning(f"未知进程类型: {process.proc_type}")
                return False

        except Exception as e:
            logger.error(f"迁移进程失败: {e}")
            return False

    def balance_once(
        self,
        strategy: BalanceStrategy = BalanceStrategy.NO_MIGRATION
    ) -> Dict[str, Any]:
        """
        执行一次负载平衡

        Args:
            strategy: 平衡策略

        Returns:
            平衡结果字典
        """
        logger.info("=" * 60)
        logger.info("开始负载平衡检查")
        logger.info("=" * 60)

        # 1. 检测不均衡状态
        imbalance_info = self.detect_imbalance()

        if not imbalance_info['is_imbalanced']:
            logger.info("✅ 负载均衡，无需调整")
            return {
                'balanced': True,
                'actions_taken': 0,
                'details': imbalance_info
            }

        # 2. 创建重新平衡计划
        actions = self.create_rebalance_plan(imbalance_info, strategy)

        if not actions:
            logger.info("⚠️  无法生成有效的平衡计划")
            return {
                'balanced': False,
                'actions_taken': 0,
                'details': imbalance_info
            }

        # 3. 执行平衡动作
        executed = 0
        for action in actions:
            if self.execute_action(action):
                executed += 1

        logger.info("=" * 60)
        logger.info(f"负载平衡完成: 执行了 {executed}/{len(actions)} 个动作")
        logger.info("=" * 60)

        return {
            'balanced': executed > 0,
            'actions_taken': executed,
            'actions_total': len(actions),
            'details': imbalance_info
        }

    def clear_balance_flags(self) -> bool:
        """
        清除平衡标志（恢复正常分配）

        Returns:
            是否成功
        """
        try:
            self.redis_client.delete('gpu:paused_new_tasks')
            self.redis_client.delete('gpu:preferred_for_new_tasks')
            logger.info("✅ 已清除负载平衡标志")
            return True
        except Exception as e:
            logger.error(f"清除平衡标志失败: {e}")
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
    print("负载均衡器测试")
    print("=" * 60)

    balancer = LoadBalancer()

    # 测试1: 检测负载不均衡
    print("\n测试1: 检测负载不均衡")
    print("-" * 60)
    imbalance = balancer.detect_imbalance()
    print(f"是否不均衡: {imbalance['is_imbalanced']}")
    print(f"过载GPU: {imbalance['overloaded_gpus']}")
    print(f"空闲GPU: {imbalance['idle_gpus']}")
    print(f"负载方差: {imbalance['load_variance']:.2f}")
    print(f"平均负载: {imbalance.get('avg_load', 0):.2f}")

    # 测试2: 生成重新平衡计划
    if imbalance['is_imbalanced']:
        print("\n测试2: 生成重新平衡计划")
        print("-" * 60)

        # 测试两种策略
        for strategy in [BalanceStrategy.NO_MIGRATION, BalanceStrategy.PROCESS_MIGRATION]:
            print(f"\n策略: {strategy.value}")
            plan = balancer.create_rebalance_plan(imbalance, strategy)
            print(f"动作数量: {len(plan)}")
            for action in plan:
                print(f"  - [{action.priority}] {action.action_type}: {action.reason}")

    # 测试3: 执行一次负载平衡（使用安全策略）
    print("\n测试3: 执行负载平衡")
    print("-" * 60)
    result = balancer.balance_once(strategy=BalanceStrategy.NO_MIGRATION)
    print(f"平衡结果: {result['balanced']}")
    print(f"执行动作: {result.get('actions_taken', 0)}")

    # 清理标志
    print("\n清理测试标志...")
    balancer.clear_balance_flags()

    print("\n✅ 所有测试完成")


if __name__ == '__main__':
    main()
