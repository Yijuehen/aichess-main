#!/usr/bin/env python
"""
负载均衡守护进程

定期检查GPU负载并执行重新平衡
可作为后台守护进程运行
"""
import time
import os
import sys
import signal
import logging
import argparse
from datetime import datetime
from threading import Event

from .load_balancer import LoadBalancer, BalanceStrategy
from .config import get_config
from .utils import get_redis_client


# 配置日志
logger = logging.getLogger('gpu_balance')


class BalanceDaemon:
    """
    负载均衡守护进程

    职责:
    1. 定期检查GPU负载
    2. 自动执行负载平衡
    3. 记录平衡历史
    4. 优雅处理停止信号
    """

    def __init__(self, interval: float = 60.0, strategy: BalanceStrategy = BalanceStrategy.NO_MIGRATION):
        """
        初始化守护进程

        Args:
            interval: 检查间隔（秒）
            strategy: 平衡策略
        """
        self.interval = interval
        self.strategy = strategy
        self.config = get_config()
        self.redis_client = get_redis_client(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_db,
            decode_responses=True
        )
        self.balancer = LoadBalancer(
            redis_client=self.redis_client,
            config=self.config
        )

        self.stop_event = Event()
        self.balance_count = 0
        self.start_time = time.time()

        # 注册信号处理
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """
        信号处理器

        Args:
            signum: 信号编号
            frame: 当前栈帧
        """
        logger.info(f"收到信号 {signum}，准备停止...")
        self.stop_event.set()

    def check_and_balance(self) -> dict:
        """
        检查并执行负载平衡

        Returns:
            平衡结果字典
        """
        try:
            logger.debug("开始负载平衡检查...")

            # 执行一次负载平衡
            result = self.balancer.balance_once(strategy=self.strategy)

            if result['balanced']:
                self.balance_count += 1

                # 记录平衡历史
                self._record_balance_history(result)

            return result

        except Exception as e:
            logger.error(f"负载平衡检查失败: {e}")
            return {
                'balanced': False,
                'error': str(e)
            }

    def _record_balance_history(self, result: dict):
        """
        记录平衡历史到Redis

        Args:
            result: 平衡结果
        """
        try:
            history_key = f"balance:history:{int(time.time())}"
            history_data = {
                'timestamp': time.time(),
                'datetime': datetime.now().isoformat(),
                'actions_taken': result.get('actions_taken', 0),
                'actions_total': result.get('actions_total', 0),
                'details': result.get('details', {})
            }

            # 使用hash存储
            self.redis_client.hset(history_key, mapping=history_data)

            # 设置过期时间（7天）
            self.redis_client.expire(history_key, 7 * 24 * 3600)

            # 添加到历史索引
            self.redis_client.zadd('balance:history:index', {history_key: time.time()})

            # 保持索引只包含最近1000条记录
            self.redis_client.zremrangebyrank('balance:history:index', 0, -1001)

            logger.debug(f"已记录平衡历史: {history_key}")

        except Exception as e:
            logger.error(f"记录平衡历史失败: {e}")

    def get_status(self) -> dict:
        """
        获取守护进程状态

        Returns:
            状态字典
        """
        uptime = time.time() - self.start_time

        return {
            'running': not self.stop_event.is_set(),
            'uptime_seconds': uptime,
            'uptime_formatted': self._format_uptime(uptime),
            'balance_count': self.balance_count,
            'interval': self.interval,
            'strategy': self.strategy.value,
            'start_time': self.start_time,
            'start_time_formatted': datetime.fromtimestamp(self.start_time).isoformat()
        }

    def _format_uptime(self, seconds: float) -> str:
        """
        格式化运行时间

        Args:
            seconds: 秒数

        Returns:
            格式化的时间字符串
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def run_once(self) -> dict:
        """
        运行一次平衡检查（用于测试）

        Returns:
            平衡结果
        """
        logger.info("执行单次负载平衡检查...")
        return self.check_and_balance()

    def run(self):
        """
        运行守护进程主循环

        持续运行直到收到停止信号
        """
        logger.info("=" * 60)
        logger.info("负载均衡守护进程启动")
        logger.info("=" * 60)
        logger.info(f"检查间隔: {self.interval}秒")
        logger.info(f"平衡策略: {self.strategy.value}")
        logger.info(f"进程迁移: {'启用' if self.config.gpu_balancing['enable_migration'] else '禁用'}")
        logger.info("=" * 60)

        # 记录守护进程启动
        self.redis_client.hset(
            'balance:daemon:status',
            mapping={
                'pid': os.getpid(),
                'start_time': self.start_time,
                'strategy': self.strategy.value,
                'interval': self.interval,
                'status': 'running'
            }
        )

        try:
            while not self.stop_event.is_set():
                # 执行负载平衡
                self.check_and_balance()

                # 等待下一次检查或停止信号
                self.stop_event.wait(self.interval)

        except Exception as e:
            logger.critical(f"守护进程运行出错: {e}")
            raise

        finally:
            # 清理
            self._cleanup()

    def _cleanup(self):
        """清理资源"""
        logger.info("清理守护进程资源...")

        # 更新状态为已停止
        self.redis_client.hset(
            'balance:daemon:status',
            mapping={
                'status': 'stopped',
                'stop_time': time.time()
            }
        )

        logger.info("负载均衡守护进程已停止")
        logger.info(f"总运行时间: {self._format_uptime(time.time() - self.start_time)}")
        logger.info(f"总平衡次数: {self.balance_count}")


def main():
    """主函数"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(levelname)s] - %(message)s'
    )

    # 解析命令行参数
    parser = argparse.ArgumentParser(description='GPU负载均衡守护进程')
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='作为守护进程运行'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='只执行一次检查'
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=60.0,
        help='检查间隔（秒），默认60'
    )
    parser.add_argument(
        '--strategy',
        type=str,
        choices=['no_migration', 'process_migration'],
        default='no_migration',
        help='平衡策略，默认no_migration'
    )
    parser.add_argument(
        '--enable-migration',
        action='store_true',
        help='启用进程迁移（谨慎使用）'
    )

    args = parser.parse_args()

    # 转换策略
    if args.strategy == 'process_migration':
        strategy = BalanceStrategy.PROCESS_MIGRATION
    else:
        strategy = BalanceStrategy.NO_MIGRATION

    # 创建守护进程
    daemon = BalanceDaemon(
        interval=args.interval,
        strategy=strategy
    )

    if args.once:
        # 单次执行模式
        result = daemon.run_once()
        print("\n单次平衡结果:")
        print(f"  是否平衡: {result['balanced']}")
        print(f"  执行动作: {result.get('actions_taken', 0)}")
        sys.exit(0 if result['balanced'] else 1)

    elif args.daemon:
        # 守护进程模式
        try:
            daemon.run()
        except KeyboardInterrupt:
            logger.info("收到键盘中断，正在停止...")
            daemon._cleanup()
        sys.exit(0)

    else:
        # 交互模式（前台运行）
        print("负载均衡守护进程 - 交互模式")
        print("=" * 60)
        print(f"检查间隔: {args.interval}秒")
        print(f"平衡策略: {args.strategy}")
        print("按 Ctrl+C 停止")
        print("=" * 60)

        try:
            daemon.run()
        except KeyboardInterrupt:
            logger.info("收到键盘中断，正在停止...")
            daemon._cleanup()
        sys.exit(0)


if __name__ == '__main__':
    main()
