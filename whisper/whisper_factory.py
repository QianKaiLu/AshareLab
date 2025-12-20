import whisper
from pathlib import Path
from datetime import timedelta, datetime
import shutil
import torch
import time
from tools.log import get_analyze_logger
from typing import Dict, Any
from video_handler import extract_audio_from_video

logger = get_analyze_logger()

VALID_MODELS = {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}

def format_timestamp_to_srt(seconds: float) -> str:
    """Formats a timestamp in seconds to SRT format (HH:MM:SS,mmm)."""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    milliseconds = int(td.microseconds / 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def check_ffmpeg():
    if not shutil.which("ffmpeg"):
        logger.error("ffmpeg not found. Please install ffmpeg (brew install ffmpeg).")
        raise RuntimeError("ffmpeg not found. Please install ffmpeg (brew install ffmpeg).")
    
def merge_segments(segments, max_length=40, max_gap=1.5) -> list[Dict[str, Any]]:
    """
    Merges transcription segments based on maximum length and gap constraints.
    """
    if not segments:
        return []

    merged = []
    current_text = segments[0]["text"].strip()
    current_start = segments[0]["start"]
    current_end = segments[0]["end"]

    for i in range(1, len(segments)):
        seg = segments[i]
        gap = seg["start"] - current_end
        if gap <= max_gap and len(current_text) + len(seg["text"]) <= max_length:
            current_text += seg["text"].strip()
            current_end = seg["end"]
        else:
            merged.append({
                "start": current_start,
                "end": current_end,
                "text": current_text
            })
            current_text = seg["text"].strip()
            current_start = seg["start"]
            current_end = seg["end"]
    
    merged.append({
        "start": current_start,
        "end": current_end,
        "text": current_text
    })
    return merged

def whisper_to_srt(audio_path: Path, model_size: str = "base", output_dir: Path | None = None, language: str = "zh", prompt: str = "") -> Path:
    """
    Transcribes an audio file using Whisper and saves the transcription in SRT format.

    Args:
        audio_path (Path): Path to the input audio file.
        model_size (str): Size of the Whisper model to use (e.g., "tiny", "base", "small", "medium", "large").
        output_dir (Path): Directory where the SRT file will be saved. If None, saves in the same directory as audio_path.
    Returns:
        Path: Path to the saved SRT file.
    """
    
    if model_size not in VALID_MODELS:
        raise ValueError(f"Invalid model_size: {model_size}. Choose from {VALID_MODELS}")
    
    if output_dir is None:
        output_dir = audio_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    trans_start = time.time()
    
    check_ffmpeg()

    model = whisper.load_model(model_size)
    logger.info(f"Loaded model: {model_size}, num parameters: {sum(p.numel() for p in model.parameters()) / 1e6:.1f}M")
    
    logger.info(f"Transcribing audio file: {audio_path}...")
    result = model.transcribe(str(audio_path), language=language, initial_prompt=prompt, verbose=False)
    srt_output_path = output_dir / f"{audio_path.stem}.srt"
    
    print(result)
    
    with open(srt_output_path, "w", encoding="utf-8") as srt_file:
        merged_segments: list[Dict[str, Any]] = result["segments"]
        for i, segment in enumerate(merged_segments):
            start_time = format_timestamp_to_srt(segment["start"])
            end_time = format_timestamp_to_srt(segment["end"])
            text = segment["text"].strip()
            srt_file.write(f"{i + 1}\n")
            srt_file.write(f"{start_time} --> {end_time}\n")
            srt_file.write(f"{text}\n\n")
            
    trans_end = time.time()
    elapsed = trans_end - trans_start
    logger.info(f"Transcription completed in {elapsed:.2f} seconds.")
    return srt_output_path

if __name__ == "__main__":
    video_file = Path(__file__).parent / "datas" / "z_talk_1.mp4"
    audio_file = extract_audio_from_video(video_file, video_file.parent)
    output_directory = Path(__file__).parent / "datas"
    srt_file = whisper_to_srt(audio_file, model_size="large-v3", output_dir=output_directory)
    logger.info(f"Transcription saved to: {srt_file}")