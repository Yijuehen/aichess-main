"""
Benchmark script to test neural network inference optimization
"""
import time
import sys
import os

# Change to script directory
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

from pytorch_net import PolicyValueNet

print("=" * 60)
print("Neural Network Inference Benchmark")
print("=" * 60)

# Load optimized model
print("\nLoading optimized model...")
net = PolicyValueNet(model_file='models/current_policy100.pkl', use_gpu=False, device='cpu')
print(f"[+] Model loaded")
print(f"  - Compiled: {net.compiled if hasattr(net, 'compiled') else 'N/A'}")

# Create dummy board state
import numpy as np
dummy_board_state = np.zeros((10, 9, 9), dtype=np.float32)

# Create a minimal board object for testing
class DummyBoard:
    def __init__(self):
        self.state = np.random.rand(10, 9, 9).astype(np.float32)

    def current_state(self):
        return self.state

    @property
    def availables(self):
        # Return some dummy legal moves
        return list(range(100))

dummy_board = DummyBoard()

# Warmup
print("\nWarming up...")
for _ in range(5):
    net.policy_value_fn(dummy_board)

# Benchmark single inference
print("\n" + "=" * 60)
print("Single Inference Performance Test")
print("=" * 60)

iterations = 100
start = time.time()
for _ in range(iterations):
    act_probs, value = net.policy_value_fn(dummy_board)
elapsed = time.time() - start

print(f"\nResults for {iterations} inferences:")
print(f"  - Total time: {elapsed:.2f}s")
print(f"  - Average: {elapsed/iterations*1000:.1f}ms per inference")
print(f"  - Speed: {iterations/elapsed:.1f} inferences/second")
print(f"  - Latency: {elapsed/iterations*1000:.1f}ms")

# Estimate game performance
print("\n" + "=" * 60)
print("Estimated Game Performance")
print("=" * 60)

# MCTS with 400 playouts (current UI setting)
mcts_playouts = 400
avg_inferences_per_move = mcts_playouts  # Rough estimate

estimated_time_per_move = (elapsed/iterations) * avg_inferences_per_move
print(f"\nWith {mcts_playouts} MCTS playouts:")
print(f"  - Estimated time per AI move: {estimated_time_per_move:.1f}s ({estimated_time_per_move:.0f}ms)")
print(f"  - This is {'FAST' if estimated_time_per_move < 3 else 'SLOW'} for game play")

# Recommendations
print("\n" + "=" * 60)
print("Optimization Recommendations")
print("=" * 60)

if estimated_time_per_move < 1:
    print("[+] EXCELLENT! Very fast - can increase n_playout for stronger AI")
    print("  Try: n_playout=800 or n_playout=1200 in UIplay.py")
elif estimated_time_per_move < 3:
    print("[+] GOOD! Balanced speed/strength")
    print("  Current setting (n_playout=400) is good for game play")
else:
    print("[!] SLOW! Consider these optimizations:")
    print("  1. Reduce n_playout to 200-300")
    print("  2. Use a smaller model (fewer res blocks)")
    print("  3. Get a GPU for faster inference")

print("\n" + "=" * 60)
print("Optimizations Applied:")
print("=" * 60)
print("[+] ReLU(inplace=True) - Saves memory")
print("[+] requires_grad=False - Disables gradient computation")
print("[+] torch.no_grad() - No gradient tracking during inference")
print("[+] torch.compile() - JIT compilation (if available)")
print("[+] Direct numpy->tensor conversion - Reduces overhead")
print("[+] Eval mode - Disables dropout/batchnorm training features")
print("[+] Fixed log_softmax dim parameter")
print("[+] Fixed value_act1 bug (was called twice)")
print("=" * 60)
