"""
GPU负载均衡工具函数

提供Redis连接、nvidia-smi查询、日志等辅助功能
"""
import subprocess
import logging
import redis
from typing import Dict, List, Optional, Any
from datetime import datetime


# 配置日志
logger = logging.getLogger('gpu_balance')


def get_redis_client(host: str = 'localhost', port: int = 6379, db: int = 0,
                     decode_responses: bool = False) -> redis.Redis:
    """
    获取Redis客户端连接

    Args:
        host: Redis主机地址
        port: Redis端口
        db: Redis数据库编号
        decode_responses: 是否自动解码响应

    Returns:
        Redis客户端实例
    """
    try:
        client = redis.StrictRedis(
            host=host,
            port=port,
            db=db,
            decode_responses=decode_responses,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            max_retries=3
        )
        # 测试连接
        client.ping()
        return client
    except Exception as e:
        logger.error(f"Redis连接失败: {e}")
        raise


def run_nvidia_smi(query: str, gpu_id: Optional[int] = None) -> str:
    """
    执行nvidia-smi命令

    Args:
        query: nvidia-smi查询字符串
        gpu_id: 指定GPU ID (None表示查询所有GPU)

    Returns:
        命令输出
    """
    try:
        cmd = ['nvidia-smi', '--query-gpu=' + query, '--format=csv,noheader,nounits']
        if gpu_id is not None:
            cmd.extend(['-i', str(gpu_id)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )

        if result.returncode != 0:
            logger.warning(f"nvidia-smi命令失败: {result.stderr}")
            return ""

        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error("nvidia-smi命令超时")
        return ""
    except Exception as e:
        logger.error(f"执行nvidia-smi失败: {e}")
        return ""


def get_gpu_count() -> int:
    """
    获取GPU数量

    Returns:
        GPU数量
    """
    try:
        output = run_nvidia_smi('count')
        if output:
            return int(output)
        return 0
    except (ValueError, IndexError):
        logger.error("无法获取GPU数量")
        return 0


def get_gpu_memory(gpu_id: int) -> Dict[str, int]:
    """
    获取指定GPU的内存使用情况

    Args:
        gpu_id: GPU ID

    Returns:
        内存信息字典 {used, total, free}
    """
    try:
        # 获取已使用内存
        used_str = run_nvidia_smi('memory.used', gpu_id)
        memory_used = int(used_str) if used_str else 0

        # 获取总内存
        total_str = run_nvidia_smi('memory.total', gpu_id)
        memory_total = int(total_str) if total_str else 0

        memory_free = memory_total - memory_used

        return {
            'used': memory_used,
            'total': memory_total,
            'free': memory_free
        }
    except (ValueError, IndexError) as e:
        logger.error(f"GPU {gpu_id}: 获取内存信息失败: {e}")
        return {'used': 0, 'total': 0, 'free': 0}


def get_gpu_utilization(gpu_id: int) -> float:
    """
    获取指定GPU的利用率

    Args:
        gpu_id: GPU ID

    Returns:
        GPU利用率 (0-100)
    """
    try:
        util_str = run_nvidia_smi('utilization.gpu', gpu_id)
        return float(util_str) if util_str else 0.0
    except (ValueError, IndexError) as e:
        logger.error(f"GPU {gpu_id}: 获取利用率失败: {e}")
        return 0.0


def get_gpu_temperature(gpu_id: int) -> int:
    """
    获取指定GPU的温度

    Args:
        gpu_id: GPU ID

    Returns:
        GPU温度 (摄氏度)
    """
    try:
        temp_str = run_nvidia_smi('temperature.gpu', gpu_id)
        return int(temp_str) if temp_str else 0
    except (ValueError, IndexError) as e:
        logger.error(f"GPU {gpu_id}: 获取温度失败: {e}")
        return 0


def get_gpu_name(gpu_id: int) -> str:
    """
    获取指定GPU的名称

    Args:
        gpu_id: GPU ID

    Returns:
        GPU名称
    """
    try:
        name = run_nvidia_smi('name', gpu_id)
        return name if name else f"GPU {gpu_id}"
    except Exception as e:
        logger.error(f"GPU {gpu_id}: 获取名称失败: {e}")
        return f"GPU {gpu_id}"


def get_processes_on_gpu(gpu_id: int) -> List[Dict[str, Any]]:
    """
    获取运行在指定GPU上的进程列表

    Args:
        gpu_id: GPU ID

    Returns:
        进程信息列表
    """
    try:
        output = run_nvidia_smi('processes.name,processes.pid,processes.used_memory', gpu_id)
        if not output:
            return []

        processes = []
        for line in output.split('\n'):
            if not line:
                continue
            parts = line.split(',')
            if len(parts) == 3:
                processes.append({
                    'name': parts[0],
                    'pid': int(parts[1]),
                    'memory_used': int(parts[2])
                })

        return processes
    except Exception as e:
        logger.error(f"GPU {gpu_id}: 获取进程列表失败: {e}")
        return []


def publish_gpu_metrics(redis_client: redis.Redis, gpu_id: int, metrics: Dict[str, Any],
                          ttl: int = 10) -> bool:
    """
    发布GPU指标到Redis

    Args:
        redis_client: Redis客户端
        gpu_id: GPU ID
        metrics: GPU指标字典
        ttl: 过期时间（秒）

    Returns:
        是否成功
    """
    try:
        key = f"gpu:metrics:{gpu_id}"
        redis_client.hset(key, mapping=metrics)
        redis_client.expire(key, ttl)
        return True
    except Exception as e:
        logger.error(f"发布GPU {gpu_id}指标失败: {e}")
        return False


def get_available_gpus(redis_client: redis.Client,
                        min_memory_mb: int = 2000,
                        max_utilization: float = 90.0) -> List[int]:
    """
    从Redis获取可用GPU列表

    Args:
        redis_client: Redis客户端
        min_memory_mb: 最小可用内存（MB）
        max_utilization: 最大利用率

    Returns:
        可用GPU ID列表
    """
    try:
        # 获取所有GPU指标
        keys = redis_client.keys('gpu:metrics:*')
        if not keys:
            return []

        available_gpus = []
        for key in keys:
            gpu_id = int(key.split(':')[-1])
            metrics = redis_client.hgetall(key)

            if not metrics:
                continue

            # 检查条件
            memory_free = int(metrics.get(b'memory_free_mb', 0))
            utilization = float(metrics.get(b'utilization', 0))

            if memory_free >= min_memory_mb and utilization <= max_utilization:
                available_gpus.append(gpu_id)

        return sorted(available_gpus)
    except Exception as e:
        logger.error(f"获取可用GPU失败: {e}")
        return []


def format_timestamp(timestamp: float) -> str:
    """
    格式化时间戳

    Args:
        timestamp: Unix时间戳

    Returns:
        格式化的时间字符串
    """
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')


def safe_int(value: Any, default: int = 0) -> int:
    """
    安全转换为整数

    Args:
        value: 要转换的值
        default: 默认值

    Returns:
        整数值
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    安全转换为浮点数

    Args:
        value: 要转换的值
        default: 默认值

    Returns:
        浮点数值
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
