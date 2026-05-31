"""
视频处理命令行工具：下载 → 提取音频 → 语音转字幕

用法:
    video-process <视频URL> [选项]

示例:
    video-process https://www.bilibili.com/video/BV1xxXXXXXXX
    video-process https://www.bilibili.com/video/BV1xxXXXXXXX -o ~/my_output
    video-process https://www.bilibili.com/video/BV1xxXXXXXXX -m medium -l en
    video-process https://www.youtube.com/watch?v=XXXXXX --skip-download
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import colorlog

# 将项目根目录加入 sys.path，确保能找到各模块
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from media_factory.yt_dlp import yt_dlp_download
from media_factory.video_handler import extract_audio_from_video
from media_factory.whisper_mlx import whisper_to_srt_long, whisper_to_srt, VALID_MODELS

DEFAULT_OUTPUT_DIR = Path.home() / "stock" / "ashare_datas"


# ══════════════════════════════════════════════════════════════════════════════
# CLI 专用日志系统 —— 干净、美观、无冗余时间戳
# ══════════════════════════════════════════════════════════════════════════════

LOG_COLORS = {
    "DEBUG":    "bold_cyan",
    "INFO":     "white",
    "WARNING":  "bold_yellow",
    "ERROR":    "bold_red",
    "CRITICAL": "bg_bold_red,white",
    "STAGE":    "bold_cyan",
    "SUCCESS":  "bold_green",
    "PROGRESS": "bold_white",
}

# 注册自定义日志级别（在标准 INFO=20 附近扩展）
STAGE_LEVEL = 25
SUCCESS_LEVEL = 21
PROGRESS_LEVEL = 15

logging.addLevelName(STAGE_LEVEL, "STAGE")
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")
logging.addLevelName(PROGRESS_LEVEL, "PROGRESS")


def _stage(self, message, *args, **kwargs):
    if self.isEnabledFor(STAGE_LEVEL):
        self._log(STAGE_LEVEL, message, args, **kwargs)


def _success(self, message, *args, **kwargs):
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kwargs)


def _progress(self, message, *args, **kwargs):
    if self.isEnabledFor(PROGRESS_LEVEL):
        self._log(PROGRESS_LEVEL, message, args, **kwargs)


logging.Logger.stage = _stage
logging.Logger.success = _success
logging.Logger.progress = _progress


def _setup_cli_logger(verbose: bool = False) -> logging.Logger:
    """配置 CLI 专用日志器。控制台输出纯消息无时间戳，文件保留完整时间戳。"""
    logger = logging.getLogger("video_process")
    logger.setLevel(logging.DEBUG if verbose else PROGRESS_LEVEL)
    logger.propagate = False
    logger.handlers.clear()

    # 控制台 handler：纯消息 + 颜色
    console_handler = colorlog.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else PROGRESS_LEVEL)
    console_handler.setFormatter(colorlog.ColoredFormatter(
        fmt="%(log_color)s%(message)s",
        log_colors=LOG_COLORS,
        reset=True,
    ))
    logger.addHandler(console_handler)

    # 文件 handler：完整时间戳，仅 WARNING+
    from tools.log import ANALYZE_LOG_FILE
    file_handler = logging.FileHandler(str(ANALYZE_LOG_FILE), encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(levelname)s - [video_process] %(message)s"
    ))
    logger.addHandler(file_handler)

    return logger


def _suppress_noisy_libs():
    """抑制第三方库的冗余控制台输出。"""
    for name in ("yt_dlp", "moviepy", "PIL", "matplotlib"):
        logging.getLogger(name).setLevel(logging.WARNING)


# ══════════════════════════════════════════════════════════════════════════════
# 辅助工具
# ══════════════════════════════════════════════════════════════════════════════

class StageTimer:
    """带计时的阶段管理器，统一输出风格。"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._start = 0.0
        self._name = ""

    def begin(self, step: int, total: int, name: str, icon: str = "●"):
        self._name = name
        self._start = time.time()
        self.logger.info("")
        self.logger.stage(f"  [{step}/{total}] {icon} {name}")
        self.logger.stage(f"  {'─' * 42}")

    def done(self, detail: str = ""):
        elapsed = time.time() - self._start
        parts = [f"  ✓  {self._name}完成"]
        if detail:
            parts.append(f" · {detail}")
        parts.append(f" ({elapsed:.1f}s)")
        self.logger.success("".join(parts))

    def skip(self, reason: str = ""):
        msg = f"  ○  跳过{self._name}"
        if reason:
            msg += f" · {reason}"
        self.logger.info(msg)


