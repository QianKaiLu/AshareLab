from pathlib import Path
from datetime import timedelta
import shutil
import time
from tools.log import get_analyze_logger
from typing import Dict, Any, List
from video_handler import extract_audio_from_video
from faster_whisper import WhisperModel

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
        raise RuntimeError("ffmpeg not found. Please install ffmpeg.")

def whisper_to_srt(
    audio_path: Path,
    model_size: str = "large-v3",
    output_dir: Path | None = None,
    language: str = "zh",
    prompt: str = "",
    beam_size: int = 5,
    best_of: int = 5,
    temperature: float = 0.0,
) -> Path:
    """
    Transcribes an audio file using faster-whisper and saves the transcription in SRT format.
    """
    if model_size not in VALID_MODELS:
        raise ValueError(f"Invalid model_size: {model_size}. Choose from {VALID_MODELS}")
    
    if output_dir is None:
        output_dir = audio_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    check_ffmpeg()
    
    trans_start = time.time()
    logger.info(f"Loading faster-whisper model: {model_size}...")

    model = WhisperModel(
        model_size,
        device="auto",
        compute_type="int8",
        cpu_threads=8,
        num_workers=2
    )
    logger.info(f"Loaded faster-whisper model: {model_size} on {model.model.device}.")
    
    logger.info(f"Transcribing audio file: {audio_path}...")
    segments_raw, info = model.transcribe(
        str(audio_path),
        language=language,
        initial_prompt=prompt,
        beam_size=beam_size,
        best_of=best_of,
        temperature=temperature,
        word_timestamps=False,
        vad_filter=False,
        vad_parameters=dict(min_silence_duration_ms=500),
        log_progress=True
    )

    segments_list = []
    for segment in segments_raw:
        segments_list.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text
        })

    srt_output_path = output_dir / f"{audio_path.stem}.srt"
    with open(srt_output_path, "w", encoding="utf-8") as srt_file:
        for i, seg in enumerate(segments_list):
            start_time = format_timestamp_to_srt(seg["start"])
            end_time = format_timestamp_to_srt(seg["end"])
            text = seg["text"].strip()
            srt_file.write(f"{i + 1}\n{start_time} --> {end_time}\n{text}\n\n")
            
    trans_end = time.time()
    elapsed = trans_end - trans_start
    logger.info(f"Transcription completed in {elapsed:.2f} seconds.")
    
    return srt_output_path

if __name__ == "__main__":
    video_file = Path(__file__).parent / "datas" / "z_talk_1.mp4"
    audio_file = extract_audio_from_video(video_file, video_file.parent)
    output_directory = Path(__file__).parent / "datas"
    srt_file = whisper_to_srt(
        audio_file,
        model_size="large-v3",
        output_dir=output_directory,
        language="zh",
        prompt="股票 分析 财报 投资",
    )
    logger.info(f"Transcription saved to: {srt_file}")
