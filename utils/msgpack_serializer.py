"""
MessagePack序列化工具 - 支持numpy数组和快速序列化

向后兼容: 自动检测pickle格式并转换为MessagePack
"""
import pickle
import gzip
from typing import Any

# 尝试导入msgpack，如果不可用则使用pickle
try:
    import msgpack
    import msgpack_numpy
    import numpy as np

    # 注册numpy扩展
    msgpack_numpy.patch()
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False
    msgpack = None
    msgpack_numpy = None
    np = None


class MsgPackSerializer:
    """MessagePack序列化工具 - 支持向后兼容"""

    @staticmethod
    def is_available() -> bool:
        """检查MessagePack是否可用"""
        return MSGPACK_AVAILABLE

    @staticmethod
    def dump(obj: Any, filepath: str, use_bin_type: bool = True) -> None:
        """
        保存对象到MessagePack文件

        Args:
            obj: 要序列化的对象
            filepath: 文件路径
            use_bin_type: 使用二进制类型 (更紧凑)
        """
        if not MSGPACK_AVAILABLE:
            # 回退到pickle
            with open(filepath, 'wb') as f:
                pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
            return

        with open(filepath, 'wb') as f:
            msgpack.dump(obj, f, use_bin_type=use_bin_type)

    @staticmethod
    def load(filepath: str) -> Any:
        """
        从MessagePack文件加载对象

        Args:
            filepath: 文件路径
        """
        if not MSGPACK_AVAILABLE:
            # 回退到pickle
            with open(filepath, 'rb') as f:
                return pickle.load(f)

        with open(filepath, 'rb') as f:
            return msgpack.load(f, raw=False)

    @staticmethod
    def dumps(obj: Any, use_bin_type: bool = True) -> bytes:
        """序列化为MessagePack字节"""
        if not MSGPACK_AVAILABLE:
            return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)

        return msgpack.packb(obj, use_bin_type=use_bin_type)

    @staticmethod
    def loads(data: bytes) -> Any:
        """从MessagePack字节反序列化"""
        if not MSGPACK_AVAILABLE:
            return pickle.loads(data)

        return msgpack.unpackb(data, raw=False)

    @staticmethod
    def dump_compressed(obj: Any, filepath: str, compress: bool = True) -> None:
        """保存到压缩的MessagePack文件"""
        if not MSGPACK_AVAILABLE:
            # 回退到CompressedPickle
            from utils.compression import CompressedPickle
            CompressedPickle.dump(obj, filepath, method='gzip' if compress else 'none')
            return

        data = MsgPackSerializer.dumps(obj)
        if compress:
            data = gzip.compress(data)
        with open(filepath, 'wb') as f:
            f.write(data)

    @staticmethod
    def load_compressed(filepath: str) -> Any:
        """从压缩的MessagePack文件加载"""
        if not MSGPACK_AVAILABLE:
            # 回退到CompressedPickle
            from utils.compression import CompressedPickle
            return CompressedPickle.load(filepath, method='gzip')

        with open(filepath, 'rb') as f:
            data = f.read()

        # 尝试解压
        try:
            data = gzip.decompress(data)
        except:
            pass  # 可能未压缩

        return MsgPackSerializer.loads(data)


def load_with_auto_detect(filepath: str) -> Any:
    """
    自动检测文件格式并加载
    支持格式: MessagePack, msgpack+gzip, pickle, gzip pickle

    Args:
        filepath: 文件路径

    Returns:
        加载的对象

    Raises:
        ValueError: 如果无法识别文件格式
    """
    if not MSGPACK_AVAILABLE:
        # 回退到pickle自动检测
        from utils.compression import load_with_auto_detect as pickle_load
        return pickle_load(filepath)

    # 尝试MessagePack
    try:
        return MsgPackSerializer.load(filepath)
    except Exception:
        pass

    # 尝试压缩的MessagePack
    try:
        return MsgPackSerializer.load_compressed(filepath)
    except Exception:
        pass

    # 回退到pickle
    from utils.compression import load_with_auto_detect as pickle_load
    try:
        return pickle_load(filepath)
    except Exception as e:
        raise ValueError(f"无法识别的文件格式: {filepath}, 错误: {e}")


def convert_pickle_to_msgpack(pickle_path: str, msgpack_path: str, compress: bool = False) -> None:
    """
    将pickle文件转换为MessagePack格式

    Args:
        pickle_path: pickle文件路径
        msgpack_path: 输出的MessagePack文件路径
        compress: 是否压缩
    """
    # 加载pickle
    from utils.compression import load_with_auto_detect
    data = load_with_auto_detect(pickle_path)

    # 保存为MessagePack
    if compress:
        MsgPackSerializer.dump_compressed(data, msgpack_path, compress=True)
    else:
        MsgPackSerializer.dump(data, msgpack_path)

    print(f"✅ 已转换: {pickle_path} -> {msgpack_path}")
