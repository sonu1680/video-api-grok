import re
import subprocess
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("GrokAPI.VideoTrimmer")

def get_video_duration(video_path: str) -> float:
    """Gets the duration of a video file in seconds."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", video_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        log.error(f"Failed to get duration for {video_path}: {e}")
        return 0.0

def detect_last_dialogue_end(video_path: Path) -> float:
    """
    Analyzes the audio track of the video to find the last point where dialogue occurs.
    Uses frequency filtering and noise reduction to ignore background music.
    Returns the timestamp (in seconds) to trim at, or the total duration if no trimming is needed.
    """
    video_path_str = str(video_path.absolute())
    duration = get_video_duration(video_path_str)
    
    if duration == 0.0:
        return duration
        
    # We use highpass and lowpass to isolate human voice frequencies.
    # afftdn applies FFT-based noise reduction.
    # silencedetect finds periods of relative quiet.
    cmd = [
        "ffmpeg", "-i", video_path_str,
        "-af", "highpass=f=200,lowpass=f=3000,afftdn=nf=-25,silencedetect=noise=-35dB:d=0.3",
        "-f", "null", "-"
    ]
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    output = result.stderr
    
    silences = []
    current_start = None
    
    for line in output.splitlines():
        if "silence_start:" in line:
            match = re.search(r"silence_start:\s*([\d\.]+)", line)
            if match:
                current_start = float(match.group(1))
        elif "silence_end:" in line:
            match = re.search(r"silence_end:\s*([\d\.]+)", line)
            if match and current_start is not None:
                end_time = float(match.group(1))
                silences.append((current_start, end_time))
                current_start = None
    
    # If the video ends while still in silence
    if current_start is not None:
        silences.append((current_start, duration))
        
    if not silences:
        log.info(f"🔈 No silence detected in {video_path.name}")
        return duration
        
    # Check if the last silence block reaches the end of the video
    last_silence_start, last_silence_end = silences[-1]
    
    # Allow a small margin (0.2s) to consider it the "end" of the video
    if last_silence_end >= duration - 0.2:
        # Don't trim the video to zero. Keep at least 1 second or half the video length.
        min_length = min(1.0, duration / 2.0)
        trim_point = max(last_silence_start, min_length)
        log.info(f"🔇 Silent tail detected. Original: {duration:.2f}s, Trim point: {trim_point:.2f}s")
        return trim_point
        
    log.info(f"🔈 Silence detected but not at the end. Keeping original duration {duration:.2f}s")
    return duration

def trim_video_to_timestamp(video_path: Path, end_timestamp: float) -> Path:
    """
    Trims the video precisely to the given end_timestamp using re-encoding.
    """
    video_path_str = str(video_path.absolute())
    output_path = video_path.parent / f"trimmed_{video_path.name}"
    
    duration = get_video_duration(video_path_str)
    
    # If the trim point is very close to the end, don't bother trimming.
    if duration - end_timestamp < 0.2:
        log.info(f"⏭️ Skipping trim for {video_path.name} (difference < 0.2s)")
        return video_path
        
    cmd = [
        "ffmpeg", "-y", "-i", video_path_str,
        "-t", str(end_timestamp),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path.absolute())
    ]
    
    log.info(f"✂️ Trimming {video_path.name} to {end_timestamp:.2f}s")
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if process.returncode == 0 and output_path.exists():
        log.info(f"✅ Successfully trimmed to {output_path.name}")
        return output_path
    else:
        log.error(f"❌ Failed to trim {video_path.name}: {process.stderr}")
        return video_path # Fallback to original file
