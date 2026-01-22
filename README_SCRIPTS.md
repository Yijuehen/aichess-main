# 📚 脚本文件说明

## 🎯 快速开始

上传这些文件到服务器 `/tmp/aichess-main/` 目录：

### 必须文件
1. ✅ collect.py - 数据收集主程序
2. ✅ config.py - 配置文件
3. ✅ train.py - 训练程序
4. ✅ run_parallel_collect.sh - 多GPU并行收集（主要）
5. ✅ run_distributed_train.sh - 多GPU训练

### 辅助脚本（推荐）
6. ✅ start_collect.sh - 快速启动
7. ✅ stop_collect.sh - 快速停止
8. ✅ monitor.sh - 实时监控
9. ✅ export_redis_data.sh - 导出Redis数据
10. ✅ import_redis_data.sh - 导入Redis数据

### 文档
11. ✅ SCRIPTS_GUIDE.md - 详细使用指南

---

## 📖 脚本功能一览

| 脚本 | 功能 | 何时使用 |
|------|------|----------|
| **start_collect.sh** | 启动collect | 每次启动数据收集 |
| **stop_collect.sh** | 停止collect | 停止数据收集 |
| **monitor.sh** | 实时监控 | 查看收集进度和状态 |
| **export_redis_data.sh** | 导出数据 | 备份Redis数据到文件 |
| **import_redis_data.sh** | 导入数据 | 从文件恢复数据到Redis |
| **run_parallel_collect.sh** | 主收集脚本 | 由start_collect调用 |
| **run_distributed_train.sh** | 训练脚本 | 训练模型时使用 |

---

## 🚀 最简单的使用流程

```bash
# 1. 上传文件到服务器
scp *.sh *.py user@server:/tmp/aichess-main/

# 2. SSH登录服务器
ssh user@server

# 3. 进入目录
cd /tmp/aichess-main

# 4. 添加执行权限
chmod +x *.sh

# 5. 启动数据收集
./start_collect.sh

# 6. 监控进度（另开终端）
./monitor.sh

# 7. 退出SSH，程序继续运行
exit

# 8. 下次登录查看
ssh user@server
cd /tmp/aichess-main
./monitor.sh
```

---

## 💾 数据管理

### 导出数据（备份）

```bash
# 导出当前Redis数据到文件
./export_redis_data.sh

# 文件保存在 exports/ 目录
ls -lh exports/
```

### 导入数据（恢复）

```bash
# 从文件导入到Redis
./import_redis_data.sh exports/train_data_backup_20260122_120000.pkl
```

---

## 📊 监控脚本输出示例

```
========================================
📊 Collect监控 - 2026-01-22 12:45:30
========================================

🖥️  进程状态:
   ✅ 运行中
   PID: 80549, CPU: 98%, MEM: 0.1%, 运行时间: 05:30

📈 数据进度:
   游戏局数: 28
   训练样本: 2520
   进度: 0% (目标: 5000局)

🎮 GPU状态:
   GPU 0: NVIDIA A100-SXM4-80GB - 利用率 23%, 显存 706M/81920M
   GPU 1: NVIDIA A100-SXM4-80GB - 利用率 20%, 显存 696M/81920M

📝 最新日志（最后3行）:
✅ Game completed! 胜者: 平局, 步数: 47
✅ Redis已更新! 总局数: 28
🎮 Game 2/1 starting...

========================================
```

---

## 🛑 停止脚本输出示例

```
========================================
🛑 停止Collect
========================================

停止进程: 80549
✅ 已停止

验证:
✅ 所有进程已停止

数据状态:
  已收集局数: 28
  训练样本数: 2520

========================================
```

---

## ⚙️ 配置说明

### 修改GPU检测参数

编辑 `run_parallel_collect.sh`:

```bash
MIN_GPU_MEMORY_MB=2000  # 最小需要GPU内存（MB）
MAX_GPU_UTIL=90         # 最大GPU利用率（%）
```

### 修改Redis配置

编辑 `config.py`:

```python
'use_redis': True,  # 使用Redis存储
'redis_host': 'localhost',
'redis_port': 6379,
```

---

## 📝 常用命令速查

```bash
# === 基本操作 ===
./start_collect.sh           # 启动
./stop_collect.sh            # 停止
./monitor.sh                 # 监控

# === 查看状态 ===
redis-cli GET iters          # 查看局数
redis-cli LLEN train_data_buffer  # 查看样本数
ps aux | grep collect.py     # 查看进程
nvidia-smi                   # 查看GPU

# === 日志 ===
tail -f nohup_collect.log    # 实时日志
tail -50 nohup_collect.log   # 最近50行

# === 数据管理 ===
./export_redis_data.sh       # 导出备份
./import_redis_data.sh <文件>  # 导入恢复
```

---

## 🎯 使用建议

### 初次使用（第1周）
1. 启动collect，收集500-1000局数据
2. 定期导出备份（每100局）
3. 不要急于训练

### 持续使用（第2周起）
1. 达到1000局后，开始训练
2. 同时运行collect（1个GPU）+ train（1个GPU）
3. 每天导出一次备份

### 最佳实践
- ✅ 每天备份一次数据
- ✅ 每周检查一次磁盘空间
- ✅ 达到5000局后保存模型
- ✅ 定期清理旧的备份文件

---

## 📞 获取帮助

详细使用说明请查看：
```bash
cat SCRIPTS_GUIDE.md
```

---

## 🎉 总结

**7个脚本，覆盖所有需求！**

1. ✅ **启动/停止/监控** - start/stop/monitor
2. ✅ **导出/导入** - export/import
3. ✅ **并行收集** - run_parallel_collect
4. ✅ **分布式训练** - run_distributed_train
5. ✅ **完整文档** - SCRIPTS_GUIDE.md

**简单、稳定、自动化！** 🚀
