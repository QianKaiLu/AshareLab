from pathlib import Path
from tools.log import get_analyze_logger
from tools.path import EXPORT_PATH
from media_factory.yt_dlp import yt_dlp_download_urls
import os

logger = get_analyze_logger()

EXPORT_PATH = Path(__file__).parent / "output"

video_urls = ["https://www.youtube.com/watch?v=XgAMayF-JZY",
              "https://www.youtube.com/watch?v=QoBCtcWO02g",
              "https://www.youtube.com/watch?v=Er2s-CFoZSo"]
video_paths: list[Path] = yt_dlp_download_urls(video_urls, output_dir=EXPORT_PATH)
for video_path in video_paths:
    logger.info(f"✅ Video downloaded to {video_path}")