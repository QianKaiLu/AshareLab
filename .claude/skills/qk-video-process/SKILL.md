---
name: qk-video-process
description: 视频下载+语音转字幕+AI整理文章流水线。调用 video-process CLI 将视频URL转化为Markdown文章。触发场景：(1) 用户提供视频链接（B站/YouTube等）要求下载、转字幕、整理文章 (2) 用户说「处理这个视频」「视频转文章」「视频转文字」「下载并转录」「提取字幕」等 (3) 用户输入 /qk-video-process 并提供视频URL。支持 --skip-download、--skip-article、--audio-only、-l en 等参数。
---

# QK Video Process — 视频→文章流水线

## 概述

对任意视频 URL 执行完整流水线：**下载 → 提取音频 → Whisper 语音转字幕 → AI 整理文章**。纯视频处理，不含卡片生成。

底层调用 `cli/video_process/` 的 `video-process` CLI（需 conda `stock` 环境）。

## 核心流程

```
用户提供视频 URL + 可选参数
  ↓
调用 video-process 处理视频（conda stock 环境）
  ↓
产出 .srt 字幕 + .md 文章
  ↓
反馈结果（产物路径、文件大小）
```

## 调用方式

必须通过 conda `stock` 环境运行，始终使用 `--no-open` 以避免弹出文件夹：

```bash
conda run -n stock video-process "<视频URL>" --no-open
```

## 常用参数

| 参数 | 说明 | 适用场景 |
|------|------|---------|
| `--no-open` | 不自动打开输出文件夹 | **始终使用** |
| `--skip-download` | 跳过下载，使用已有视频 | 视频已下载到本地 |
| `--skip-article` | 跳过 AI 文章生成，仅输出 SRT | 只需要字幕 |
| `--audio-only` | 仅下载音频（不下载视频画面） | 节省带宽 |
| `-l en` | 指定音频语言为英文 | 英文视频 |
| `-m small` | 使用较小 Whisper 模型 | 英文视频或追求速度 |
| `-o <path>` | 指定输出目录 | 自定义输出位置 |
| `-v` | 显示详细日志 | 调试时使用 |

## 进度输出

流水线耗时较长，必须在各阶段输出进度：

- 调用前：`🎬 开始处理视频: <URL>（预计3-10分钟）`
- 处理中：直接显示 `video-process` 的终端输出（自带进度和颜色）
- 完成后：列出产物路径和文件大小

## 产物结构

默认输出目录 `~/stock/ashare_datas`，每个视频在独立子文件夹中：

```
~/stock/ashare_datas/
└── 视频标题/
    ├── 视频标题.mp4    # 下载的视频
    ├── 视频标题.wav    # 提取的音频（PCM 16-bit 单声道）
    ├── 视频标题.srt    # Whisper 转录字幕
    └── 视频标题.md     # AI 整理的文章（# 一级标题开头）
```

## 断点续传

`video-process` 自动检测已存在的产物并跳过对应步骤。中断后重新运行相同命令即可续传。

## 常见场景

### 场景 1：标准流水线

```
用户: 帮我把这个视频转成文章 https://www.bilibili.com/video/BV1xxXXXXXXX
```

→ `conda run -n stock video-process "<URL>" --no-open`

### 场景 2：英文视频

```
用户: 处理这个YouTube视频 https://www.youtube.com/watch?v=XXXX
```

→ `conda run -n stock video-process "<URL>" --no-open -l en`

### 场景 3：只需字幕

```
用户: 帮我提取这个视频的字幕，不用AI整理 https://www.bilibili.com/video/BV1xxXXXXXXX
```

→ `conda run -n stock video-process "<URL>" --no-open --skip-article`

### 场景 4：本地已有视频

```
用户: 这个视频我下载好了在 ~/stock/ashare_datas/视频标题/ 里，帮我转录
```

→ `conda run -n stock video-process "<URL>" --no-open --skip-download`

### 场景 5：自定义输出目录

```
用户: 视频转文章输出到 ~/Downloads/video_notes/
```

→ `conda run -n stock video-process "<URL>" --no-open -o ~/Downloads/video_notes/`

## 依赖

- **conda `stock` 环境**：`video-process` CLI 已安装
- **ffmpeg**：音频提取必需（`brew install ffmpeg`）
- **mlx-whisper**：Apple Silicon 语音转录（仅 M 系列芯片）
- **AI API**：字幕转文章步骤需 DeepSeek API（`.env` 中配置）

## 注意事项

- 默认使用 `large-v3` Whisper 模型，中文精度最高但需 ~4GB 内存
- 长视频（>20分钟）自动分段转录
- 首次使用某模型会自动下载（耗时较长）
- 处理完成后不自动打开文件夹（已使用 `--no-open`）
