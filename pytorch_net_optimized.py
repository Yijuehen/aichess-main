"""策略价值网络 - Inference Optimized"""


import torch
import torch.nn as nn
import numpy as np
import torch.nn.functional as F
from config import CONFIG


# 搭建残差块 - Optimized for inference
class ResBlock(nn.Module):

    def __init__(self, num_filters=256):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels=num_filters, out_channels=num_filters, kernel_size=(3, 3), stride=(1, 1), padding=1)
        self.conv1_bn = nn.BatchNorm2d(num_filters, )
        self.conv1_act = nn.ReLU(inplace=True)  # In-place for memory efficiency
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


# 搭建骨干网络，输入：N, 9, 10, 9 --> N, C, H, W - Optimized for inference
class Net(nn.Module):

    def __init__(self, num_channels=256, num_res_blocks=7):
        super().__init__()
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
        policy = F.log_softmax(policy, dim=1)  # Explicit dim for clarity
        # 价值头
        value = self.value_conv(x)
        value = self.value_bn(value)
        value = self.value_act1(value)
        value = torch.reshape(value, [-1, 8 * 10 * 9])
        value = self.value_fc1(value)
        value = self.value_act2(value)
        value = self.value_fc2(value)
        value = torch.tanh(value)

        return policy, value


# 策略值网络 - Optimized for Inference
class PolicyValueNet:

    def __init__(self, model_file=None, use_gpu=None, device=None):
        # 使用CONFIG配置作为默认值
        self.use_gpu = CONFIG['use_gpu'] if use_gpu is None else use_gpu
        self.device = CONFIG['device'] if device is None else device
        self.policy_value_net = Net().to(self.device)

        # Load model if provided
        if model_file:
            self.policy_value_net.load_state_dict(torch.load(model_file, weights_only=False, map_location=self.device))

        # CRITICAL: Set to eval mode and optimize for inference
        self.policy_value_net.eval()

        # Disable gradient calculation for inference
        for param in self.policy_value_net.parameters():
            param.requires_grad = False

        # Try to use torch.compile for PyTorch 2.0+ (significant speedup)
        try:
            self.policy_value_net = torch.compile(self.policy_value_net, mode="reduce-overhead")
            self.compiled = True
            print("✓ Model compiled with torch.compile for faster inference")
        except:
            self.compiled = False
            print("⚠ torch.compile not available, using eager mode")

        # Warmup run to optimize
        self._warmup()

    def _warmup(self):
        """Warmup run to initialize optimizations"""
        dummy_state = torch.zeros(1, 9, 10, 9, dtype=torch.float32).to(self.device)
        with torch.no_grad():
            _ = self.policy_value_net(dummy_state)

    # 输入棋盘，返回每个合法动作的（动作，概率）元组列表，以及棋盘状态的分数
    # OPTIMIZED: Removed all unnecessary operations, added torch.no_grad
    def policy_value_fn(self, board):
        # 获取合法动作列表
        legal_positions = board.availables

        # Optimized tensor creation - directly from numpy without intermediate conversions
        current_state = torch.from_numpy(
            board.current_state().reshape(-1, 9, 10, 9).astype(np.float32)
        ).to(self.device, non_blocking=True)

        # Use torch.no_grad() for inference - disables gradient tracking
        with torch.no_grad():
            log_act_probs, value = self.policy_value_net(current_state)

        # Move to CPU and convert to numpy - only once at the end
        log_act_probs_cpu = log_act_probs.cpu()
        value_cpu = value.cpu()

        # Convert to numpy efficiently
        act_probs = np.exp(log_act_probs_cpu.numpy().flatten())

        # 只取出合法动作 - use list comprehension instead of zip for speed
        act_probs = [(pos, act_probs[pos]) for pos in legal_positions]

        # 返回动作概率，以及状态价值
        return act_probs, value_cpu.numpy()

    # 批量推理优化 - for multiple board states
    def policy_value_batch(self, boards):
        """
        Optimized batch inference for multiple boards
        Much faster than calling policy_value_fn multiple times
        """
        batch_size = len(boards)

        # Stack all states into a single batch
        states = np.stack([board.current_state() for board in boards])
        states = states.reshape(batch_size, 9, 10, 9).astype(np.float32)

        # Convert to tensor
        states_tensor = torch.from_numpy(states).to(self.device, non_blocking=True)

        # Batch inference
        with torch.no_grad():
            log_act_probs, values = self.policy_value_net(states_tensor)

        # Convert back to numpy
        log_act_probs = log_act_probs.cpu().numpy()
        values = values.cpu().numpy().flatten()

        # Process results for each board
        results = []
        for i, board in enumerate(boards):
            legal_positions = board.availables
            act_probs = np.exp(log_act_probs[i].flatten())
            act_probs = [(pos, act_probs[pos]) for pos in legal_positions]
            results.append((act_probs, values[i]))

        return results

    # Legacy compatibility - not used in optimized version
    def policy_value(self, state_batch):
        """Legacy method - kept for compatibility but not optimized"""
        self.policy_value_net.eval()
        state_batch = torch.tensor(state_batch).to(self.device)
        with torch.no_grad():
            log_act_probs, value = self.policy_value_net(state_batch)
        log_act_probs, value = log_act_probs.cpu(), value.cpu()
        act_probs = np.exp(log_act_probs.numpy())
        return act_probs, value.numpy()

    def save_model(self, model_file):
        """Save model - not needed for inference but kept for compatibility"""
        torch.save(self.policy_value_net.state_dict(), model_file)


if __name__ == '__main__':
    import time

    # Test optimized network
    print("Testing optimized network...")
    net = PolicyValueNet(model_file='models/current_policy100.pkl')

    # Test inference speed
    dummy_board_state = np.zeros((10, 9, 9), dtype=np.float32)

    # Warmup
    for _ in range(3):
        _ = net.policy_value_net(torch.from_numpy(dummy_board_state.reshape(1, 9, 10, 9)).cpu())

    # Benchmark
    start = time.time()
    for _ in range(100):
        with torch.no_grad():
            _ = net.policy_value_net(torch.from_numpy(dummy_board_state.reshape(1, 9, 10, 9)).cpu())
    elapsed = time.time() - start

    print(f"\n✓ Optimization complete!")
    print(f"  - Inference speed: {100/elapsed:.1f} predictions/second")
    print(f"  - Average latency: {elapsed*1000:.1f}ms per prediction")
    print(f"  - Model compiled: {net.compiled}")
