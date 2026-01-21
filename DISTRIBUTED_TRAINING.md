# 多GPU分布式训练使用说明

## 快速开始

### Linux/Mac
```bash
# 直接运行启动脚本
bash aichess-main/run_distributed_train.sh
```

### Windows
```cmd
# 直接运行启动脚本
aichess-main\run_distributed_train.bat
```

## 手动启动（高级用法）

### 使用所有可用GPU
```bash
# 自动检测GPU数量
NUM_GPUS=$(python -c "import torch; print(torch.cuda.device_count())")

python -m torch.distributed.launch \
    --nproc_per_node=$NUM_GPUS \
    aichess-main/train.py
```

### 指定特定GPU
```bash
# 只使用GPU 0和GPU 1
export CUDA_VISIBLE_DEVICES=0,1
python -m torch.distributed.launch \
    --nproc_per_node=2 \
    aichess-main/train.py
```

## 环境变量说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `DISTIBUTED_TRAINING` | 启用分布式训练 | `false` |
| `WORLD_SIZE` | GPU数量 | 自动检测 |
| `MASTER_ADDR` | 主节点地址 | `localhost` |
| `MASTER_PORT` | 主节点端口 | `29500` |
| `RANK` | 进程rank（自动设置） | - |
| `LOCAL_RANK` | 本地rank（自动设置） | - |

## 性能优化建议

### 1. Batch Size调整
```python
# 在config.py中调整
'batch_size': 512 * num_gpus  # 4个GPU则设置为2048
```

### 2. 数据加载优化
```python
# 使用Redis可以加速数据共享
'use_redis': True
```

### 3. GPU内存优化
如果遇到GPU内存不足，可以：
- 减少`batch_size`
- 减少`epochs`
- 减少`buffer_size`

## 故障排查

### 问题1：NCCL错误
```
RuntimeError: NCCL error in: ...
```
**解决方案**：
- 检查CUDA_VISIBLE_DEVICES是否正确
- 确保所有GPU可见
- 尝试使用不同的backend：`gloo`代替`nccl`

### 问题2：进程初始化失败
```
RuntimeError: Address already in use
```
**解决方案**：
- 更改MASTER_PORT：`export MASTER_PORT=29501`
- 检查是否有其他训练进程在运行

### 问题3：数据加载缓慢
```
已载入数据 (等待很久)
```
**解决方案**：
- 使用Redis：`'use_redis': True`
- 将数据放在SSD上
- 增加数据预加载

## 性能监控

### 查看GPU使用情况
```bash
# Linux
watch -n 1 nvidia-smi

# Windows (需要在任务管理器中查看GPU)
```

### 查看训练进度
- Rank 0会打印训练信息
- 其他进程静默运行
- 模型只在Rank 0保存

## 预期性能提升

| GPU数量 | 训练速度加速 | 内存占用 |
|--------|------------|---------|
| 1 GPU  | 1.0x (基准) | 100% |
| 2 GPU  | 1.7-1.9x   | 200% |
| 4 GPU  | 3.2-3.6x   | 400% |
| 8 GPU  | 6.0-7.0x   | 800% |

注意：实际加速比取决于：
- GPU型号和数量
- 数据加载速度
- 网络带宽（多机训练时）
- Batch size大小
