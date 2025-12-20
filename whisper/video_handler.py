from moviepy import VideoFileClip
import os
from pathlib import Path

def extract_audio_from_video(video_path: Path, output_dir: Path) -> Path:
    """
    Extracts audio from a video file and saves it as a WAV file.

    Args:
        video_path (Path): Path to the input video file.
        output_dir (Path): Directory where the extracted audio will be saved.

    Returns:
        Path: Path to the saved audio file.
    """
    video_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    try:
        video_clip = VideoFileClip(str(video_path))
    except Exception as e:
        raise ValueError(f"Failed to load video file {video_path}: {e}")

    video_filename = video_path.stem
    audio_output_path = output_dir / f"{video_filename}.wav"

    audio = video_clip.audio
    
    if audio is None:
        raise ValueError("The video file does not contain an audio track.")
    
    audio.write_audiofile(str(audio_output_path), codec='pcm_s16le')

    video_clip.close()

    return audio_output_path

if __name__ == "__main__":
    video_file = Path(__file__).parent / "datas" / "ad_video.mp4"
    output_directory = Path(__file__).parent / "datas"
    audio_file = extract_audio_from_video(video_file, output_directory)
    print(f"Extracted audio saved to: {audio_file}")