import pickle
from config import CONFIG
import redis

# 序列化工具 - MessagePack优化
from utils.msgpack_serializer import MsgPackSerializer, load_with_auto_detect


def get_redis_cli():
    r = redis.StrictRedis(host=CONFIG['redis_host'], port=CONFIG['redis_port'], db=CONFIG['redis_db'])
    return r


def get_list_range(redis_cli, name, l, r=-1):
    """
    从Redis获取列表数据 - 支持MessagePack和pickle自动检测

    Args:
        redis_cli: Redis客户端实例
        name: 列表键名
        l: 起始索引
        r: 结束索引 (-1表示到末尾)

    Returns:
        反序列化后的数据列表
    """
    assert isinstance(redis_cli, redis.Redis)
    data_list = redis_cli.lrange(name, l, r)

    # 根据配置选择反序列化方法
    redis_format = CONFIG['serialization'].get('redis_format', 'pickle')
    compress = CONFIG['serialization'].get('compress', False)

    if redis_format == 'msgpack':
        # 尝试MessagePack格式
        result = []
        for d in data_list:
            try:
                data = MsgPackSerializer.loads(d)
                result.append(data)
            except Exception:
                # 尝试解压后的MessagePack
                try:
                    import gzip
                    data = gzip.decompress(d)
                    result.append(MsgPackSerializer.loads(data))
                except Exception:
                    # 回退到pickle (兼容旧数据)
                    result.append(pickle.loads(d))
        return result
    else:
        # 使用pickle
        return [pickle.loads(d) for d in data_list]

if __name__ == '__main__':
    """
    导出训练数据到Redis
    自动检测pickle/msgpack格式
    """
    r = get_redis_cli()

    # 使用自动检测加载 (支持pickle和msgpack)
    data_file = load_with_auto_detect(CONFIG['train_data_buffer_path'])
    data_buffer = data_file['data_buffer']

    print(f"✅ 已加载数据: {len(data_buffer)} 样本")
    print(f"📤 正在导出到Redis...")

    # 根据配置选择序列化格式
    redis_format = CONFIG['serialization'].get('redis_format', 'pickle')
    compress = CONFIG['serialization'].get('compress', False)

    for d in data_buffer:
        if redis_format == 'msgpack':
            data = MsgPackSerializer.dumps(d)
            if compress:
                import gzip
                data = gzip.compress(data)
            r.rpush('train_data_buffer', data)
        else:
            r.rpush('train_data_buffer', pickle.dumps(d))

    print(f"✅ 已完成! 格式: {redis_format}, 压缩: {compress}")
