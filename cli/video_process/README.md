# video-process — 视频下载 & 语音转字幕 CLI 工具

对任意视频 URL 执行完整流水线：**下载 → 提取音频 → Whisper 语音转字幕（SRT）**。

## 安装

```bash
cd AshareLab
pip install -e .
```

安装后，`video-process` 命令即可全局使用。

### 依赖

- **ffmpeg**：音频提取 & 分段必需
  ```bash
  brew install ffmpeg
  ```
- **mlx-whisper**：Apple Silicon 优化的语音转录（仅 macOS）
  ```bash
  pip install mlx-whisper
  ```

## 用法

```bash
video-process <视频URL> [选项]
```

### 基本示例

```bash
# 最简单的用法：下载 B 站视频，提取音频，转录为 SRT
video-process https://www.bilibili.com/video/BV1xxXXXXXXX

# 指定输出目录
video-process https://www.bilibili.com/video/BV1xxXXXXXXX -o ~/my_work_dir

# 英文视频
video-process https://www.youtube.com/watch?v=XXXXXX -l en -m small

# 只下载音频（不下载视频画面）
video-process https://www.bilibili.com/video/BV1xxXXXXXXX --audio-only

# 已有视频文件，跳过下载直接转录
video-process https://example.com/video --skip-download -o ~/my_videos/

# 调试模式（显示详细日志）
video-process https://www.bilibili.com/video/BV1xxXXXXXXX -v
```

### 终端输出示例

```
  ╔══════════════════════════════════════════╗
  ║     🎬  视频处理流水线                     ║
  ╚══════════════════════════════════════════╝
  ▶  输出目录: /Users/qianqian/stock/ashare_datas
  ▶  模型: large-v3  |  语言: zh

  [1/3] 📥 下载视频
  ──────────────────────────────────────────
    URL: https://www.bilibili.com/video/BV1xxXXXXXXX
    文件: 视频标题.mp4  (156.3 MB)
  ✓  下载视频完成 (23.5s)

  [2/3] 🎵 提取音频
  ──────────────────────────────────────────
    源视频: 视频标题.mp4
    输出: 视频标题.wav  (78.1 MB)
  ✓  提取音频完成 (12.3s)

  [3/3] 📝 语音转字幕
  ──────────────────────────────────────────
    音频: 视频标题.wav  (78.1 MB)
    模型: large-v3
    语言: zh
    模式: 长音频分段
    分段: 20 分钟/段
  ...whisper 转录进度...
    输出: 视频标题.srt  (45.2 KB)
  ✓  语音转字幕完成 (180.5s)

  ╔══════════════════════════════════════════╗
  ║     ✅  处理完成                           ║
  ╚══════════════════════════════════════════╝
  ▶  输出目录: /Users/qianqian/stock/ashare_datas
  ▶  视频文件: 视频标题.mp4  (156.3 MB)
  ▶  音频文件: 视频标题.wav  (78.1 MB)
  ▶  字幕文件: 视频标题.srt  (45.2 KB)
  ▶  总耗时: 216.3s

  💡 下一步: 可用任意文本编辑器打开 视频标题.srt
```

> 颜色方案：阶段标题 = 青色粗体，完成 = 绿色粗体，详细信息 = 白色，警告 = 黄色，错误 = 红色。**无冗余时间戳**，保持终端干净。

### 全部参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `url` | 视频 URL（位置参数），支持 Bilibili、YouTube 等 | **必填** |
| `-o, --output-dir` | 工作目录，所有输出保存在此 | `~/stock/ashare_datas` |
| `-m, --model` | Whisper 模型大小 | `large-v3` |
| `-l, --language` | 音频语言代码 | `zh` |
| `--prompt` | Whisper 提示词，引导识别特定词汇 | （空） |
| `--segment-minutes` | 长音频分段转录时每段时长（分钟） | `20` |
| `--keep-segments` | 保留中间分段文件（调试用） | 关闭 |
| `--skip-download` | 跳过下载，使用已有视频 | 关闭 |
| `--skip-audio-extract` | 跳过音频提取，使用已有 wav | 关闭 |
| `--skip-transcribe` | 跳过转录（仅下载+提取） | 关闭 |
| `--audio-only` | 直接下载音频而非完整视频 | 关闭 |
| `--no-long-mode` | 关闭长音频分段，一次转录全部 | 关闭 |
| `-v, --verbose` | 显示详细日志（含调试信息） | 关闭 |

