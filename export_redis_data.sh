#!/bin/bash
# 导出Redis训练数据到文件

echo "========================================"
echo "💾 导出Redis数据到文件"
echo "========================================"
echo ""

# 检查Redis是否运行
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis未运行！"
    echo "请先启动Redis: sudo systemctl start redis"
    exit 1
fi

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 获取当前数据统计
echo "📊 当前Redis数据状态:"
iters=$(redis-cli GET iters 2>/dev/null || echo "0")
samples=$(redis-cli LLEN train_data_buffer 2>/dev/null || echo "0")
echo "  游戏局数: $iters"
echo "  训练样本: $samples"
echo ""

# 生成导出文件名（带时间戳）
timestamp=$(date '+%Y%m%d_%H%M%S')
export_file="train_data_backup_${timestamp}.pkl"
export_dir="exports"

# 创建导出目录
mkdir -p "$export_dir"

echo "📦 开始导出..."
echo "  目标文件: $export_dir/$export_file"
echo ""

# 创建临时Python脚本进行导出
cat > /tmp/export_redis.py << 'EOF'
import pickle
import sys
import redis
from tqdm import tqdm

# 连接Redis
r = redis.Redis(host='localhost', port=6379, db=0)

try:
    # 获取数据总数
    total = r.llen('train_data_buffer')
    print(f"总样本数: {total}")

    if total == 0:
        print("⚠️  没有数据可导出！")
        sys.exit(1)

    # 批量导出数据
    print("正在导出数据...")
    data = []
    batch_size = 1000

    with tqdm(total=total, desc="导出进度") as pbar:
        for i in range(0, total, batch_size):
            batch = r.lrange('train_data_buffer', i, i + batch_size - 1)
            # 反序列化
            for item in batch:
                data.append(pickle.loads(item))
            pbar.update(len(batch))

    # 保存到文件
    with open(sys.argv[1], 'wb') as f:
        pickle.dump(data, f)

    print(f"\n✅ 导出完成！")
    print(f"文件: {sys.argv[1]}")
    print(f"样本数: {len(data)}")

except Exception as e:
    print(f"❌ 导出失败: {e}")
    sys.exit(1)
EOF

# 执行导出
/root/miniconda3/bin/python /tmp/export_redis.py "$export_dir/$export_file"

# 清理临时脚本
rm /tmp/export_redis.py

echo ""
echo "========================================"
echo "导出完成！"
echo "========================================"
echo ""
echo "文件位置: $export_dir/$export_file"

# 显示文件大小
if [ -f "$export_dir/$export_file" ]; then
    size=$(du -h "$export_dir/$export_file" | cut -f1)
    echo "文件大小: $size"
    echo ""
    echo "使用方法:"
    echo "  python -c \"import pickle; data = pickle.load(open('$export_dir/$export_file', 'rb')); print(f'样本数: {len(data)}')\""
else
    echo "⚠️  文件未创建"
fi

echo ""
echo "========================================"
