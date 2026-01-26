"""
进程追踪模块

追踪collect和train进程的状态，管理心跳检测
"""
import time
import os
import redis
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict

from .config import get_config
from .utils import get_redis_client, format_timestamp


logger = logging.getLogger('gpu_balance')


@dataclass
class ProcessInfo:
    """进程信息数据类"""
    pid: int
    gpu_id: int
    proc_type: str  # 'collect', 'train', 'eval'
    status: str  # 'running', 'stuck', 'dead'
    priority: int  # 0-10
    start_time: float
    last_heartbeat: float
    games_completed: int = 0  # for collect
    iteration: int = 0  # for train

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @property
def age(self) -> float:
        """进程年龄（秒）"""
        return time.time() - self.start_time

    @property
def heartbeat_age(self) -> float:
        """距离上次心跳的时间（秒）"""
        return time.time() - self.last_heartbeat


class ProcessTracker:
    """进程追踪器类"""

    def __init__(self, redis_client: Optional[redis.Redis] = None,
                 config=None):
        """
        初始化进程追踪器

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

    def register_process(self, pid: int, gpu_id: int, proc_type: str,
                         priority: int = 5) -> bool:
        """
        注册新进程

        Args:
            pid: 进程ID
            gpu_id: GPU ID
            proc_type: 进程类型 ('collect', 'train', 'eval')
            priority: 优先级 (0-10, 默认5)

        Returns:
            是否成功
        """
        try:
            # 创建进程信息
            process_info = ProcessInfo(
                pid=pid,
                gpu_id=gpu_id,
                proc_type=proc_type,
                status='running',
                priority=priority,
                start_time=time.time(),
                last_heartbeat=time.time()
            )

            # 保存到进程注册表
            self.redis_client.hset(
                f"process:{pid}",
                mapping=process_info.to_dict()
            )

            # 添加到GPU进程映射
            self.redis_client.sadd(f"gpu:{gpu_id}:processes", pid)

            # 添加到全局注册表
            self.redis_client.hset(
                "process:registry",
                mapping={str(pid): proc_type}
            )

            logger.info(
                f"注册进程: PID={pid}, GPU={gpu_id}, "
                f"类型={proc_type}, 优先级={priority}"
            )
            return True

        except Exception as e:
            logger.error(f"注册进程失败 (PID={pid}): {e}")
            return False

    def update_heartbeat(self, pid: int, **kwargs) -> bool:
        """
        更新进程心跳

        Args:
            pid: 进程ID
            **kwargs: 要更新的字段

        Returns:
            是否成功
        """
        try:
            # 更新心跳时间
            heartbeat_data = {
                'last_heartbeat': time.time(),
                **kwargs
            }

            self.redis_client.hset(f"process:{pid}", mapping=heartbeat_data)
            return True

        except Exception as e:
            logger.error(f"更新心跳失败 (PID={pid}): {e}")
            return False

    def get_process_info(self, pid: int) -> Optional[ProcessInfo]:
        """
        获取进程信息

        Args:
            pid: 进程ID

        Returns:
            进程信息对象，如果不存在返回None
        """
        try:
            data = self.redis_client.hgetall(f"process:{pid}")
            if not data:
                return None

            # 转换字段类型
            data['pid'] = int(data['pid'])
            data['gpu_id'] = int(data['gpu_id'])
            data['status'] = data['status']
            data['priority'] = int(data['priority'])
            data['start_time'] = float(data['start_time'])
            data['last_heartbeat'] = float(data['last_heartbeat'])
            data['games_completed'] = int(data.get('games_completed', 0))
            data['iteration'] = int(data.get('iteration', 0))

            return ProcessInfo(**data)

        except Exception as e:
            logger.error(f"获取进程信息失败 (PID={pid}): {e}")
            return None

    def get_processes_by_gpu(self, gpu_id: int) -> List[ProcessInfo]:
        """
        获取指定GPU上的所有进程

        Args:
            gpu_id: GPU ID

        Returns:
            进程信息列表
        """
        try:
            pids = self.redis_client.smembers(f"gpu:{gpu_id}:processes")
            processes = []

            for pid in pids:
                info = self.get_process_info(int(pid))
                if info:
                    processes.append(info)

            return processes

        except Exception as e:
            logger.error(f"获取GPU {gpu_id}进程列表失败: {e}")
            return []

    def get_all_processes(self) -> List[ProcessInfo]:
        """
        获取所有进程

        Returns:
            所有进程信息列表
        """
        try:
            # 从进程注册表获取所有PID
            pids = self.redis_client.hkeys("process:registry")
            processes = []

            for pid_str in pids:
                pid = int(pid_str)
                info = self.get_process_info(pid)
                if info:
                    processes.append(info)

            return processes

        except Exception as e:
            logger.error(f"获取所有进程失败: {e}")
            return []

    def check_heartbeats(self) -> List[int]:
        """
        检查所有进程的心跳状态

        Returns:
        超时的进程PID列表
        """
        timeout = self.config.heartbeat_timeout
        stale_pids = []

        try:
            all_processes = self.get_all_processes()

            for process in all_processes:
                # 检查心跳是否超时
                heartbeat_age = process.heartbeat_age
                if heartbeat_age > timeout:
                    logger.warning(
                        f"进程 {process.pid} 心跳超时 "
                        f"(最后心跳: {heartbeat_age:.1f}秒前)"
                    )

                    # 标记为stuck
                    self.redis_client.hset(
                        f"process:{process.pid}",
                        mapping={'status': 'stuck'}
                    )
                    stale_pids.append(process.pid)

        except Exception as e:
            logger.error(f"检查心跳失败: {e}")

        return stale_pids

    def cleanup_stale_processes(self) -> int:
        """
        清理超时进程

        Returns:
            清理的进程数量
        """
        cleaned = 0

        try:
            stale_pids = self.check_heartbeats()

            for pid in stale_pids:
                try:
                    # 获取进程信息
                    info = self.get_process_info(pid)
                    if not info:
                        continue

                    # 从GPU映射中移除
                    self.redis_client.srem(f"gpu:{info.gpu_id}:processes", pid)

                    # 从注册表移除
                    self.redis_client.hdel("process:registry", str(pid))

                    # 删除进程数据
                    self.redis_client.delete(f"process:{pid}")

                    logger.info(f"清理超时进程: PID={pid}")
                    cleaned += 1

                except Exception as e:
                    logger.error(f"清理进程 {pid} 失败: {e}")

        except Exception as e:
            logger.error(f"清理超时进程失败: {e}")

        return cleaned

    def unregister_process(self, pid: int) -> bool:
        """
        注销进程

        Args:
            pid: 进程ID

        Returns:
            是否成功
        """
        try:
            # 获取进程信息
            info = self.get_process_info(pid)
            if not info:
                logger.warning(f"进程不存在 (PID={pid})")
                return False

            # 从GPU映射中移除
            self.redis_client.srem(f"gpu:{info.gpu_id}:processes", pid)

            # 从注册表移除
            self.redis_client.hdel("process:registry", str(pid))

            # 删除进程数据
            self.redis_client.delete(f"process:{pid}")

            logger.info(f"注销进程: PID={pid}, GPU={info.gpu_id}, 类型={info.proc_type}")
            return True

        except Exception as e:
            logger.error(f"注销进程失败 (PID={pid}): {e}")
            return False

    def get_process_count_by_gpu(self) -> Dict[int, int]:
        """
        获取每个GPU的进程数量

        Returns:
            GPU ID到进程数量的映射
        """
        try:
            # 获取所有GPU:processes键
            keys = self.redis_client.keys("gpu:*:processes")

            count_dict = {}
            for key in keys:
                gpu_id = int(key.split(':')[1])
                count = self.redis_client.scard(key)
                count_dict[gpu_id] = count

            return count_dict

        except Exception as e:
            logger.error(f"获取GPU进程数量失败: {e}")
            return {}

    def get_process_count_by_type(self) -> Dict[str, int]:
        """
        按类型统计进程数量

        Returns:
            进程类型到数量的映射
        """
        try:
            all_processes = self.get_all_processes()

            count_dict = {}
            for process in all_processes:
                proc_type = process.proc_type
                count_dict[proc_type] = count_dict.get(proc_type, 0) + 1

            return count_dict

        except Exception as e:
            logger.error(f"统计进程类型失败: {e}")
            return {}

    def get_status_summary(self) -> Dict[str, Any]:
        """
        获取状态汇总

        Returns:
            状态汇总字典
        """
        try:
            all_processes = self.get_all_processes()

            running = sum(1 for p in all_processes if p.status == 'running')
            stuck = sum(1 for p in all_processes if p.status == 'stuck')

            count_by_gpu = self.get_process_count_by_gpu()
            count_by_type = self.get_process_by_type()

            summary = {
                'total_processes': len(all_processes),
                'running': running,
                'stuck': stuck,
                'by_gpu': count_by_gpu,
                'by_type': count_by_type,
                'timestamp': time.time()
            }

            return summary

        except Exception as e:
            logger.error(f"获取状态汇总失败: {e}")
            return {}


def main():
    """主函数 - 用于测试"""
    import sys

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(levelname)s] - %(message)s'
    )

    print("=" * 60)
    print("进程追踪器测试")
    print("=" * 60)

    tracker = ProcessTracker()

    # 测试注册模拟进程
    print("\n测试1: 注册模拟进程")
    print("-" * 60)
    tracker.register_process(pid=12345, gpu_id=0, proc_type='collect', priority=5)
    tracker.register_process(pid=12346, gpu_id=1, proc_type='train', priority=6)

    # 测试获取GPU进程
    print("\n测试2: 获取GPU进程")
    print("-" * 60)
    processes = tracker.get_processes_by_gpu(0)
    for proc in processes:
        print(f"  PID={proc.pid}, 类型={proc.proc_type}")

    # 测试状态汇总
    print("\n测试3: 状态汇总")
    print("-" * 60)
    summary = tracker.get_status_summary()
    print(f"总进程数: {summary['total_processes']}")
    print(f"运行中: {summary['running']}")
    print(f"卡住: {summary['stuck']}")
    print(f"按GPU: {summary['by_gpu']}")
    print(f"按类型: {summary['by_type']}")

    # 清理测试数据
    print("\n清理测试数据...")
    tracker.unregister_process(12345)
    tracker.unregister_process(12346)

    print("\n✅ 所有测试完成")


if __name__ == '__main__':
    main()