def fmt_size(path: Path) -> str:
    """格式化文件大小（B / KB / MB / GB）。"""
    try:
        size = path.stat().st_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 ** 2:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 ** 3:
            return f"{size / 1024 ** 2:.1f} MB"
        else:
            return f"{size / 1024 ** 3:.2f} GB"
    except OSError:
        return "?"


# ══════════════════════════════════════════════════════════════════════════════
# CLI 参数解析
# ══════════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="视频处理工具：下载视频 → 提取音频 → 语音转字幕（SRT）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s https://www.bilibili.com/video/BV1xxXXXXXXX
  %(prog)s https://www.bilibili.com/video/BV1xxXXXXXXX -o ~/my_output
  %(prog)s https://www.youtube.com/watch?v=XXXXXX -m medium -l en
  %(prog)s https://www.bilibili.com/video/BV1xxXXXXXXX --skip-download --audio-only
        """,
    )

    parser.add_argument(
        "url",
        type=str,
        help="视频 URL（支持 Bilibili、YouTube 等 yt-dlp 支持的平台）",
    )

    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"工作目录，所有输出文件都会放在此目录下。默认: {DEFAULT_OUTPUT_DIR}",
    )

    parser.add_argument(
        "-m", "--model",
        type=str,
        default="large-v3",
        choices=list(VALID_MODELS.keys()),
        help="Whisper 模型大小，越大越准但越慢。默认: large-v3",
    )

    parser.add_argument(
        "-l", "--language",
        type=str,
        default="zh",
        help="音频语言代码。默认: zh（中文）",
    )

    parser.add_argument(
        "--prompt",
        type=str,
        default="",
        help="Whisper 转录提示词，用于引导模型识别特定词汇",
    )

    parser.add_argument(
        "--segment-minutes",
        type=int,
        default=20,
        help="长音频分段转录时每段的最大时长（分钟）。默认: 20",
    )

    parser.add_argument(
        "--keep-segments",
        action="store_true",
        help="保留中间分段文件（调试用）",
    )

    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="跳过下载步骤，直接在 output-dir 中找已有视频文件",
    )

    parser.add_argument(
        "--skip-audio-extract",
        action="store_true",
        help="跳过音频提取步骤，直接使用已有的 .wav 文件",
    )

    parser.add_argument(
        "--skip-transcribe",
        action="store_true",
        help="跳过转录步骤（仅下载和提取音频）",
    )

    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="直接下载音频而非完整视频（使用 yt-dlp 的音频下载）",
    )

    parser.add_argument(
        "--no-long-mode",
        action="store_true",
        help="关闭长音频分段转录，一次性转录整个音频（适用于较短音频）",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细日志（包括调试信息）",
    )

    return parser.parse_args()


# ══════════════════════════════════════════════════════════════════════════════
# 流水线各阶段
# ══════════════════════════════════════════════════════════════════════════════

def _step_download(log: logging.Logger, args: argparse.Namespace,
                   output_dir: Path, timer: StageTimer) -> tuple[Path | None, Path | None]:
    """
    [1/3] 获取视频源。

    Returns:
        (video_path, audio_path): 正常模式返回 (video_path, None);
        audio-only 模式返回 (None, audio_path)
    """
    timer.begin(1, 3, "下载视频", "📥")

    # ── 跳过下载，使用本地文件 ──
    if args.skip_download:
        video_exts = ("*.mp4", "*.mkv", "*.webm", "*.flv", "*.mov", "*.avi")
        existing: list[Path] = []
        for ext in video_exts:
            existing.extend(output_dir.glob(ext))
        if not existing:
            log.error(f"  ✘  在 {output_dir} 中未找到视频文件")
            log.error(f"     支持的格式: {', '.join(video_exts)}")
            raise FileNotFoundError(f"未在 {output_dir} 中找到视频文件")
        video_path = existing[0]
        log.progress(f"    文件: {video_path.name}  ({fmt_size(video_path)})")
        timer.done("使用已有文件")
        return video_path, None

    # ── 纯音频模式 ──
    if args.audio_only:
        from media_factory.yt_dlp import yt_dlp_download_audio
        log.progress(f"    URL: {args.url}")
        audio_path = yt_dlp_download_audio(args.url, output_dir=output_dir)
        log.progress(f"    文件: {audio_path.name}  ({fmt_size(audio_path)})")
        timer.done("仅音频模式")
        return None, audio_path

    # ── 标准下载 ──
    log.progress(f"    URL: {args.url}")
    video_path = yt_dlp_download(args.url, output_dir=output_dir)
    log.progress(f"    文件: {video_path.name}  ({fmt_size(video_path)})")
    timer.done()
    return video_path, None


def _step_extract_audio(log: logging.Logger, args: argparse.Namespace,
                        output_dir: Path, video_path: Path | None,
                        audio_from_dl: Path | None,
                        timer: StageTimer) -> Path:
    """
    [2/3] 获取音频。

    优先级：
      1. 已通过 audio-only 下载的音频
      2. --skip-audio-extract → 找已有 .wav
      3. 已有 .wav 缓存（根据视频名推断）
      4. 从视频提取
    """
    timer.begin(2, 3, "提取音频", "🎵")

    # 情况 A：audio-only 模式已下载
    if audio_from_dl is not None:
        log.progress(f"    源: 直接下载的音频文件")
        timer.done("跳过提取")
        return audio_from_dl

    # 情况 B：用户指定跳过提取
    if args.skip_audio_extract:
        existing_wav = list(output_dir.glob("*.wav"))
        if not existing_wav:
            log.error(f"  ✘  --skip-audio-extract 已指定，但 {output_dir} 中未找到 .wav")
            raise FileNotFoundError(f"未在 {output_dir} 中找到 .wav 音频文件")
        wav_path = existing_wav[0]
        log.progress(f"    文件: {wav_path.name}  ({fmt_size(wav_path)})")
        timer.done("使用已有音频")
        return wav_path

    # 情况 C：需要从视频提取
    if video_path is None:
        log.error("  ✘  没有视频文件可供提取音频")
        raise RuntimeError("无可用视频源进行音频提取")

    wav_path = output_dir / f"{video_path.stem}.wav"
    if wav_path.exists():
        log.progress(f"    文件: {wav_path.name}  ({fmt_size(wav_path)})")
        timer.done("音频已存在")
        return wav_path

    log.progress(f"    源视频: {video_path.name}")
    wav_path = extract_audio_from_video(video_path, output_dir=output_dir)
    log.progress(f"    输出: {wav_path.name}  ({fmt_size(wav_path)})")
    timer.done()
    return wav_path


def _step_transcribe(log: logging.Logger, args: argparse.Namespace,
                     output_dir: Path, audio_path: Path,
                     timer: StageTimer) -> Path | None:
    """
    [3/3] 语音转字幕（Whisper）。
    """
    timer.begin(3, 3, "语音转字幕", "📝")

    if args.skip_transcribe:
        timer.skip("--skip-transcribe")
        return None

    if audio_path is None:
        log.error("  ✘  没有音频文件可供转录")
        raise RuntimeError("无可用音频源进行转录")

    # 已有缓存
    srt_path = output_dir / f"{audio_path.stem}.srt"
    if srt_path.exists():
        log.progress(f"    文件: {srt_path.name}  ({fmt_size(srt_path)})")
        timer.done("字幕已存在")
        return srt_path

    use_long_mode = not args.no_long_mode

    log.progress(f"    音频: {audio_path.name}  ({fmt_size(audio_path)})")
    log.progress(f"    模型: {args.model}")
    log.progress(f"    语言: {args.language}")
    log.progress(f"    模式: {'长音频分段' if use_long_mode else '单次转录'}")
    if use_long_mode:
        log.progress(f"    分段: {args.segment_minutes} 分钟/段")
    if args.prompt:
        log.progress(f"    提示词: {args.prompt}")

    log.info("")  # 空行，分隔 whisper 子模块的输出

    if use_long_mode:
        srt_path = whisper_to_srt_long(
            audio_path=audio_path,
            model_size=args.model,
            output_dir=output_dir,
            language=args.language,
            prompt=args.prompt,
            max_segment_minutes=args.segment_minutes,
            keep_segments=args.keep_segments,
        )
    else:
        srt_path = whisper_to_srt(
            audio_path=audio_path,
            model_size=args.model,
            output_dir=output_dir,
            language=args.language,
            prompt=args.prompt,
        )

    log.progress(f"    输出: {srt_path.name}  ({fmt_size(srt_path)})")
    timer.done()
    return srt_path


# ══════════════════════════════════════════════════════════════════════════════
# 流水线编排
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(args: argparse.Namespace, log: logging.Logger) -> dict:
    """执行完整流水线：下载 → 提取音频 → 转录。"""
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    timer = StageTimer(log)
    total_start = time.time()

    # ── 启动横幅 ──
    log.info("")
    log.stage("  ╔══════════════════════════════════════════╗")
    log.stage("  ║     🎬  视频处理流水线                     ║")
    log.stage("  ╚══════════════════════════════════════════╝")
    log.info(f"  ▶  输出目录: {output_dir}")
    log.info(f"  ▶  模型: {args.model}  |  语言: {args.language}")

    # ── 执行各阶段 ──
    video_path, audio_from_dl = _step_download(log, args, output_dir, timer)
    audio_path = _step_extract_audio(log, args, output_dir, video_path, audio_from_dl, timer)
    srt_path = _step_transcribe(log, args, output_dir, audio_path, timer)

    # ── 完成摘要 ──
    total_elapsed = time.time() - total_start
    _print_summary(log, output_dir, video_path, audio_path, srt_path, total_elapsed)

    return {
        "video_path": video_path,
        "audio_path": audio_path,
        "srt_path": srt_path,
        "output_dir": output_dir,
    }


def _print_summary(log: logging.Logger, output_dir: Path,
                   video_path: Path | None, audio_path: Path | None,
                   srt_path: Path | None, total_elapsed: float) -> None:
    """打印处理结果摘要。"""
    log.info("")
    log.stage("  ╔══════════════════════════════════════════╗")
    log.stage("  ║     ✅  处理完成                           ║")
    log.stage("  ╚══════════════════════════════════════════╝")

    log.info(f"  ▶  输出目录: {output_dir}")
    if video_path:
        log.info(f"  ▶  视频文件: {video_path.name}  ({fmt_size(video_path)})")
    if audio_path:
        log.info(f"  ▶  音频文件: {audio_path.name}  ({fmt_size(audio_path)})")
    if srt_path:
        log.info(f"  ▶  字幕文件: {srt_path.name}  ({fmt_size(srt_path)})")
    log.success(f"  ▶  总耗时: {total_elapsed:.1f}s")

    if srt_path and srt_path.exists():
        log.info("")
        log.info(f"  💡 下一步: 可用任意文本编辑器打开 {srt_path.name}")


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

def main():
    args = parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    log = _setup_cli_logger(verbose=args.verbose)
    _suppress_noisy_libs()

    try:
        run_pipeline(args, log)
    except FileNotFoundError as e:
        log.error("")
        log.error(f"  ✘  文件未找到: {e}")
        log.info(f"  💡 请确认文件是否存在，或去掉 --skip-download / --skip-audio-extract 参数")
        sys.exit(1)
    except ValueError as e:
        log.error("")
        log.error(f"  ✘  参数错误: {e}")
        sys.exit(1)
    except RuntimeError as e:
        log.error("")
        log.error(f"  ✘  运行时错误: {e}")
        log.info(f"  💡 可能的原因:")
        log.info(f"     · 视频 URL 无效或需要登录")
        log.info(f"     · 网络连接问题")
        log.info(f"     · ffmpeg 未安装 → brew install ffmpeg")
        log.info(f"     · 视频没有音频轨道")
        log.info(f"     · 模型未下载（首次使用会自动下载）")
        sys.exit(1)
    except KeyboardInterrupt:
        log.warning("")
        log.warning(f"  ⚠  用户中断操作")
        sys.exit(130)
    except Exception as e:
        log.error("")
        log.error(f"  ✘  未知错误: {type(e).__name__}: {e}")
        log.info(f"  💡 详细错误信息已写入日志文件: logs/analyze.log")
        if args.verbose:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
