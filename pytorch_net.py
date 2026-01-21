"""策略价值网络 - Inference Optimized"""


import torch
import torch.nn as nn
import numpy as np
import torch.nn.functional as F
from config import CONFIG


# 搭建残差块 - Optimized with inplace operations
class ResBlock(nn.Module):

    def __init__(self, num_filters=256):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels=num_filters, out_channels=num_filters, kernel_size=(3, 3), stride=(1, 1), padding=1)
        self.conv1_bn = nn.BatchNorm2d(num_filters, )
        self.conv1_act = nn.ReLU(inplace=True)  # In-place saves memory
        self.conv2 = nn.Conv2d(in_channels=num_filters, out_channels=num_filters, kernel_size=(3, 3), stride=(1, 1), padding=1)
        self.conv2_bn = nn.BatchNorm2d(num_filters, )
        self.conv2_act = nn.ReLU(inplace=True)

    def forward(self, x):
        y = self.conv1(x)
        y = self.conv1_bn(y)
        y = self.conv1_act(y)
        y = self.conv2(y)
        y = self.conv2_bn(y)
        y = x + y
        return self.conv2_act(y)


# 搭建骨干网络，输入：N, 9, 10, 9 --> N, C, H, W
class Net(nn.Module):

    def __init__(self, num_channels=256, num_res_blocks=7):
        super().__init__()
        # 全局特征
        # self.global_conv = nn.Conv2D(in_channels=9, out_channels=512, kernel_size=(10, 9))
        # self.global_bn = nn.BatchNorm2D(512)
        # 初始化特征
        self.conv_block = nn.Conv2d(in_channels=9, out_channels=num_channels, kernel_size=(3, 3), stride=(1, 1), padding=1)
        self.conv_block_bn = nn.BatchNorm2d(256)
        self.conv_block_act = nn.ReLU(inplace=True)
        # 残差块抽取特征
        self.res_blocks = nn.ModuleList([ResBlock(num_filters=num_channels) for _ in range(num_res_blocks)])
        # 策略头
        self.policy_conv = nn.Conv2d(in_channels=num_channels, out_channels=16, kernel_size=(1, 1), stride=(1, 1))
        self.policy_bn = nn.BatchNorm2d(16)
        self.policy_act = nn.ReLU(inplace=True)
        self.policy_fc = nn.Linear(16 * 9 * 10, 2086)
        # 价值头
        self.value_conv = nn.Conv2d(in_channels=num_channels, out_channels=8, kernel_size=(1, 1), stride=(1, 1))
        self.value_bn = nn.BatchNorm2d(8)
        self.value_act1 = nn.ReLU(inplace=True)
        self.value_fc1 = nn.Linear(8 * 9 * 10, 256)
        self.value_act2 = nn.ReLU(inplace=True)
        self.value_fc2 = nn.Linear(256, 1)

    # 定义前向传播
    def forward(self, x):
        # 公共头
        x = self.conv_block(x)
        x = self.conv_block_bn(x)
        x = self.conv_block_act(x)
        for layer in self.res_blocks:
            x = layer(x)
        # 策略头
        policy = self.policy_conv(x)
        policy = self.policy_bn(policy)
        policy = self.policy_act(policy)
        policy = torch.reshape(policy, [-1, 16 * 10 * 9])
        policy = self.policy_fc(policy)
        policy = F.log_softmax(policy, dim=1)
        # 价值头
        value = self.value_conv(x)
        value = self.value_bn(value)
        value = self.value_act1(value)
        value = torch.reshape(value, [-1, 8 * 10 * 9])
        value = self.value_fc1(value)
        value = self.value_act2(value)
        value = self.value_fc2(value)
        value = F.tanh(value)

        return policy, value


