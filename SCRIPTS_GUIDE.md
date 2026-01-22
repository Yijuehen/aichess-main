# 数据收集脚本使用指南

## 📁 脚本文件说明

### 主要脚本
- **run_parallel_collect.sh** - 多GPU并行数据收集（智能GPU检测）
- **run_distributed_train.sh** - 多GPU分布式训练

### 辅助脚本
- **start_collect.sh** - 快速启动collect
- **stop_collect.sh** - 停止collect
- **monitor.sh** - 实时监控collect状态
- **export_redis_data.sh** - 导出Redis数据到 train_data_buffer.pkl（备份）

---

## 🚀 快速开始

### 1. 启动数据收集

```bash
cd /tmp/aichess-main
./start_collect.sh
```

**输出示例**：
```
========================================
🚀 启动Collect数据收集
========================================

✅ Redis运行正常

启动collect...

✅ Collect已启动！

进程ID: 12345
日志文件: nohup_collect.log

常用命令:
  查看日志: tail -f nohup_collect.log
  查看进度: redis-cli GET iters
  监控状态: ./monitor.sh
  停止程序: ./stop_collect.sh
========================================
```

---

### 2. 监控运行状态

```bash
./monitor.sh
```

**显示内容**：
- ✅ 进程状态（PID、CPU、内存）
- 📊 数据进度（游戏局数、训练样本数）
- 📈 进度条（目标5000局）
- 🎮 GPU状态（利用率、显存使用）
- 📝 最新日志

**按 Ctrl+C 退出监控（不影响collect运行）**

---

### 3. 查看实时日志

```bash
tail -f nohup_collect.log
```

**按 Ctrl+C 退出日志查看**

---

### 4. 停止数据收集

```bash
./stop_collect.sh
```

**输出示例**：
```
========================================
🛑 停止Collect
========================================

停止进程: 12345
✅ 已停止

验证:
✅ 所有进程已停止

数据状态:
  已收集局数: 28
  训练样本数: 2520
========================================
```

---

## 📊 常用命令

### 查看收集进度

```bash
# 查看游戏局数
redis-cli GET iters

# 查看训练样本数
redis-cli LLEN train_data_buffer

# 查看进程状态
ps aux | grep collect.py | grep -v grep

# 查看GPU使用
nvidia-smi
```

---

### 后台运行

脚本已经使用 `nohup` 后台运行，可以安全退出SSH：

```bash
# 启动
./start_collect.sh

# 退出SSH
exit
# 程序继续运行！

# 下次登录查看
ssh user@server
cd /tmp/aichess-main
./monitor.sh
```

---

## 🔄 完整工作流程

### 阶段1：数据收集（冷启动）

```bash
# 启动collect
./start_collect.sh

# 监控进度
./monitor.sh

# 等待收集500-1000局（可通过redis-cli GET iters查看）
```

### 阶段2：开始训练

达到目标局数后，切换到一收集一训练模式：

```bash
# 终端1：继续收集
CUDA_VISIBLE_DEVICES=0 python collect.py

# 终端2：训练模型
CUDA_VISIBLE_DEVICES=1 python train.py
```

---

## ⚠️ 注意事项

### 1. Redis必须运行

启动collect前确保Redis运行：

```bash
# 检查Redis
redis-cli ping
# 应该返回: PONG

# 如果没运行，启动Redis
sudo systemctl start redis
```

### 2. GPU内存要求

- 最低空闲内存：2GB
- 最低GPU利用率：<90%

脚本会自动检测并只使用符合条件的GPU。

### 3. 数据存储

- ✅ 数据保存在Redis内存中
- ✅ 最大保留100,000个样本
- ✅ 超限后自动删除旧数据（循环使用）
- ✅ 不会爆内存

### 4. 模型文件

- ⚠️ 模型文件路径：`models/current_policy100.pkl`
- ⚠️ 如果模型不存在，会创建随机初始化的新模型
- 💡 建议先收集数据，再开始训练

---

## 📈 预期性能

