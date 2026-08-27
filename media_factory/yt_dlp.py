from pathlib import Path
import yt_dlp

def yt_dlp_download(url: str, output_dir: Path) -> Path:
    """
    Downloads a video from the given URL using yt-dlp and saves it to the specified output directory.
    Returns the path to the downloaded video file.

    合集/多分 P URL 会一次下载全部条目。文件路径取自 postprocess 钩子的实际产物，
    不用 prepare_filename 猜测——后者对合集返回的路径可能不存在（如 .NA 后缀）。
    多分 P 时返回文件名序第一个，其余路径打到日志；要处理其他分 P 给 URL 加 ?p=N。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: dict[str, Path] = {}

    def postprocess_hook(d):
        if d['status'] == 'finished':
            file_path = d.get('info_dict', {}).get('filepath')
            if file_path:
                downloaded[Path(file_path).name] = Path(file_path)

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': str(output_dir / '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'postprocessor_hooks': [postprocess_hook],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not downloaded:
        raise FileNotFoundError(f"yt-dlp 未产出任何文件: {url}")

    paths = sorted(downloaded.values())
    if len(paths) > 1:
        print(f"[yt_dlp] 合集 URL 下载了 {len(paths)} 个分 P，返回第 1 个: {paths[0].name}")
        print(f"[yt_dlp] 其余分 P: {', '.join(p.name for p in paths[1:])}")
    return paths[0]


def yt_dlp_download_list(
    url: str,
    output_dir: Path,
    index_format: str = "%(playlist_index)02d_",
) -> list[Path]:
    """
    Downloads videos from a playlist URL using yt-dlp and saves them to the specified output directory.
    The downloaded files are prefixed with their index in the playlist.
    Returns a list of paths to the downloaded video files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded_paths = []

    def postprocess_hook(d):
        if d['status'] == 'finished':
            file_path = d.get('info_dict', {}).get('filepath')
            if file_path:
                downloaded_paths.append(Path(file_path))

    outtmpl_str = str(output_dir / f"{index_format}%(title)s.%(ext)s")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': outtmpl_str,
        'merge_output_format': 'mp4',
        'ignoreerrors': True,
        'noplaylist': False,
        'postprocessor_hooks': [postprocess_hook],
        'quiet': False, 
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return downloaded_paths

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