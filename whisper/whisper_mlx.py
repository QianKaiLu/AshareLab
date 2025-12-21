from pathlib import Path
from datetime import timedelta
import shutil
import time
from tools.log import get_analyze_logger
from typing import Dict, Any, List
from whisper.video_handler import extract_audio_from_video
from mlx_whisper import transcribe

logger = get_analyze_logger()

VALID_MODELS = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "large": "mlx-community/whisper-large",
    "large-v2": "mlx-community/whisper-large-v2",
    "large-v3": "mlx-community/whisper-large-v3-turbo",
}

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
) -> Path:
    """
    Transcribes an audio file using MLX-Whisper and saves the transcription in SRT format.
    """
    if model_size not in VALID_MODELS:
        raise ValueError(f"Invalid model_size: {model_size}. Choose from {list(VALID_MODELS.keys())}")
    
    if output_dir is None:
        output_dir = audio_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    check_ffmpeg()
    
    trans_start = time.time()
    hf_model_id = VALID_MODELS[model_size]
    logger.info(f"Loading MLX-Whisper model: {hf_model_id}...")

    result = transcribe(
        str(audio_path),
        path_or_hf_repo=hf_model_id,
        language=language,
        prompt=prompt,
        verbose=False,
        temperature=0.0,
    )

    segments_list: List[Dict[str, Any]] = result["segments"]
    logger.info(f"Transcribed {len(segments_list)} segments.")

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
    video_file = Path(__file__).parent / "datas" / "ad_video.mp4"
    # audio_file = extract_audio_from_video(video_file, video_file.parent)
    output_directory = Path(__file__).parent / "datas"
    srt_file = whisper_to_srt(
        video_file,
        model_size="large-v3",
        output_dir=output_directory,
        language="zh",
        prompt="本命年 忌争强 广告",
    )
    logger.info(f"Transcription saved to: {srt_file}")
