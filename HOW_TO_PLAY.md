# How to Play Against the AI Chess

## Setup Complete!

The AI chess project has been configured and is ready to use. Here's how to play:

## Prerequisites

- Python 3.14 installed in `.venv`
- PyTorch installed (CPU version)
- Model `current_policy100.pkl` converted and ready

## Two Ways to Play

### Option 1: Command Line Interface (Simple)

Run from PowerShell or terminal:

```bash
cd D:\code\project\chess\aichess-main
python.exe play_with_ai.py
```

**How to make moves:**
- Enter moves in the format: `row1col1row2col2`
- For example: `0304` means move from row 0, col 3 to row 0, col 4
- Rows are 0-9 (top to bottom), columns are 0-8 (left to right)
- Red pieces move first

The board will display in Chinese characters. You'll see the board state after each move.

### Option 2: GUI Interface (Recommended)

1. First install pygame (only need to do this once):
```bash
cd D:\code\project\chess
.venv\Scripts\pip install pygame
```

2. Run the GUI:
```bash
cd aichess-main
..\..\.venv\Scripts\python.exe UIplay.py
```

**How to play:**
- Click on the piece you want to move (it will be highlighted with fire)
- Click on the destination square
- The AI will respond automatically

## Configuration

Current settings in `config.py`:
- **Framework:** PyTorch
- **Model:** `models/current_policy100.pkl` (converted from PaddlePaddle)
- **AI Strength:** MCTS with 100 playouts (play_with_ai) or 1000-2000 (UIplay)
- **Device:** CPU

## Game Rules

This is **Chinese Chess (象棋)**, not Western chess!

### Board Setup:
- Red pieces at top (you play first)
- Black pieces at bottom (AI plays)

### Pieces:
- 帅/将 - General/King
- 士 - Advisor
- 象/相 - Elephant
- 马 - Horse/Knight
- 车 - Chariot/Rook
- 炮 - Cannon
- 兵/卒 - Soldier/Pawn

### Objective:
Capture the opponent's General (帅/将)

## Model Information

- **Original Format:** PaddlePaddle (`.model` file)
- **Converted to:** PyTorch (`.pkl` file) for compatibility
- **Training:** AlphaZero algorithm with MCTS
- **Training iterations:** 100 steps
- **Fixed issues:**
  - CPU-only PyTorch compatibility
  - Removed FP16 autocast for CPU
  - Proper parameter name mapping from Paddle to PyTorch

## Troubleshooting

**If the game is too slow:**
- Reduce `n_playout` in the play scripts (try 50 instead of 100)

**If you see encoding issues:**
- The Chinese characters may display as squares in some terminals
- This is normal and doesn't affect gameplay

**To use GPU (if you have NVIDIA CUDA):**
1. Install CUDA-enabled PyTorch
2. Remove `use_gpu=False` from the play scripts
3. Change `device='cpu'` to `device='cuda'`

## Advanced: Modify AI Strength

Edit these values in `play_with_ai.py` or `UIplay.py`:

```python
mcts_player = MCTSPlayer(
    policy_value_net.policy_value_fn,
    c_puct=5,
    n_playout=100,  # Adjust: 50=easy, 100=medium, 500+=hard
    is_selfplay=0
)
```

- Lower `n_playout` = faster but weaker AI
- Higher `n_playout` = stronger but slower AI
- Recommended for CPU: 50-200
- With GPU: can go up to 1000-5000
