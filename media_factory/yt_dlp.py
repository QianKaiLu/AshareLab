from pathlib import Path
import yt_dlp

def yt_dlp_download(url: str, output_dir: Path) -> Path:
    """
    Downloads a video from the given URL using yt-dlp and saves it to the specified output directory.
    Returns the path to the downloaded video file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': str(output_dir / '%(title)s.%(ext)s'),
        'cookiesfrombrowser': ('chrome',), 
        'merge_output_format': 'mp4',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info_dict)
        video_path = Path(filename)
        return video_path

def yt_dlp_download_urls(urls: list[str], output_dir: Path) -> list[Path]:
    """
    Downloads multiple videos from the given list of URLs using yt-dlp and saves them to the specified output directory.
    Returns a list of paths to the downloaded video files.
    """
    downloaded_paths = []
    for url in urls:
        try:
            video_path = yt_dlp_download(url, output_dir)
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            continue
        else:
            downloaded_paths.append(video_path)
    return downloaded_paths

def yt_dlp_download_audio(url: str, output_dir: Path) -> Path:
    """
    Downloads audio from the given URL using yt-dlp and saves it to the specified output directory.
    Returns the path to the downloaded audio file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_dir / '%(title)s.%(ext)s'),
        'cookiesfrombrowser': ('chrome',), 
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            },
            {
                'key': 'EmbedThumbnail',
                'already_have_thumbnail': False,
            },
            {
                'key': 'FFmpegMetadata',
            },
            ],
        'writethumbnail': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info_dict)
        audio_path = Path(filename).with_suffix('.mp3')
        return audio_path
    
if __name__ == "__main__":
    download_url = "https://www.bilibili.com/video/BV1Jm2LBbE1w"
    output_directory = Path("/Users/qianqian/Downloads")
    audio_file_path = yt_dlp_download_audio(download_url, output_directory).resolve()
    print(f"Audio downloaded to: {audio_file_path}")