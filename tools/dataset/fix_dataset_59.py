import json
import os
import glob

dataset_dir = '/home/lip/lerobot_data'

# 1. Update episodes.jsonl
ep_file = os.path.join(dataset_dir, 'meta', 'episodes.jsonl')
with open(ep_file, 'r') as f:
    ep_lines = f.readlines()

new_ep_lines = []
ep59_length = 0
for line in ep_lines:
    data = json.loads(line)
    if data['episode_index'] == 59:
        ep59_length = data['length']
    else:
        new_ep_lines.append(line)

with open(ep_file, 'w') as f:
    f.writelines(new_ep_lines)

print(f"Removed episode 59 from episodes.jsonl, length was {ep59_length}")

# 2. Update episodes_stats.jsonl
stats_file = os.path.join(dataset_dir, 'meta', 'episodes_stats.jsonl')
if os.path.exists(stats_file):
    with open(stats_file, 'r') as f:
        stats_lines = f.readlines()
    new_stats_lines = [line for line in stats_lines if json.loads(line).get('episode_index', -1) != 59]
    with open(stats_file, 'w') as f:
        f.writelines(new_stats_lines)
    print("Removed episode 59 from episodes_stats.jsonl")

# 3. Update info.json
info_file = os.path.join(dataset_dir, 'meta', 'info.json')
with open(info_file, 'r') as f:
    info_data = json.load(f)

info_data['total_episodes'] = 59
if 'train' in info_data.get('splits', {}):
    info_data['splits']['train'] = '0:59'

info_data['total_frames'] -= ep59_length

with open(info_file, 'w') as f:
    json.dump(info_data, f, indent=4)

print(f"Updated info.json: total_episodes={info_data['total_episodes']}, total_frames={info_data['total_frames']}")

# 4. Delete data and video files
# Data: data/chunk-*/episode_000059.parquet
data_files = glob.glob(os.path.join(dataset_dir, 'data', 'chunk-*', 'episode_000059.parquet'))
for df in data_files:
    os.remove(df)
    print(f"Deleted {df}")

# Videos: videos/chunk-*/*/episode_000059.mp4
video_files = glob.glob(os.path.join(dataset_dir, 'videos', 'chunk-*', '*', 'episode_000059.mp4'))
for vf in video_files:
    os.remove(vf)
    print(f"Deleted {vf}")

print("Dataset cleanup for episode 59 completed!")
