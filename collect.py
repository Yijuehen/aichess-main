"""自我对弈收集数据 - 只保存到训练缓冲区"""
import random
from collections import deque
import copy
import os
import pickle
import time
import traceback
import logging
from datetime import datetime
from game import Board, Game, move_action2move_id, move_id2move_action, flip_map
from mcts import MCTSPlayer
from config import CONFIG

if CONFIG['use_redis']:
    import my_redis, redis

import zip_array

if CONFIG['use_frame'] == 'paddle':
    from paddle_net import PolicyValueNet
elif CONFIG['use_frame'] == 'pytorch':
    from pytorch_net import PolicyValueNet
else:
    print('暂不支持您选择的框架')


# 定义整个对弈收集数据流程
class CollectPipeline:

    def __init__(self, init_model=None):
        # 象棋逻辑和棋盘
        self.board = Board()
        self.game = Game(self.board)
        # 对弈参数
        self.temp = 1  # 温度
        self.n_playout = CONFIG['play_out']  # 每次移动的模拟次数
        self.c_puct = CONFIG['c_puct']  # u的权重
        self.buffer_size = CONFIG['buffer_size']  # 经验池大小
        self.data_buffer = deque(maxlen=self.buffer_size)
        self.iters = 0

        if CONFIG['use_redis']:
            self.redis_cli = my_redis.get_redis_cli()

    # 从主体加载模型
    def load_model(self):
        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - [%(levelname)s] - %(message)s'
        )

        # 确定模型路径
        if CONFIG['use_frame'] == 'paddle':
            model_path = CONFIG['paddle_model_path']
        elif CONFIG['use_frame'] == 'pytorch':
            model_path = CONFIG['pytorch_model_path']
        else:
            raise ValueError(f'暂不支持所选框架: {CONFIG["use_frame"]}')

        # 尝试加载已有模型
        try:
            self.policy_value_net = PolicyValueNet(model_file=model_path)
            logging.info(f'✅ 已加载最新模型: {model_path}')
            logging.info(f'使用设备: {self.policy_value_net.device}')
        except FileNotFoundError as e:
            logging.warning(f'⚠️  模型文件不存在: {model_path}')
            logging.warning(f'错误详情: {e}')
            logging.info(f'创建新模型...')
            self.policy_value_net = PolicyValueNet()
            logging.info(f'使用设备: {self.policy_value_net.device}')
        except Exception as e:
            logging.error(f'❌ 模型加载失败: {e}')
            logging.error(traceback.format_exc())
            raise  # 重新抛出异常，让调用者知道失败

        # 初始化MCTS
        self.mcts_player = MCTSPlayer(self.policy_value_net.policy_value_fn,
                                      c_puct=self.c_puct,
                                      n_playout=self.n_playout,
                                      is_selfplay=1)
        logging.info(f'MCTS已初始化: c_puct={self.c_puct}, n_playout={self.n_playout}')

    def get_equi_data(self, play_data):
        """左右对称变换，扩充数据集一倍，加速一倍训练速度"""
        extend_data = []
        # 棋盘状态shape is [9, 10, 9], 走子概率，赢家
        for state, mcts_prob, winner in play_data:
            # 原始数据
            extend_data.append(zip_array.zip_state_mcts_prob((state, mcts_prob, winner)))
            # 水平翻转后的数据
            state_flip = state.transpose([1, 2, 0])
            state = state.transpose([1, 2, 0])
            for i in range(10):
                for j in range(9):
                    state_flip[i][j] = state[i][8 - j]
            state_flip = state_flip.transpose([2, 0, 1])
            mcts_prob_flip = copy.deepcopy(mcts_prob)
            for i in range(len(mcts_prob_flip)):
                mcts_prob_flip[i] = mcts_prob[move_action2move_id[flip_map(move_id2move_action[i])]]
            extend_data.append(zip_array.zip_state_mcts_prob((state_flip, mcts_prob_flip, winner)))
        return extend_data

    def collect_selfplay_data(self, n_games=1):
        """收集自我对弈的数据 - 只保存到训练缓冲区"""
        for i in range(n_games):
            print(f"\n{'='*60}", flush=True)
            print(f"🎮 Game {i+1}/{n_games} starting...", flush=True)
            print(f"{'='*60}", flush=True)

            self.load_model()  # 从本体处加载最新模型

            print(f"🔄 正在进行自我对弈 (MCTS模拟: {self.n_playout}次/步)...", flush=True)
            winner, play_data = self.game.start_self_play(self.mcts_player, temp=self.temp, is_shown=False)
            play_data = list(play_data)[:]
            episode_len = len(play_data)
            self.episode_len = episode_len  # 保存为实例属性供run()使用

            print(f"✅ Game completed!", flush=True)
            print(f"    胜者: {'黑方' if winner == -1 else '红方' if winner == 1 else '平局'}", flush=True)
            print(f"    步数: {episode_len}", flush=True)
            print(f"    时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

            # 增加数据 - 左右对称扩充
            print(f"🔄 正在扩展数据...", flush=True)
            play_data_extended = self.get_equi_data(play_data)
            print(f"    扩展后样本数: {len(play_data_extended)}", flush=True)

            # 保存到训练缓冲区
            if CONFIG['use_redis']:
                print(f"💾 正在保存到Redis...", flush=True)
                while True:
                    try:
                        for d in play_data_extended:
                            self.redis_cli.rpush('train_data_buffer', pickle.dumps(d))
                        self.redis_cli.incr('iters')
                        self.iters = int(self.redis_cli.get('iters'))
                        print(f"✅ Redis已更新! 总局数: {self.iters}", flush=True)
                        break
                    except Exception as e:
                        print(f"❌ Redis保存失败: {e}", flush=True)
                        time.sleep(1)
            else:
                # Load existing buffer
                if os.path.exists(CONFIG['train_data_buffer_path']):
                    try:
                        with open(CONFIG['train_data_buffer_path'], 'rb') as data_dict:
                            data_file = pickle.load(data_dict)
                            self.data_buffer = deque(maxlen=self.buffer_size)
                            self.data_buffer.extend(data_file['data_buffer'])
                            self.iters = data_file['iters']
                            del data_file
                    except Exception as e:
                        print(f"[!] Failed to load existing buffer: {e}")
                        self.iters = 0

                # Add new data
                self.data_buffer.extend(play_data_extended)
                self.iters += 1

                # Save combined buffer
                print(f"💾 正在保存到文件...", flush=True)
                data_dict = {'data_buffer': list(self.data_buffer), 'iters': self.iters}
                try:
                    with open(CONFIG['train_data_buffer_path'], 'wb') as data_file:
                        pickle.dump(data_dict, data_file)
                    print(f"✅ 文件已更新! 总样本数: {len(self.data_buffer)}, 总局数: {self.iters}", flush=True)
                except Exception as e:
                    print(f"❌ 保存文件失败: {e}", flush=True)

            print(f"{'='*60}\n", flush=True)

        return self.iters

    def run(self):
        """开始收集数据"""
        # 配置日志 - 同时输出到文件和控制台
        log_file = f'collect_{os.getpid()}.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - [%(levelname)s] - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

        try:
            logging.info('=' * 60)
            logging.info('开始自我对弈数据收集')
            logging.info(f'配置: buffer_size={self.buffer_size}, temp={self.temp}, n_playout={self.n_playout}')
            logging.info(f'日志文件: {log_file}')
            logging.info('=' * 60)

            iteration = 0
            while True:
                try:
                    iters = self.collect_selfplay_data()
                    iteration += 1
                    logging.info(f'✅ 第 {iters} 局完成 | 本局步数: {self.episode_len} | 总迭代: {iteration}')

                except Exception as game_error:
                    logging.error(f'❌ 自我对弈失败 (第{iteration}次迭代): {game_error}')
                    logging.error(traceback.format_exc())
                    logging.info(f'等待5秒后重试...')
                    time.sleep(5)
                    continue

        except KeyboardInterrupt:
            logging.info('')
            logging.info('=' * 60)
            logging.info('收到停止信号，正在退出...')
            logging.info('=' * 60)
        except Exception as e:
            logging.critical(f'💥 致命错误: {e}')
            logging.critical(traceback.format_exc())
            raise


if CONFIG['use_frame'] == 'paddle':
    collecting_pipeline = CollectPipeline(init_model=CONFIG['paddle_model_path'])
    collecting_pipeline.run()
elif CONFIG['use_frame'] == 'pytorch':
    collecting_pipeline = CollectPipeline(init_model=CONFIG['pytorch_model_path'])
    collecting_pipeline.run()
else:
    print('暂不支持您选择的框架')
    print('训练结束')
