# GPU负载均衡脚本

本目录包含GPU负载均衡系统的管理和控制脚本。

## 📋 脚本列表

### GPU监控
- **start_gpu_monitor.sh** - 启动GPU监控守护进程
- **stop_gpu_monitor.sh** - 停止GPU监控守护进程

### 负载均衡
- **start_balance_daemon.sh** - 启动负载均衡守护进程
- **stop_balance_daemon.sh** - 停止负载均衡守护进程

### 环境配置
- **gpu_balance_env.sh** - GPU分配环境脚本（由其他脚本调用）

## 🚀 快速开始

### 1. 启动GPU监控（必需）
```bash
./scripts/start_gpu_monitor.sh
```

这会启动GPU监控守护进程，定期收集GPU指标并发布到Redis。

### 2. 启动负载均衡（可选）
```bash
./scripts/start_balance_daemon.sh
```

这会启动负载均衡守护进程，自动检测和纠正GPU负载不均衡。

### 3. 运行数据收集
```bash
export GPU_BALANCING_ENABLED=true
./run_parallel_collect.sh
```

启用GPU负载均衡后，数据收集进程会使用智能GPU分配。

### 4. 停止监控
```bash
# 停止负载均衡
./scripts/stop_balance_daemon.sh

# 停止GPU监控
./scripts/stop_gpu_monitor.sh
```

## 🔧 环境变量

### GPU负载均衡控制
```bash
# 启用GPU负载均衡
export GPU_BALANCING_ENABLED=true

# 禁用GPU负载均衡（使用静态检测）
export GPU_BALANCING_ENABLED=false
```

### 负载均衡配置
```bash
# 负载均衡检查间隔（秒）
export BALANCE_INTERVAL=60

# 平衡策略
export BALANCE_STRATEGY=no_migration  # 推荐，安全
# 或
export BALANCE_STRATEGY=process_migration  # 可选，高级

# 启用进程迁移（谨慎使用）
export ENABLE_MIGRATION=false
```

### GPU阈值配置
```bash
# 最小GPU内存（MB）
export MIN_GPU_MEMORY=2000

# 最大GPU利用率（%）
export MAX_GPU_UTIL=90

# GPU利用率阈值
export UTIL_LOW=50.0      # 空闲阈值
export UTIL_HIGH=85.0     # 过载阈值

# 最大GPU温度（°C）
export MAX_GPU_TEMP=85

# 启用自适应阈值
export ADAPTIVE_THRESHOLDS=true
```

## 📊 日志文件

所有守护进程的日志都存储在项目根目录：

- `gpu_monitor.log` - GPU监控日志
- `balance_daemon.log` - 负载均衡日志

查看日志：
```bash
tail -f gpu_monitor.log
tail -f balance_daemon.log
```

## 🔍 进程管理

### 查看PID文件
```bash
cat gpu_monitor.pid      # GPU监控进程ID
cat balance_daemon.pid   # 负载均衡进程ID
```

### 检查进程状态
```bash
ps -p $(cat gpu_monitor.pid)
ps -p $(cat balance_daemon.pid)
```

## 🧪 测试脚本

项目根目录下的测试脚本：

```bash
# 测试GPU监控
python test_gpu_monitor.py

# 测试任务调度
python test_task_scheduler.py

# 测试负载均衡
python test_load_balancer.py

# 测试自适应优化
python test_adaptive.py
```

## 📖 更多信息

查看项目根目录下的文档：
- README.md - 项目总览
- README_SCRIPTS.md - 脚本使用说明

## ⚠️ 注意事项

1. **Redis依赖**：所有功能都需要Redis运行
2. **nvidia-smi依赖**：需要nvidia-smi命令来获取GPU状态
3. **进程迁移**：默认禁用，仅在有充分了解时启用
4. **优雅停止**：使用stop脚本而不是kill -9，以确保数据正确保存

## 🐛 故障排除

### GPU监控无法启动
```bash
# 检查Redis
redis-cli ping

# 检查nvidia-smi
nvidia-smi

# 查看日志
tail gpu_monitor.log
```

### GPU分配失败
```bash
# 检查GPU监控是否运行
ps -p $(cat gpu_monitor.pid)

# 检查Redis中的GPU指标
redis-cli KEYS "gpu:metrics:*"

# 查看可用GPU
redis-cli SMEMBERS gpu:available
```

### 负载均衡不工作
```bash
# 查看守护进程状态
ps -p $(cat balance_daemon.pid)

# 查看负载均衡日志
tail balance_daemon.log

# 检查Redis标志
redis-cli SMEMBERS gpu:paused_new_tasks
redis-cli SMEMBERS gpu:preferred_for_new_tasks
```
