@echo off
REM 多进程并行数据收集脚本 - 智能GPU检测版本 (Windows)
REM 使用Python检测GPU状态，因为batch脚本无法直接调用nvidia-smi

setlocal enabledelayedexpansion

REM 配置区域
set MIN_GPU_MEMORY_MB=2000
set MAX_GPU_UTIL=90
set BATCH_SIZE=512

echo ==================================
echo 多进程并行数据收集（智能GPU检测）
echo ==================================
echo 最小GPU内存要求: %MIN_GPU_MEMORY_MB%MB
echo 最大GPU利用率: %MAX_GPU_UTIL%%%
echo 数据存储: Redis
echo ==================================

REM 获取脚本所在目录
set SCRIPT_DIR=%~dp0

REM 使用Python检测GPU状态
echo.
echo 正在检测GPU状态...

REM 创建临时Python检测脚本
(
echo import subprocess
echo import re
echo import os
echo import sys
echo import time
echo
echo MIN_GPU_MEMORY = 2000  # MB
echo MAX_GPU_UTIL = 90  # %%
echo
echo def check_gpu(gpu_id):
echo     try:
echo         result = subprocess.run([
echo             'nvidia-smi', '-i', str(gpu_id),
echo             '--query-gpu=memory.free,memory.total,utilization.gpu,name',
echo             '--format=csv,noheader,nounits'
echo         ], capture_output=True, text=True, timeout=5)
echo
echo         if result.returncode != 0:
echo             return False, "nvidia-smi failed"
echo
echo         parts = result.stdout.strip().split(', ')
echo         if len(parts) ^< 4:
echo             return False, "parse error"
echo
echo         mem_free = int(parts[0])
echo         mem_total = int(parts[1])
echo         gpu_util = int(parts[2])
echo         gpu_name = parts[3]
echo
echo         print(f"GPU {gpu_id}: {gpu_name}")
echo         print(f"  空闲内存: {mem_free}MB / 总计 {mem_total}MB")
echo         print(f"  利用率: {gpu_util}%%")
echo
echo         if mem_free ^< MIN_GPU_MEMORY:
echo             print(f"  X 不可用: 空闲内存不足")
echo             return False, "low memory"
echo
echo         if gpu_util ^> MAX_GPU_UTIL:
echo             print(f"  X 不可用: 利用率过高")
echo             return False, "high utilization"
echo
echo         print(f"  OK 可用")
echo         return True, "ok"
echo
echo     except Exception as e:
echo         print(f"GPU {gpu_id}: X 检测失败 - {e}")
echo         return False, str(e)
echo
echo # 检测所有GPU
echo result = subprocess.run(['nvidia-smi', '--query-gpu=count', '--format=csv,noheader,nounits'],
echo                          capture_output=True, text=True)
echo num_gpus = int(result.stdout.strip()) if result.stdout.strip() else 0
echo print(f"检测到 {num_gpus} 个GPU")
echo
echo available_gpus = []
echo for i in range(num_gpus):
echo     print()
echo     ok, reason = check_gpu(i)
echo     if ok:
echo         available_gpus.append(i)
echo
echo print()
echo print("=" * 50)
echo print(f"可用GPU数量: {len(available_gpus)}")
echo print(f"可用GPU编号: {available_gpus}")
echo
echo if len(available_gpus) == 0:
echo     print()
echo     print("X 没有可用的GPU！")
echo     print("建议:")
echo     print("  1. 降低 MIN_GPU_MEMORY_MB 要求")
echo     print("  2. 关闭其他使用GPU的程序")
echo     input("按Enter退出...")
echo     sys.exit(1)
echo
echo # 启动collect进程
echo script_dir = os.path.dirname(os.path.abspath(__file__))
echo pids = []
echo
echo print()
echo print("启动数据收集进程...")
echo print("=" * 50)
echo
echo for idx, gpu_id in enumerate(available_gpus):
echo     print(f"启动进程 {idx} 使用 GPU {gpu_id}")
echo
echo     env = os.environ.copy()
echo     env['CUDA_VISIBLE_DEVICES'] = str(gpu_id)
echo     env['DISTIBUTED_TRAINING'] = 'false'
echo
echo     log_file = os.path.join(script_dir, f'collect_{gpu_id}.log')
echo     proc = subprocess.Popen(
echo         [sys.executable, os.path.join(script_dir, 'collect.py')],
echo         env=env,
echo         stdout=open(log_file, 'w'),
echo         stderr=subprocess.STDOUT
echo     )
echo     pids.append(proc.pid)
echo     print(f"  进程ID: {proc.pid}")
echo     print(f"  日志: {log_file}")
echo     time.sleep(1)  # 延迟避免同时启动
echo
echo print()
echo print("=" * 50)
echo print("所有进程已启动！")
echo print(f"进程数量: {len(available_gpus)}")
echo print(f"进程ID: {pids}")
echo print()
echo print("监控命令:")
echo print("  查看GPU: 在任务管理器中查看")
echo print("  查看Redis: redis-cli LLEN train_data_buffer")
echo print("  查看日志: type collect_*.log")
echo print()
echo print("按Enter停止所有进程...")
echo
echo try:
echo     input()
echo except KeyboardInterrupt:
echo     pass
echo
echo print()
echo print("停止所有进程...")
echo for pid in pids:
echo     try:
echo         subprocess.run(['taskkill', '/F', '/PID', str(pid)],
echo                        capture_output=True)
echo     except:
echo         pass
echo print("所有进程已停止")
) > "%TEMP%\gpu_collect_helper.py"

python "%TEMP%\gpu_collect_helper.py"
del "%TEMP%\gpu_collect_helper.py"

echo.
echo ==================================
echo 脚本执行完成
echo ==================================
pause
