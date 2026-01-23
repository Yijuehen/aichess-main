"""
数据压缩工具 - 支持pickle + gzip/bz2/lzma

向后兼容工具类，支持多种压缩方法和自动检测
"""
import pickle
import gzip
import bz2
import lzma
from typing import Any


class CompressedPickle:
    """压缩序列化工具 - 支持向后兼容"""

    @staticmethod
    def dump(obj: Any, filepath: str, method: str = 'gzip') -> None:
        """
        保存对象到压缩文件

        Args:
            obj: 要序列化的对象
            filepath: 文件路径
            method: 压缩方法 ('gzip', 'bz2', 'lzma', 'none')
        """
        if method == 'gzip':
            with gzip.open(filepath, 'wb') as f:
                pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        elif method == 'bz2':
            with bz2.BZ2File(filepath, 'wb') as f:
                pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        elif method == 'lzma':
            with lzma.LZMAFile(filepath, 'wb') as f:
                pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        else:  # none
            with open(filepath, 'wb') as f:
                pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def load(filepath: str, method: str = 'gzip') -> Any:
        """
        从压缩文件加载对象

        Args:
            filepath: 文件路径
            method: 压缩方法 ('gzip', 'bz2', 'lzma', 'none')
        """
        if method == 'gzip':
            with gzip.open(filepath, 'rb') as f:
                return pickle.load(f)
        elif method == 'bz2':
            with bz2.BZ2File(filepath, 'rb') as f:
                return pickle.load(f)
        elif method == 'lzma':
            with lzma.LZMAFile(filepath, 'rb') as f:
                return pickle.load(f)
        else:  # none
            with open(filepath, 'rb') as f:
                return pickle.load(f)

    @staticmethod
    def dumps(obj: Any, method: str = 'gzip') -> bytes:
        """序列化为压缩字节"""
        data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        if method == 'gzip':
            import zlib
            return zlib.compress(data)
        elif method == 'bz2':
            import bz2
            return bz2.compress(data)
        elif method == 'lzma':
            import lzma
            return lzma.compress(data)
        return data

    @staticmethod
    def loads(data: bytes, method: str = 'gzip') -> Any:
        """从压缩字节反序列化"""
        if method == 'gzip':
            import zlib
            data = zlib.decompress(data)
        elif method == 'bz2':
            import bz2
            data = bz2.decompress(data)
        elif method == 'lzma':
            import lzma
            data = lzma.decompress(data)
        return pickle.loads(data)


def load_with_auto_detect(filepath: str) -> Any:
    """
    自动检测文件格式并加载
    支持格式: gzip pickle, bz2 pickle, lzma pickle, raw pickle

    Args:
        filepath: 文件路径

    Returns:
        加载的对象
    """
    # 尝试各种压缩格式
    for method in ['gzip', 'bz2', 'lzma', 'none']:
        try:
            return CompressedPickle.load(filepath, method=method)
        except Exception:
            continue

    # 如果都失败，抛出异常
    raise ValueError(f"无法识别的文件格式: {filepath}")
