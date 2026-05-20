from app.pipelines.video_trimmer import detect_last_dialogue_end, trim_video_to_timestamp, get_video_duration
from pathlib import Path

test_vid = Path("test_assets/test_video.mp4")

print(f"Original Duration: {get_video_duration(str(test_vid))}")
trim_point = detect_last_dialogue_end(test_vid)
print(f"Trim Point: {trim_point}")

if trim_point > 0:
    trimmed_vid = trim_video_to_timestamp(test_vid, trim_point)
    print(f"Trimmed Video Path: {trimmed_vid}")
    if trimmed_vid.exists():
        print(f"Trimmed Duration: {get_video_duration(str(trimmed_vid))}")
