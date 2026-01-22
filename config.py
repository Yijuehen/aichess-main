import torch
import os

CONFIG = {
    'kill_action': 30,      #和棋回合数
    'dirichlet': 0.2,       # 国际象棋，0.3；日本将棋，0.15；围棋，0.03
    'play_out': 1200,        # 每次移动的模拟次数
    'c_puct': 5,             # u的权重
    'buffer_size': 100000,   # 经验池大小
    'paddle_model_path': '../current_policy100.model',      # paddle模型路径（相对路径，指向项目根目录）
    'pytorch_model_path': '../current_policy100.pkl',   # pytorch模型路径（相对路径，指向项目根目录）
    'train_data_buffer_path': 'train_data_buffer.pkl',   # 数据容器的路径（在aichess-main目录下）
    'batch_size': 512,  # 每次更新的train_step数量
    'kl_targ': 0.02,  # kl散度控制
    'epochs' : 5,  # 每次更新的train_step数量
    'game_batch_num': 3000,  # 训练更新的次数
    'use_frame': 'pytorch',  # paddle or pytorch根据自己的环境进行切换
    'train_update_interval': 600,  #模型更新间隔时间
    'use_redis': True, # 数据存储方式（True=Redis用于并行收集，False=文件）
    'redis_host': 'localhost',
    'redis_port': 6379,
    'redis_db': 0,
    # GPU配置
    'use_gpu': True,  # 是否使用GPU
    'device': 'cuda' if torch.cuda.is_available() else 'cpu',  # 自动检测GPU

    # 分布式训练配置
    'distributed': {
        'enabled': bool(os.getenv('DISTIBUTED_TRAINING', 'False').lower() == 'true'),
        'backend': 'nccl',  # nccl for NVIDIA GPUs
        # torch.distributed.launch 会自动设置这些环境变量
        'world_size': int(os.getenv('WORLD_SIZE', os.getenv('GROUP_WORLD_SIZE', str(torch.cuda.device_count())))),
        'rank': int(os.getenv('RANK', os.getenv('GROUP_RANK', '0'))),  # 兼容 torch.distributed.launch
        'local_rank': int(os.getenv('LOCAL_RANK', '0')),  # torch.distributed.launch 自动设置
        # 构造完整的 init_method URL
        'master_addr': os.getenv('MASTER_ADDR', 'localhost'),
        'master_port': int(os.getenv('MASTER_PORT', '29500')),
        'init_method': f"tcp://{os.getenv('MASTER_ADDR', 'localhost')}:{os.getenv('MASTER_PORT', '29500')}",
    }
}