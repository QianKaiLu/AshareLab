from pathlib import Path
from datetime import timedelta
import shutil
import time
import subprocess
import json
from tools.log import get_analyze_logger
from typing import Dict, Any, List
# from media_factory.video_handler import extract_audio_from_video
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
        temperature=0.2,
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


def get_audio_duration(audio_path: Path) -> float:
    """
    Get the duration of an audio file in seconds using ffprobe.

    Args:
        audio_path: Path to the audio file

    Returns:
        Duration in seconds
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(audio_path)
            ],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        return duration
    except (subprocess.CalledProcessError, KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to get audio duration: {e}")
        raise RuntimeError(f"Failed to get audio duration from {audio_path}")


def split_audio(
    audio_path: Path,
    segment_duration_minutes: int,
    output_dir: Path
) -> List[tuple[Path, float]]:
    """
    Split an audio file into smaller segments.

    Args:
        audio_path: Path to the input audio file
        segment_duration_minutes: Maximum duration of each segment in minutes
        output_dir: Directory to save the split audio files

    Returns:
        List of tuples (segment_path, start_time_in_seconds)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    total_duration = get_audio_duration(audio_path)
    segment_duration_seconds = segment_duration_minutes * 60

    logger.info(f"Total audio duration: {total_duration:.2f} seconds ({total_duration/60:.2f} minutes)")
    logger.info(f"Splitting into segments of {segment_duration_minutes} minutes each")

    segments = []
    segment_index = 0
    start_time = 0.0

    while start_time < total_duration:
        segment_path = output_dir / f"{audio_path.stem}_segment_{segment_index:03d}.wav"

        # Use ffmpeg to extract the segment with re-encoding to avoid codec issues
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-ss", str(start_time),
            "-t", str(segment_duration_seconds),
            "-ar", "16000",  # Sample rate for Whisper
            "-ac", "1",  # Mono channel
            "-c:a", "pcm_s16le",  # PCM encoding for WAV
            "-y",  # Overwrite output file if exists
            str(segment_path)
        ]

        logger.info(f"Creating segment {segment_index} starting at {start_time:.2f}s")

        try:
            subprocess.run(cmd, capture_output=True, check=True)
            segments.append((segment_path, start_time))
            logger.info(f"Created segment: {segment_path.name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create segment {segment_index}: {e.stderr.decode()}")
            raise

        segment_index += 1
        start_time += segment_duration_seconds

    logger.info(f"Created {len(segments)} segments")
    return segments


def merge_srt_files(
    srt_files: List[tuple[Path, float]],
    output_path: Path
) -> None:
    """
    Merge multiple SRT files into a single file with adjusted timestamps.

    Args:
        srt_files: List of tuples (srt_path, time_offset_in_seconds)
        output_path: Path to save the merged SRT file
    """
    logger.info(f"Merging {len(srt_files)} SRT files into {output_path}")

    subtitle_index = 1

    with open(output_path, "w", encoding="utf-8") as outfile:
        for srt_path, time_offset in srt_files:
            if not srt_path.exists():
                logger.warning(f"SRT file not found: {srt_path}, skipping")
                continue

            with open(srt_path, "r", encoding="utf-8") as infile:
                lines = infile.readlines()

            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # Skip the original subtitle index
                if line.isdigit():
                    i += 1
                    continue

                # Process timestamp line
                if "-->" in line:
                    parts = line.split("-->")
                    if len(parts) == 2:
                        start_str, end_str = parts[0].strip(), parts[1].strip()

                        # Parse timestamps
                        start_seconds = parse_srt_timestamp(start_str)
                        end_seconds = parse_srt_timestamp(end_str)

                        # Add time offset
                        adjusted_start = start_seconds + time_offset
                        adjusted_end = end_seconds + time_offset

                        # Write adjusted subtitle entry
                        outfile.write(f"{subtitle_index}\n")
                        outfile.write(f"{format_timestamp_to_srt(adjusted_start)} --> {format_timestamp_to_srt(adjusted_end)}\n")

                        # Write subtitle text (next line(s) until blank line)
                        i += 1
                        while i < len(lines) and lines[i].strip():
                            outfile.write(lines[i])
                            i += 1

                        outfile.write("\n")
                        subtitle_index += 1

                i += 1

    logger.info(f"Merged SRT file saved to: {output_path}")


