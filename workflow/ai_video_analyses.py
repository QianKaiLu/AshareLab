from pathlib import Path
from tools.log import get_analyze_logger
from ai.ai_srt_lab import summarize_srt
from tools.markdown_lab import save_md_to_file_name, render_markdown_to_image_file_name
from draws.kline_card import make_kline_card, save_img_file
from tools.path import export_file_path, EXPORT_PATH
from whisper.whisper_mlx import whisper_to_srt
from whisper.video_handler import extract_audio_from_video
from ai.prompts.srt_prompts import ModeType

logger = get_analyze_logger()

video_path = export_file_path(filename="z_talk_1", format="mp4")
name = video_path.stem

logger.info(f"🤖 Starting AI video analysis for {video_path.name}.{video_path.suffix}...")

logger.info("🎬 Extracting audio from video...")
audio_path = extract_audio_from_video(video_path, output_dir=EXPORT_PATH)
logger.info(f"✅ Audio extracted to {audio_path}")

logger.info("📝 Transcribing audio to SRT...")
to_srt_prompt = "股票 金融 投资 分析 财报"
language = "zh"
srt_path = whisper_to_srt(audio_path, output_dir=EXPORT_PATH, language=language, prompt=to_srt_prompt)
logger.info(f"✅ Transcription completed: {srt_path}")

logger.info("🧠 Summarizing SRT content with AI...")
mode: ModeType = "summary"
# extra_prompt = "文章作者为 鳗鱼实验室（Lazy-Lab）。另外需要在合适的位置添加免责声明：本文内容仅供参考，不构成投资建议。投资有风险，入市需谨慎。"
summary = summarize_srt(srt_file_path=srt_path, mode=mode, extra_prompt=None)
logger.info(f"✅ Summary completed.")

if summary:
    md_file_path = save_md_to_file_name(summary, file_name=f"{name}_summary")
    logger.info(f"💾 Summary saved to markdown file: {md_file_path}")
    
    render_markdown_to_image_file_name(summary, f"{name}_summary", open_folder_after=True)
    logger.info(f"🖼️ Rendered and opened image report for {name}_summary")