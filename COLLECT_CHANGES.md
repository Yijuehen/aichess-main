# Self-Play Data Collection - Individual Episode Saving

## Summary

The `collect.py` script has been modified to save each self-play game (episode) separately instead of only accumulating them in batches.

## Changes Made

### 1. Individual Game Files
Each game is now saved to a separate file:
```
selfplay_data/game_1_20250120_143025.pkl
selfplay_data/game_2_20250120_143530.pkl
selfplay_data/game_3_20250120_144108.pkl
...
```

### 2. Episode Data Structure
Each file contains complete information about the game:
```python
episode_data = {
    'game_id': 1,                    # Sequential game number
    'winner': 1,                     # 1=Red, -1=Black, 0=Tie
    'episode_len': 42,               # Number of moves
    'timestamp': '2025-01-20T14:30:25',  # ISO format timestamp
    'raw_data': [...],               # Original move data
    'extended_data': [...]           # Data with horizontal flip augmentation
}
```

### 3. Collection Log
A `collection_log.txt` file tracks all games in CSV format:
```
game_id,timestamp,winner,moves,extended_samples
1,20250120_143025,1,42,84
2,20250120_143530,-1,38,76
3,20250120_144108,1,55,110
```

### 4. Progress Display
Each game shows detailed progress:
```
============================================================
Game 1/10 starting...
============================================================
[+] Game completed!
    Winner: Red
    Moves: 42
    Timestamp: 2025-01-20 14:30:25
    Extended samples: 84
[+] Saved to: selfplay_data/game_1_20250120_143025.pkl
[+] Total buffer updated: 2520 samples, 1 games
============================================================
```

## Usage

### Run Self-Play Collection
```bash
cd aichess-main
python collect.py
```

### Output Location
- Individual game files: `selfplay_data/game_*.pkl`
- Collection log: `selfplay_data/collection_log.txt`
- Combined buffer: `train_data_buffer.pkl` (for backward compatibility)

### Loading Individual Games
```python
import pickle

# Load a specific game
with open('selfplay_data/game_1_20250120_143025.pkl', 'rb') as f:
    game_data = pickle.load(f)

print(f"Game {game_data['game_id']}: {game_data['episode_len']} moves")
print(f"Winner: {'Red' if game_data['winner'] == 1 else 'Black'}")

# Access training data
training_samples = game_data['extended_data']
```

## Features

### Data Augmentation
Each game is doubled using horizontal flip symmetry:
- Original moves: `episode_len` samples
- Extended moves: `episode_len * 2` samples (with flip)

### Backward Compatibility
The script still maintains the original combined buffer:
- Updates `train_data_buffer.pkl` with all accumulated data
- Supports Redis if enabled in config

### Error Handling
- Individual game save failures don't stop the collection
- Buffer save failures are reported but don't crash
- Progress continues even if one game fails to save

## Benefits

1. **Incremental Analysis**: Analyze individual games without loading the entire dataset
2. **Debugging**: Easier to identify problematic games or patterns
3. **Selective Training**: Choose specific games for training
4. **Progress Tracking**: See exactly how many games have been collected
5. **Data Management**: Easy to backup, move, or delete specific games
6. **Resume Capability**: Can continue from where collection stopped

## Configuration

Key settings in `collect.py`:
- `self.save_dir = 'selfplay_data'` - Directory for individual game files
- `self.temp = 1` - Temperature for exploration
- `self.n_playout = CONFIG['play_out']` - MCTS simulations per move
- `self.buffer_size = CONFIG['buffer_size']` - Max samples in combined buffer

## File Formats

### .pkl File Format
Standard Python pickle format containing:
- Metadata (game_id, winner, etc.)
- Raw move sequence (list of tuples)
- Extended move sequence with augmentation (list of tuples)

### Log File Format
CSV with columns:
1. game_id - Sequential game number
2. timestamp - YYYYMMDD_HHMMSS format
3. winner - 1 (Red), -1 (Black), 0 (Tie)
4. moves - Number of moves in game
5. extended_samples - Total training samples after augmentation

## Notes

- Game IDs are sequential and increment with each completed game
- Timestamps use ISO 8601 format for uniqueness
- All data is pickle-serialized for fast loading
- Extended data includes both original and horizontally-flipped positions
- Log file is appended to, not overwritten (preserves history)
