#!/bin/bash
# 从文件导入训练数据到Redis

echo "========================================"
echo "📥 导入数据到Redis"
echo "========================================"
echo ""

# 检查参数
if [ -z "$1" ]; then
    echo "用法: ./import_redis_data.sh <文件名>"
    echo ""
    echo "示例:"
    echo "  ./import_redis_data.sh exports/train_data_backup_20260122_120000.pkl"
    echo ""
    echo "可用文件:"
    ls -lh exports/*.pkl 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
    exit 1
fi

export_file="$1"

# 检查文件是否存在
if [ ! -f "$export_file" ]; then
    echo "❌ 文件不存在: $export_file"
    exit 1
fi

# 检查Redis是否运行
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis未运行！"
    echo "请先启动Redis: sudo systemctl start redis"
    exit 1
fi

# 显示文件信息
echo "📄 文件信息:"
echo "  文件: $export_file"
size=$(du -h "$export_file" | cut -f1)
echo "  大小: $size"
echo ""

# 询问是否清空现有数据
echo "⚠️  注意：导入将添加到现有数据"
read -p "是否继续? (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消"
    exit 0
fi

echo ""
echo "📦 开始导入..."

# 创建临时Python脚本进行导入
cat > /tmp/import_redis.py << 'EOF'
import pickle
import sys
import redis
from tqdm import tqdm

# 连接Redis
r = redis.Redis(host='localhost', port=6379, db=0)

try:
    # 读取文件
    print(f"读取文件: {sys.argv[1]}")
    with open(sys.argv[1], 'rb') as f:
        data = pickle.load(f)

    print(f"样本数: {len(data)}")

    if len(data) == 0:
        print("⚠️  文件中没有数据！")
        sys.exit(1)

    # 获取当前Redis数据量
    current_count = r.llen('train_data_buffer')
    print(f"当前Redis样本数: {current_count}")

    # 导入数据到Redis
    print("正在导入数据...")
    batch_size = 100

    with tqdm(total=len(data), desc="导入进度") as pbar:
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            pipe = r.pipeline()
            for item in batch:
                pipe.rpush('train_data_buffer', pickle.dumps(item))
            pipe.execute()
            pbar.update(len(batch))

    # 更新局数（如果需要）
    # 注意：这里只是简单的累加，可能不准确
    games_added = len(data) // 90  # 假设每局约90个样本
    current_iters = int(r.get('iters') or 0)
    new_iters = current_iters + games_added
    r.set('iters', new_iters)

    print(f"\n✅ 导入完成！")
    print(f"导入样本数: {len(data)}")
    print(f"更新游戏局数: {current_iters} → {new_iters}")

except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

# 执行导入
/root/miniconda3/bin/python /tmp/import_redis.py "$export_file"

# 清理临时脚本
rm /tmp/import_redis.py

echo ""
echo "========================================"
echo "导入完成！"
echo "========================================"
echo ""

# 显示新的Redis状态
echo "📊 更新后的Redis状态:"
iters=$(redis-cli GET iters 2>/dev/null || echo "0")
samples=$(redis-cli LLEN train_data_buffer 2>/dev/null || echo "0")
echo "  游戏局数: $iters"
echo "  训练样本: $samples"

echo ""
echo "========================================"