# 策略值网络 - Optimized for Inference (faster, no training needed)
class PolicyValueNet:

    def __init__(self, model_file=None, use_gpu=False, device='cpu'):
        self.use_gpu = use_gpu
        self.device = device
        self.policy_value_net = Net().to(self.device)

        # Load model if provided
        if model_file:
            self.policy_value_net.load_state_dict(torch.load(model_file, weights_only=False))

        # CRITICAL OPTIMIZATIONS FOR INFERENCE:
        # 1. Set to eval mode (disables dropout, batchnorm updates, etc.)
        self.policy_value_net.eval()

        # 2. Disable gradient computation - saves memory and speeds up inference
        for param in self.policy_value_net.parameters():
            param.requires_grad = False

        # 3. Try torch.compile for PyTorch 2.0+ (major speedup)
        try:
            self.policy_value_net = torch.compile(self.policy_value_net, mode="reduce-overhead")
            self.compiled = True
        except:
            self.compiled = False

        # 4. Warmup run to initialize optimizations
        self._warmup()

        if hasattr(self, 'compiled') and self.compiled:
            print("✓ Model optimized with torch.compile")

    def _warmup(self):
        """Warmup run to optimize first inference"""
        with torch.no_grad():
            dummy = torch.zeros(1, 9, 10, 9, dtype=torch.float32).to(self.device)
            _ = self.policy_value_net(dummy)

    # 输入一个批次的状态，输出一个批次的动作概率和状态价值
    def policy_value(self, state_batch):
        # OPTIMIZED: Added torch.no_grad()
        with torch.no_grad():
            state_batch = torch.tensor(state_batch).to(self.device)
            log_act_probs, value = self.policy_value_net(state_batch)
            log_act_probs, value = log_act_probs.cpu(), value.cpu()
            act_probs = np.exp(log_act_probs.numpy())
        return act_probs, value.numpy()

    # 输入棋盘，返回每个合法动作的（动作，概率）元组列表，以及棋盘状态的分数
    # OPTIMIZED: torch.no_grad(), direct tensor conversion, fewer CPU-GPU transfers
    def policy_value_fn(self, board):
        # 获取合法动作列表
        legal_positions = board.availables

        # Optimized tensor conversion - direct from numpy
        current_state = torch.from_numpy(
            board.current_state().reshape(-1, 9, 10, 9).astype(np.float32)
        ).to(self.device, non_blocking=True)

        # OPTIMIZED: Use torch.no_grad() - CRITICAL for speed
        with torch.no_grad():
            log_act_probs, value = self.policy_value_net(current_state)

        # Move to CPU only once at the end
        log_act_probs_cpu = log_act_probs.cpu()
        value_cpu = value.cpu()

        # Convert to numpy efficiently
        act_probs = np.exp(log_act_probs_cpu.numpy().flatten())

        # 只取出合法动作 - faster than zip for small lists
        act_probs = [(pos, act_probs[pos]) for pos in legal_positions]

        # 返回动作概率，以及状态价值
        return act_probs, value_cpu.numpy()

    # 保存模型
    def save_model(self, model_file):
        torch.save(self.policy_value_net.state_dict(), model_file)

    # 执行一步训练
    def train_step(self, state_batch, mcts_probs, winner_batch, lr=0.002):
        self.policy_value_net.train()
        # 包装变量
        state_batch = torch.tensor(state_batch).to(self.device)
        mcts_probs = torch.tensor(mcts_probs).to(self.device)
        winner_batch = torch.tensor(winner_batch).to(self.device)
        # 清零梯度
        self.optimizer.zero_grad()
        # 设置学习率
        for params in self.optimizer.param_groups:
            # 遍历Optimizer中的每一组参数，将该组参数的学习率 * 0.9
            params['lr'] = lr
        # 前向运算
        log_act_probs, value = self.policy_value_net(state_batch)
        value = torch.reshape(value, shape=[-1])
        # 价值损失
        value_loss = F.mse_loss(input=value, target=winner_batch)
        # 策略损失
        policy_loss = -torch.mean(torch.sum(mcts_probs * log_act_probs, dim=1))  # 希望两个向量方向越一致越好
        # 总的损失，注意l2惩罚已经包含在优化器内部
        loss = value_loss + policy_loss
        # 反向传播及优化
        loss.backward()
        self.optimizer.step()
        # 计算策略的熵，仅用于评估模型
        with torch.no_grad():
            entropy = -torch.mean(
                torch.sum(torch.exp(log_act_probs) * log_act_probs, dim=1)
            )
        return loss.detach().cpu().numpy(), entropy.detach().cpu().numpy()


if __name__ == '__main__':
    net = Net().to('cuda')
    test_data = torch.ones([8, 9, 10, 9]).to('cuda')
    x_act, x_val = net(test_data)
    print(x_act.shape)  # 8, 2086
    print(x_val.shape)  # 8, 1
