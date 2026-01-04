from pathlib import Path
from tools.log import get_analyze_logger
from ai.ai_srt_lab import summarize_srt
from tools.markdown_lab import save_md_to_file
from media_factory.whisper_mlx import whisper_to_srt
from media_factory.video_handler import extract_audio_from_video
from ai.prompts.srt_prompts import ModeType
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = get_analyze_logger()
WORKING_DIR = Path(__file__).parent / "output"
mode: ModeType = "book"

video_paths = list(WORKING_DIR.glob("*.mp4"))

with ThreadPoolExecutor(max_workers=8) as executor:
    future_to_info = {}

    # for video_path in video_paths[:1]:  # limit to first 1 videos for testing
    for video_path in video_paths:
        if not video_path.is_file():
            continue

        logger.info(f"🤖 Starting AI video analysis for {video_path.name}...")
        name = video_path.stem

        subdir = WORKING_DIR / name
        subdir.mkdir(parents=True, exist_ok=True)
        
        # audio extraction and SRT transcription
        audio_path = subdir / f"{name}.wav"
        if not audio_path.exists():
            logger.info("🎬 Extracting audio from video...")
            audio_path = extract_audio_from_video(video_path, output_dir=subdir)
            logger.info(f"✅ Audio extracted to {audio_path}")
        else:
            logger.info(f"🎵 Audio file already exists at {audio_path}, skipping extraction.")

        # SRT transcription
        srt_path = subdir / f"{name}.srt"
        if not srt_path.exists():
            logger.info("📝 Transcribing audio to SRT...")
            srt_path = whisper_to_srt(audio_path, output_dir=subdir, language="zh", prompt=name)
            logger.info(f"✅ Transcription completed: {srt_path}")
        else:
            logger.info(f"📝 SRT file already exists at {srt_path}, skipping transcription.")

        # submit summary task
        md_file_path = subdir / f"{name}_summary.md"
        # if not md_file_path.exists():
        logger.info(f"🧠 Submitting summary task for {name}...")
        future = executor.submit(summarize_srt, srt_file_path=srt_path, srt_content=None, mode=mode, extra_prompt=None)
        future_to_info[future] = (subdir, name)

    # collect results
    for future in as_completed(future_to_info):
        subdir, name = future_to_info[future]
        try:
            summary = future.result()
            if summary:
                md_file_path = subdir / f"{name}_summary.md"
                save_md_to_file(summary, md_file_path)
                logger.info(f"✅ Summary saved: {md_file_path}")
            else:
                logger.warning(f"⚠️ Empty summary for {name}")
        except Exception as e:
            logger.error(f"❌ Failed to summarize {name}: {e}")
