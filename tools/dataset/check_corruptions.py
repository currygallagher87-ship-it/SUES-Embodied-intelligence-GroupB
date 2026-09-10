import pandas as pd
import glob
import os

dataset_dir = '/home/lip/lerobot_data'
parquet_files = sorted(glob.glob(os.path.join(dataset_dir, 'data', 'chunk-*', 'episode_*.parquet')))

corrupted_eps = []
for pf in parquet_files:
    try:
        df = pd.read_parquet(pf, columns=['timestamp', 'episode_index'])
        diff = df['timestamp'].diff()
        drop = diff < 0
        if drop.any():
            ep_idx = df['episode_index'].iloc[0]
            corrupted_eps.append(ep_idx)
            print(f"Episode {ep_idx} has invalid timestamps (timestamp went backward).")
    except Exception as e:
        print(f"Error reading {pf}: {e}")

if not corrupted_eps:
    print("All remaining episodes look fine timestamp-wise!")
else:
    print(f"The following episodes are corrupted: {corrupted_eps}")
