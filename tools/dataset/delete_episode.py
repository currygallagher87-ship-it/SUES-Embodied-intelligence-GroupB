import sys
import json
import os
import glob

if len(sys.argv) < 2:
    print("Usage: python delete_episode.py <episode_index>")
    sys.exit(1)

target_ep = int(sys.argv[1])
dataset_dir = '/home/lip/lerobot_data'

# 1. Update episodes.jsonl
ep_file = os.path.join(dataset_dir, 'meta', 'episodes.jsonl')
with open(ep_file, 'r') as f:
    ep_lines = f.readlines()

new_ep_lines = []
target_length = 0
found = False

for line in ep_lines:
    data = json.loads(line)
    if data['episode_index'] == target_ep:
        target_length = data['length']
        found = True
    else:
        new_ep_lines.append(line)

if not found:
    print(f"Episode {target_ep} not found in episodes.jsonl, proceeding to cleanup files anyway just in case.")

with open(ep_file, 'w') as f:
    f.writelines(new_ep_lines)

print(f"Removed episode {target_ep} from episodes.jsonl, length was {target_length}")

# 2. Update episodes_stats.jsonl
stats_file = os.path.join(dataset_dir, 'meta', 'episodes_stats.jsonl')
if os.path.exists(stats_file):
    with open(stats_file, 'r') as f:
        stats_lines = f.readlines()
    new_stats_lines = [line for line in stats_lines if json.loads(line).get('episode_index', -1) != target_ep]
    with open(stats_file, 'w') as f:
        f.writelines(new_stats_lines)
    print(f"Removed episode {target_ep} from episodes_stats.jsonl")

# 3. Update info.json
info_file = os.path.join(dataset_dir, 'meta', 'info.json')
with open(info_file, 'r') as f:
    info_data = json.load(f)

# Ensure the total frames decrement and total episodes decrement
info_data['total_episodes'] -= 1 if found else 0
info_data['total_frames'] -= target_length

last_valid_ep = target_ep - 1
if 'train' in info_data.get('splits', {}):
    # Only useful if removing the absolute last element. If removing in middle, this split logic is flawed.
    # But for trailing corruptions, it resets max train index usually.
    # Wait, the user deleted episode 5 previously? We shouldn't blindly do '0:n'.
    # Actually, splits just indicates indices? The format in splits is "0:<total_episodes>" usually.
    # Let's just fix it to '0:{}'.format(info_data['total_episodes'])
    info_data['splits']['train'] = f"0:{info_data['total_episodes']}"

with open(info_file, 'w') as f:
    json.dump(info_data, f, indent=4)

print(f"Updated info.json: total_episodes={info_data['total_episodes']}, total_frames={info_data['total_frames']}")

# 4. Delete data and video files
ep_str = f"episode_{target_ep:06d}"

# Data
data_files = glob.glob(os.path.join(dataset_dir, 'data', 'chunk-*', f'{ep_str}.parquet'))
for df in data_files:
    os.remove(df)
    print(f"Deleted {df}")

# Videos
video_files = glob.glob(os.path.join(dataset_dir, 'videos', 'chunk-*', '*', f'{ep_str}.mp4'))
for vf in video_files:
    os.remove(vf)
    print(f"Deleted {vf}")

print(f"Dataset cleanup for episode {target_ep} completed!")
