from pathlib import Path
from tools.log import get_analyze_logger
from ai.ai_srt_lab import summarize_srt
from tools.markdown_lab import save_md_to_file, render_markdown_to_image
from draws.kline_card import make_kline_card, save_img_file
from tools.path import export_file_path, EXPORT_PATH
from media_factory.whisper_mlx import whisper_to_srt
from media_factory.video_handler import extract_audio_from_video
from ai.prompts.srt_prompts import ModeType
from media_factory.yt_dlp import yt_dlp_download
from typing import Optional
import os

logger = get_analyze_logger()

# video_path = EXPORT_PATH / "11 Lessons From Growing A 7-Figure One Person Business.mp4"
# name = video_path.stem

video_url = "https://www.bilibili.com/video/BV1C21pBJErw/?spm_id_from=333.1387.favlist.content.click&vd_source=442a5d658bc897c6e7d62a5abe9ddb13"
logger.info(f"⬇️ Downloading video from {video_url}...")
video_path = yt_dlp_download(video_url, output_dir=EXPORT_PATH)
logger.info(f"✅ Video downloaded to {video_path}")
name = video_path.stem

export_dir = EXPORT_PATH / name
export_dir.mkdir(parents=True, exist_ok=True)

logger.info(f"📁 Export directory created at {export_dir}")

new_video_path = export_dir / video_path.name
os.rename(video_path, new_video_path)
video_path = new_video_path

logger.info(f"📹 Video moved to export directory: {video_path}")

logger.info(f"🤖 Starting AI video analysis for {video_path.name}{video_path.suffix}...")

audio_path = export_dir / f"{name}.wav"
if not audio_path.exists():
    logger.info("🎬 Extracting audio from video...")
    audio_path = extract_audio_from_video(video_path, output_dir=export_dir)
    logger.info(f"✅ Audio extracted to {audio_path}")
else:
    logger.info(f"🎵 Audio file already exists at {audio_path}, skipping extraction.")

srt_path = export_dir / f"{name}.srt"
if srt_path.exists():
    logger.info(f"📝 SRT file already exists at {srt_path}, skipping transcription.")
else:
    logger.info("📝 Transcribing audio to SRT...")
    to_srt_prompt = name
    language = "zh"
    srt_path = whisper_to_srt(audio_path, output_dir=export_dir, language=language, prompt=to_srt_prompt)
    logger.info(f"✅ Transcription completed: {srt_path}")

logger.info("🧠 Summarizing SRT content with AI...")
mode: ModeType = "book"
extra_prompt = "如果是英文，请使用中文总结输出；文章作者为 鳗鱼实验室（Lazy-Lab）。"
summary = summarize_srt(srt_file_path=srt_path, mode=mode, extra_prompt=None)
logger.info(f"✅ Summary completed.")

if summary:
    md_file_path = export_dir / f"{name}_summary.md"
    save_md_to_file(summary, md_file_path)
    logger.info(f"💾 Summary saved to markdown file: {md_file_path}")
    
    image_path = export_dir / f"{name}_summary.png"
    render_markdown_to_image(summary, image_path, open_folder_after=True)
    logger.info(f"🖼️ Rendered and opened image report for {name}_summary")