### Whisper 模型选择

| 模型 | 大小 | 速度 | 精度 |
|------|------|------|------|
| `tiny` | ~150MB | ⚡⚡⚡ | ★ |
| `base` | ~250MB | ⚡⚡ | ★★ |
| `small` | ~1GB | ⚡ | ★★★ |
| `medium` | ~3GB | 🐢 | ★★★★ |
| `large-v3` | ~4GB | 🐢🐢 | ★★★★★ |

> 推荐：中文长视频用 `large-v3`，英文短视频可用 `small`/`medium`。

## 输出

所有文件保存在 `--output-dir` 目录下：

```
~/stock/ashare_datas/
├── 视频标题.mp4          # 下载的视频（或 .mp3 如果 --audio-only）
├── 视频标题.wav          # 提取的音频（PCM 16-bit 单声道）
└── 视频标题.srt          # 转录字幕文件
```

### SRT 字幕格式

标准 SRT 格式，每段字幕包含序号、时间码和文本：

```
1
00:00:01,200 --> 00:00:04,500
这是第一段字幕内容

2
00:00:05,100 --> 00:00:08,300
这是第二段字幕内容
```

> **时间码格式**: `HH:MM:SS,mmm`（时:分:秒,毫秒）

## 流水线步骤

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ 1. 下载  │ ──▶ │ 2. 提取  │ ──▶ │ 3. 转录  │
│ yt-dlp   │     │ moviepy  │     │ mlx-whisper│
│   → mp4  │     │   → wav  │     │   → srt   │
└──────────┘     └──────────┘     └──────────┘
```

- **长音频自动分段**：超过 `--segment-minutes` 分钟的音频会被自动切分为多个片段、分别转录后合并，避免内存溢出。
- **断点续传**：每步都会检查输出文件是否已存在，存在则跳过。适合中断后继续运行。
- **文件大小显示**：每个阶段完成后展示文件大小，方便判断数据量。

## 日志系统

- **控制台**：纯消息 + 颜色，**无时间戳**，干净美观。INFO 及以上级别默认输出。
- **文件**：`logs/analyze.log`，记录 WARNING 及以上级别的完整日志（含时间戳），用于排查问题。
- **第三方库静默**：yt-dlp、moviepy 等库的调试输出会被自动抑制，避免干扰。

## 常见问题

### 报错 `ffmpeg not found`

安装 ffmpeg：
```bash
brew install ffmpeg
```

### 报错 `Failed to load video file`

- 视频文件损坏或格式不支持，尝试重新下载
- URL 可能需要登录才能访问

### 报错 `The video file does not contain an audio track`

视频没有音频轨道（如纯画面视频），无法提取音频。

### B 站视频下载失败

yt-dlp 需要有浏览器 cookie 才能下载部分 B 站视频。确保：
- Chrome 已安装且登录了 B 站
- 或使用 `--cookies-from-browser` 参数（代码默认使用 Chrome cookie）

### 转录质量差

- 尝试更大的模型：`-m large-v3`
- 设置正确的语言：`-l en` / `-l ja` 等
- 使用 `--prompt` 引导模型识别特定术语

### Apple Silicon 以外的 Mac

`mlx-whisper` 仅支持 Apple Silicon（M 系列芯片）。Intel Mac 请使用其他 whisper 实现。

## 开发

```bash
# 直接运行（无需安装）
python cli/video_process/main.py <URL> [选项]
```