def parse_srt_timestamp(timestamp_str: str) -> float:
    """
    Parse an SRT timestamp string (HH:MM:SS,mmm) to seconds.

    Args:
        timestamp_str: Timestamp string in SRT format

    Returns:
        Time in seconds
    """
    # Format: HH:MM:SS,mmm
    time_part, ms_part = timestamp_str.split(",")
    hours, minutes, seconds = map(int, time_part.split(":"))
    milliseconds = int(ms_part)

    total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
    return total_seconds


def whisper_to_srt_long(
    audio_path: Path,
    model_size: str = "large-v3",
    output_dir: Path | None = None,
    language: str = "zh",
    prompt: str = "",
    max_segment_minutes: int = 20,
    keep_segments: bool = False,
) -> Path:
    """
    Transcribes a long audio file by splitting it into smaller segments,
    transcribing each segment separately, and merging the results.

    This method is designed for very long audio files that may cause memory
    issues or timeout when processed as a whole.

    Args:
        audio_path: Path to the input audio file
        model_size: Whisper model size to use
        output_dir: Directory to save the output SRT file
        language: Language code for transcription
        prompt: Optional prompt to guide the transcription
        max_segment_minutes: Maximum duration of each segment in minutes (default: 20)
        keep_segments: Whether to keep intermediate segment files after merging (default: False)

    Returns:
        Path to the final merged SRT file
    """
    if model_size not in VALID_MODELS:
        raise ValueError(f"Invalid model_size: {model_size}. Choose from {list(VALID_MODELS.keys())}")

    if output_dir is None:
        output_dir = audio_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    check_ffmpeg()

    logger.info(f"Starting long audio transcription for: {audio_path}")
    logger.info(f"Max segment duration: {max_segment_minutes} minutes")

    # Create a temporary directory for segments
    temp_dir = output_dir / f"_temp_{audio_path.stem}_segments"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Split audio into segments
        segments = split_audio(audio_path, max_segment_minutes, temp_dir)

        # Step 2: Transcribe each segment
        hf_model_id = VALID_MODELS[model_size]
        logger.info(f"Loading MLX-Whisper model: {hf_model_id}...")

        srt_files = []

        for idx, (segment_path, start_time) in enumerate(segments):
            logger.info(f"Transcribing segment {idx + 1}/{len(segments)}: {segment_path.name}")

            segment_start_time = time.time()

            result = transcribe(
                str(segment_path),
                path_or_hf_repo=hf_model_id,
                language=language,
                prompt=prompt,
                verbose=False,
                temperature=0.2,
            )

            segments_list: List[Dict[str, Any]] = result["segments"]
            logger.info(f"Transcribed {len(segments_list)} segments from {segment_path.name}")

            # Save segment SRT file
            segment_srt_path = temp_dir / f"{segment_path.stem}.srt"
            with open(segment_srt_path, "w", encoding="utf-8") as srt_file:
                for i, seg in enumerate(segments_list):
                    start = format_timestamp_to_srt(seg["start"])
                    end = format_timestamp_to_srt(seg["end"])
                    text = seg["text"].strip()
                    srt_file.write(f"{i + 1}\n{start} --> {end}\n{text}\n\n")

            srt_files.append((segment_srt_path, start_time))

            segment_end_time = time.time()
            logger.info(f"Segment {idx + 1} completed in {segment_end_time - segment_start_time:.2f} seconds")

        # Step 3: Merge all SRT files
        final_srt_path = output_dir / f"{audio_path.stem}.srt"
        merge_srt_files(srt_files, final_srt_path)

        logger.info(f"Transcription completed successfully: {final_srt_path}")

        return final_srt_path

    finally:
        # Clean up temporary files
        if not keep_segments and temp_dir.exists():
            logger.info("Cleaning up temporary segment files...")
            shutil.rmtree(temp_dir)
            logger.info("Cleanup completed")


if __name__ == "__main__":
    video_file = Path(__file__).parent / "datas" / "z_talk_2.mp4"
    # audio_file = extract_audio_from_video(video_file, video_file.parent)
    output_directory = Path(__file__).parent / "datas"
    srt_file = whisper_to_srt_long(
        audio_path=video_file,
        model_size="large-v3",
        max_segment_minutes=10
    )
    logger.info(f"Transcription saved to: {srt_file}")
