"""
GPU负载均衡配置模块

管理GPU负载均衡的所有配置参数
"""
import os
from typing import Dict, Any


class GPUBalanceConfig:
    """GPU负载均衡配置类"""

    def __init__(self):
        # 从环境变量或默认值加载配置
        self.enabled = os.getenv('GPU_BALANCING_ENABLED', 'False').lower() == 'true'

        # 监控配置
        self.monitor_interval = float(os.getenv('GPU_MONITOR_INTERVAL', '5.0'))  # 秒
        self.metrics_ttl = int(os.getenv('GPU_METRICS_TTL', '10'))  # 秒

        # GPU检测配置
        self.enable_temperature = os.getenv('GPU_MONITOR_TEMP', 'True').lower() == 'true'
        self.enable_power = os.getenv('GPU_MONITOR_POWER', 'False').lower() == 'true'

        # 负载均衡配置
        self.balance_interval = float(os.getenv('BALANCE_INTERVAL', '60.0'))  # 秒
        self.enable_migration = os.getenv('ENABLE_MIGRATION', 'False').lower() == 'true'

        # 阈值配置
        self.thresholds = {
            'min_memory_mb': int(os.getenv('MIN_GPU_MEMORY', '2000')),
            'max_utilization': float(os.getenv('MAX_GPU_UTIL', '90.0')),
            'max_temperature': int(os.getenv('MAX_GPU_TEMP', '85')),
            'util_low_threshold': float(os.getenv('UTIL_LOW', '50.0')),
            'util_high_threshold': float(os.getenv('UTIL_HIGH', '85.0')),
            'adaptive': os.getenv('ADAPTIVE_THRESHOLDS', 'True').lower() == 'true',
        }

        # 进程管理配置
        self.heartbeat_interval = float(os.getenv('HEARTBEAT_INTERVAL', '10.0'))  # 秒
        self.heartbeat_timeout = float(os.getenv('HEARTBEAT_TIMEOUT', '30.0'))  # 秒
        self.restart_on_failure = os.getenv('AUTO_RESTART', 'True').lower() == 'true'
        self.max_restart_attempts = int(os.getenv('MAX_RESTART', '3'))
        self.graceful_shutdown_timeout = int(os.getenv('SHUTDOWN_TIMEOUT', '30'))  # 秒

        # Redis配置
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.redis_db = int(os.getenv('REDIS_DB', '0'))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'enabled': self.enabled,
            'monitor_interval': self.monitor_interval,
            'metrics_ttl': self.metrics_ttl,
            'enable_temperature': self.enable_temperature,
            'enable_power': self.enable_power,
            'balance_interval': self.balance_interval,
            'enable_migration': self.enable_migration,
            'thresholds': self.thresholds,
            'heartbeat_interval': self.heartbeat_interval,
            'heartbeat_timeout': self.heartbeat_timeout,
            'restart_on_failure': self.restart_on_failure,
            'max_restart_attempts': self.max_restart_attempts,
            'graceful_shutdown_timeout': self.graceful_shutdown_timeout,
        }

    def __repr__(self) -> str:
        return f"GPUBalanceConfig(enabled={self.enabled}, monitor_interval={self.monitor_interval}s)"


# 全局配置实例
_config = None


def get_config() -> GPUBalanceConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = GPUBalanceConfig()
    return _config


def reset_config():
    """重置全局配置（用于测试）"""
    global _config
    _config = None
