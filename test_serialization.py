"""
序列化测试脚本 - 验证向后兼容性

测试:
1. MessagePack是否可用
2. pickle数据是否能正常加载
3. MessagePack序列化是否工作
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG
from utils.msgpack_serializer import MsgPackSerializer, load_with_auto_detect
from utils.compression import CompressedPickle
import pickle


def test_msgpack_available():
    """测试MessagePack是否可用"""
    print("=" * 60)
    print("测试1: MessagePack可用性")
    print("=" * 60)

    if MsgPackSerializer.is_available():
        print("✅ MessagePack已安装并可用")
        return True
    else:
        print("⚠️  MessagePack未安装，将使用pickle")
        print("   安装方法: pip install msgpack msgpack-numpy")
        return False


def test_pickle_compat():
    """测试pickle兼容性"""
    print("\n" + "=" * 60)
    print("测试2: Pickle向后兼容")
    print("=" * 60)

    # 创建测试数据
    test_data = {
        'data_buffer': [(1, 2, 3), (4, 5, 6)],
        'iters': 10
    }

    # 保存为pickle
    pickle_file = 'test_data.pkl'
    try:
        with open(pickle_file, 'wb') as f:
            pickle.dump(test_data, f)
        print(f"✅ 已创建测试pickle文件: {pickle_file}")

        # 使用自动检测加载
        loaded_data = load_with_auto_detect(pickle_file)
        print(f"✅ 成功加载pickle数据: {loaded_data}")

        # 验证数据一致性
        assert loaded_data == test_data, "数据不一致!"
        print("✅ Pickle数据一致性验证通过")

        return True
    except Exception as e:
        print(f"❌ Pickle兼容性测试失败: {e}")
        return False
    finally:
        # 清理
        if os.path.exists(pickle_file):
            os.remove(pickle_file)


def test_msgpack_serialize():
    """测试MessagePack序列化"""
    print("\n" + "=" * 60)
    print("测试3: MessagePack序列化")
    print("=" * 60)

    if not MsgPackSerializer.is_available():
        print("⚠️  MessagePack不可用，跳过此测试")
        return True

    # 创建测试数据 (模拟训练数据)
    test_data = {
        'data_buffer': [(1, 2, 3)] * 100,
        'iters': 100
    }

    msgpack_file = 'test_data.msgpack'
    try:
        # 保存为MessagePack
        MsgPackSerializer.dump(test_data, msgpack_file)
        file_size = os.path.getsize(msgpack_file)
        print(f"✅ 已保存MessagePack文件: {msgpack_file}")
        print(f"   文件大小: {file_size:,} bytes")

        # 加载验证
        loaded_data = MsgPackSerializer.load(msgpack_file)
        assert loaded_data['iters'] == test_data['iters'], "数据不一致!"
        print("✅ MessagePack数据一致性验证通过")

        # 对比pickle大小
        pickle_file = 'test_data.pkl'
        with open(pickle_file, 'wb') as f:
            pickle.dump(test_data, f)
        pickle_size = os.path.getsize(pickle_file)

        compression_ratio = (1 - file_size / pickle_size) * 100
        print(f"   Pickle大小: {pickle_size:,} bytes")
        print(f"   压缩率: {compression_ratio:.1f}%")

        return True
    except Exception as e:
        print(f"❌ MessagePack测试失败: {e}")
        return False
    finally:
        # 清理
        for f in [msgpack_file, 'test_data.pkl']:
            if os.path.exists(f):
                os.remove(f)


def test_existing_data():
    """测试加载现有数据文件"""
    print("\n" + "=" * 60)
    print("测试4: 现有数据文件加载")
    print("=" * 60)

    data_path = CONFIG.get('train_data_buffer_path', 'train_data_buffer.pkl')

    if not os.path.exists(data_path):
        print(f"⚠️  数据文件不存在: {data_path}")
        print("   跳过此测试 (首次运行正常)")
        return True

    try:
        print(f"📂 正在加载: {data_path}")
        data = load_with_auto_detect(data_path)

        buffer_size = len(data.get('data_buffer', []))
        iters = data.get('iters', 0)

        print(f"✅ 成功加载数据文件!")
        print(f"   样本数: {buffer_size:,}")
        print(f"   迭代数: {iters}")

        return True
    except Exception as e:
        print(f"❌ 加载现有数据失败: {e}")
        print(f"   建议检查文件是否损坏")
        return False


def test_redis_config():
    """测试Redis配置"""
    print("\n" + "=" * 60)
    print("测试5: Redis配置")
    print("=" * 60)

    print(f"Redis启用: {CONFIG.get('use_redis', False)}")

    if CONFIG.get('use_redis'):
        redis_format = CONFIG['serialization'].get('redis_format', 'pickle')
        print(f"Redis格式: {redis_format}")
        print(f"Redis地址: {CONFIG.get('redis_host')}:{CONFIG.get('redis_port')}")

        # 尝试连接
        try:
            import redis
            r = redis.StrictRedis(
                host=CONFIG['redis_host'],
                port=CONFIG['redis_port'],
                db=CONFIG['redis_db']
            )
            r.ping()
            print("✅ Redis连接成功")
            return True
        except Exception as e:
            print(f"⚠️  Redis连接失败: {e}")
            return False
    else:
        print("✅ Redis未启用 (文件模式)")
        return True


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🧪 序列化兼容性测试")
    print("=" * 60)

    results = []

    # 运行测试
    results.append(("MessagePack可用性", test_msgpack_available()))
    results.append(("Pickle兼容性", test_pickle_compat()))
    results.append(("MessagePack序列化", test_msgpack_serialize()))
    results.append(("现有数据加载", test_existing_data()))
    results.append(("Redis配置", test_redis_config()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status} - {name}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("🎉 所有测试通过! 可以开始使用MessagePack序列化了")
        print("\n下一步:")
        print("1. 导出Redis数据 (如需要): python my_redis.py")
        print("2. 重启collect: python collect.py")
        print("3. 开始训练: python train.py")
    else:
        print("⚠️  部分测试失败，请检查上述错误信息")
        print("\n建议:")
        print("1. 安装MessagePack: pip install msgpack msgpack-numpy")
        print("2. 检查config.py配置")
        print("3. 确保现有数据文件可访问")

    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