| GPU数量 | 收集速度 | 预计时间（1000局） |
|---------|---------|-------------------|
| 1 GPU   | 1.0x    | ~8小时            |
| 2 GPU   | 1.8x    | ~4.5小时          |
| 4 GPU   | 3.5x    | ~2.5小时          |

---

## 🐛 故障排查

### 问题1：Redis连接失败

```
Error: Error connecting to Redis
```

**解决方案**：
```bash
sudo systemctl start redis
redis-cli ping
```

### 问题2：GPU内存不足

```
CUDA out of memory
```

**解决方案**：
- 减少collect进程数量
- 检查GPU使用：`nvidia-smi`

### 问题3：进程意外退出

**解决方案**：
```bash
# 查看日志
tail -50 nohup_collect.log

# 查看详细日志
ls -lt collect_*.log
tail -f collect_*.log
```

---

## 💾 数据备份

### 导出Redis数据到文件

**为什么需要导出？**
- ✅ **备份重要数据** - 防止Redis重启或服务器断电导致数据丢失
- ✅ **持久化存储** - 数据保存在磁盘文件中
- ✅ **可迁移** - 可以在其他机器上使用这些数据

#### 导出命令

```bash
./export_redis_data.sh
```

**输出示例**：
```
========================================
💾 导出Redis数据到 train_data_buffer.pkl
========================================

📊 当前Redis数据状态:
  游戏局数: 500
  训练样本: 45000

📦 开始导出...
  目标文件: train_data_buffer.pkl

总样本数: 45000
导出进度: 100%|████████████████████| 45000/45000

✅ 导出完成！
文件: train_data_buffer.pkl
样本数: 45000

========================================
导出完成！
========================================

文件位置: train_data_buffer.pkl
文件大小: 500M

✅ 数据已备份，可以防止Redis重启丢失
========================================
```

#### 导出说明

- **固定文件名**: `train_data_buffer.pkl`（每次导出覆盖）
- **存储位置**: `/tmp/aichess-main/train_data_buffer.pkl`
- **数据格式**: 与Redis中相同的pickle格式
- **覆盖策略**: 每次导出会覆盖旧文件（保持最新备份）

#### 查看备份文件

```bash
# 查看文件信息
ls -lh train_data_buffer.pkl

# 查看文件大小
du -h train_data_buffer.pkl

# 验证文件内容
python -c "import pickle; data = pickle.load(open('train_data_buffer.pkl', 'rb')); print(f'样本数: {len(data)}')"
```

---

### 定期备份建议

#### 每天自动备份（推荐）

```bash
# 添加到crontab
crontab -e

# 每天凌晨2点备份Redis数据
0 2 * * * cd /tmp/aichess-main && ./export_redis_data.sh >> export.log 2>&1
```

#### 手动定期备份

```bash
# 每达到一定局数后备份
iters=$(redis-cli GET iters)
if [ "$iters" -gt 1000 ]; then
    echo "达到1000局，正在备份..."
    ./export_redis_data.sh
fi

# 或者每周备份一次
./export_redis_data.sh
```

#### 收集完成后备份

```bash
# 停止collect
./stop_collect.sh

# 备份最新数据
./export_redis_data.sh

# 安全重启服务器
sudo reboot
```

---

### 数据恢复（如果需要）

如果Redis数据丢失，可以从备份文件恢复：

```bash
# 方法1：临时恢复（推荐）
# 启动collect前，先从文件加载数据到Redis
# 修改 collect.py 或 train.py 的启动逻辑

# 方法2：手动恢复（高级用户）
# 使用Redis的批量导入功能
# 需要编写简单的导入脚本
```

---

## 📝 总结

| 任务 | 命令 |
|------|------|
| **启动** | `./start_collect.sh` |
| **监控** | `./monitor.sh` |
| **查看日志** | `tail -f nohup_collect.log` |
| **查看进度** | `redis-cli GET iters` |
| **停止** | `./stop_collect.sh` |
| **导出备份** | `./export_redis_data.sh` |

**简单、可靠、自动化！** 🎯
