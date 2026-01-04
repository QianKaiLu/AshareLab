from pathlib import Path
from tools.log import get_analyze_logger
from tools.path import EXPORT_PATH
from media_factory.yt_dlp import yt_dlp_download_list
import os

logger = get_analyze_logger()

EXPORT_PATH = Path(__file__).parent / "output"

list_url = "https://www.youtube.com/watch?v=BZ2nSULolKI&list=PLB4ePXk6nBaeG3fD13NaRMsRsEc2iCsV4"
logger.info(f"⬇️ Downloading playlist from {list_url}...")
video_paths: list[Path] = yt_dlp_download_list(list_url, output_dir=EXPORT_PATH)
logger.info(f"✅ Playlist（{len(video_paths)} videos） downloaded to {EXPORT_PATH}:")

for video_path in video_paths:
     logger.info(f"{video_path.stem}{video_path.suffix}")
     
# video_paths = list(EXPORT_PATH.glob("*.mp4"))

# for video_path in video_paths:
#     logger.info(f"Processing video: {video_path}")
#     name = video_path.stem

#     export_dir = EXPORT_PATH / name
#     export_dir.mkdir(parents=True, exist_ok=True)

#     logger.info(f"📁 Export directory created at {export_dir}")

#     new_video_path = export_dir / video_path.name
#     os.rename(video_path, new_video_path)
#     video_path = new_video_path

#     logger.info(f"📹 Video moved to export directory: {video_path}")
