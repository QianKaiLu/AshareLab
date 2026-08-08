---
name: qk-video2anki
description: 将视频 URL 转化为 Anki 记忆闪卡。自动下载视频 → 语音转文字稿 → AI 提取核心观点 → 生成 Anki 知识点卡片。触发场景：(1) 用户提供视频链接（B站/YouTube等）并要求生成 Anki 卡片 (2) 用户说「把这个视频做成卡片」「视频转Anki」「视频知识点提取」「从视频提取闪卡」等 (3) 用户输入 /qk-video2anki 并提供视频URL。支持 count=N 参数指定期望卡片张数（如 count=5、3张）。
---

# QK Video2Anki — 视频观点 → Anki 闪卡

## 概述

将视频内容转化为 Anki 闪卡的端到端流水线：**视频下载 → 语音转字幕 → AI 整理文章 → 提取核心观点 → 生成 Anki 卡片**。

视频处理由 `cli/video_process/` 的 `video-process` CLI 完成（需 conda `stock` 环境），卡片创建复用 `qk-anki` 的 AnkiConnect 脚本和缓存机制。

## 进度输出规范

流水线耗时长（视频下载 + 转录 + AI 文章可能需要数分钟），**每个阶段必须向用户输出当前进度**，让用户了解发生了什么、还需要等多久。使用以下格式：

```
## Step N: 阶段名称
简短说明当前在做什么...
[执行命令/处理中...]
✅/❌ 结果 + 关键信息
```

**各阶段必须输出的信息：**

| 阶段 | 必须输出的内容 |
|------|--------------|
| Step 1 开始 | `🎬 开始处理视频: <URL>（下载+转录+AI文章，预计3-10分钟）` |
| Step 1 完成 | `✅ 视频处理完成` + 产物目录、文章文件名 |
| Step 2 开始 | `📖 读取文章，提取核心观点（count=N）` |
| Step 2 完成 | 列出提取的 N 个核心观点主题（一行一个） |
| Step 3 开始 | `📝 确定卡组: xxx，卡片类型分配...` |
| Step 4 开始 | `🔗 检查 AnkiConnect...` + 连接状态 |
| Step 4 写入 | `💾 正在写入 Anki...` |
| Step 4 完成 | `✅ 成功写入 N 张卡片` + `🔄 已触发 Anki 同步` |
| Step 4 降级 | `⚠️ AnkiConnect 未连接，已将 N 张卡片写入缓存` |
| Step 5 | 结果汇总表格（视频标题、主题、卡组、卡片列表） |

**禁止：** 在流水线执行过程中沉默。即使只是等待命令返回，也要先告诉用户在等什么。

## 核心流程

```
用户提供视频 URL + 可选 count=N
  ↓
[1] 调用 video-process 处理视频（conda stock 环境）
    → 产出 .md 文章文件
  ↓
[2] 读取文章内容，提取视频的核心观点/知识点
    → 按 count=N 调整粒度
  ↓
[3] 确定卡组（根据视频主题） + 选择卡片类型
  ↓
[4] 生成 Anki 卡片  →  AnkiConnect 写入 / 本地缓存
  ↓
[5] 反馈结果
```

## Step 1: 处理视频

### 进度输出

```
## Step 1: 处理视频
🎬 开始处理视频: <URL>（下载+转录+AI文章，预计3-10分钟）
[等待 video-process 运行...]
✅ 视频处理完成，产物目录: ~/stock/ashare_datas/<视频标题>/
   - 文章: <视频标题>.md
```

### 调用方式

必须通过 conda `stock` 环境运行 `video-process`，使用 `--no-open` 禁止自动打开文件夹：

```bash
conda run -n stock video-process "<视频URL>" --no-open
```

默认输出目录为 `~/stock/ashare_datas`，每个视频会在其下创建以视频标题命名的子文件夹，产物结构：

```
~/stock/ashare_datas/
└── 视频标题/
    ├── 视频标题.mp4    # 下载的视频
    ├── 视频标题.wav    # 提取的音频
    ├── 视频标题.srt    # Whisper 转录字幕
    └── 视频标题.md     # AI 整理的文章 ← 这是后续步骤的输入
```

### 处理选项

| 场景 | 命令参数 |
|------|---------|
| 正常处理（下载+转录+文章） | `video-process <URL> --no-open` |
| 已有视频，跳过下载 | `video-process <URL> --no-open --skip-download` |
| 只需字幕，不调用 AI 写文章 | `video-process <URL> --no-open --skip-article` |
| 英文视频 | `video-process <URL> --no-open -l en` |

### 断点续传

`video-process` 会自动检测已存在的中间产物并跳过对应步骤。如果处理中断，重新运行相同命令即可从断点继续。

### 定位输出文件

命令执行完毕后，在输出目录下找到 `.md` 文章文件。若使用了 `--skip-article`，则使用 `.srt` 字幕文件作为输入。

```bash
# 找到最新生成的文章
ls -t ~/stock/ashare_datas/*/*.md | head -1
```

### 跳过 AI 文章的情况

当使用 `--skip-article` 时，得到的 `.srt` 字幕可能很长（包含大量口语化内容）。此时先用 AI 自行整理 SRT 为结构化文章，再进行知识提取。

## Step 2: 提取核心观点

### 进度输出

```
## Step 2 & 3: 提取核心观点 & 确定卡组
📖 读取文章，提取核心观点（count=N）
已识别 N 个核心观点:
  1. 观点主题一
  2. 观点主题二
  ...
📝 视频主题: xxx → 卡组: xxx
```

先输出初步提取的观点主题列表，再开始生成完整卡片内容。

视频内容与普通文档不同，具有**叙事结构**（引入 → 论证 → 案例 → 结论）。提取知识原子时侧重：

- **核心论点/观点**：视频作者想传达的主要信息
- **关键框架/模型**：作者提出的思维框架或分析模型
- **反直觉认知**：与常识相悖的见解
- **可操作建议**：明确的行动指南或方法
- **重要数据/事实**：支撑论点的关键数据
- **核心概念定义**：作者对关键术语的定义

**忽略：**
- 过渡性内容、寒暄、铺垫
- 纯案例叙述（除非案例本身是知识）
- 广告、求关注等非内容部分

### count 参数

- **count 小（如 3）**：只提取最核心的几个观点，每个观点包含较完整的论证链
- **count 大（如 8-10）**：细化拆分，每个知识点独立成卡
- **未指定 count**：根据视频内容体量自主判断，默认 4-6 张

## Step 3: 确定卡组与卡片类型

### 卡组选择

根据视频主题归入 qk-anki 的核心卡组体系：

| 视频主题 | 卡组 | 示例子卡组 |
|---------|------|-----------|
| 投资/交易/市场 | `Invest` | `Invest::Trading`、`Invest::Stocks` |
| 编程/AI/技术 | `Tech` | `Tech::Python`、`Tech::AI` |
| 个人成长/效率 | `Life` | `Life::Habits`、`Life::Learning` |
| 工作/业务 | `Work` | `Work::Strategy`、`Work::Management` |

不确定时选择最接近的核心卡组，不追求过度细分。

### 卡片类型

按知识形态匹配（详见 qk-anki SKILL.md Step 3）：

- 观点/定义/解释 → **Basic**（`Basic`，字段 `Front`/`Back`）
- 关键术语/参数/数据 → **Cloze**（`填空题`，字段 `文字`/`背面额外`）
- 需双向记忆的核心概念 → **Reversed**（`问答题（附翻转卡片）`，字段 `正面`/`背面`）

## Step 4: 生成并写入卡片

### 进度输出

```
## Step 4: 生成并写入卡片
🔗 检查 AnkiConnect... ✅ 可用 / ⚠️ 不可用
💾 正在写入 Anki（N 张卡片）...
✅ 成功写入 N 张卡片，失败 M 张
🔄 已触发 Anki 同步
```

或降级场景：

```
⚠️ AnkiConnect 未连接，已将 N 张卡片写入缓存
请启动 Anki 后使用 /qk-anki sync 同步
```

### 卡片内容规范

遵循 qk-anki 的卡片规范，并针对视频内容做以下调整：

- **正面加主题标签**：`【卡组名 · 视频主题】<br>` 开头，帮助复习时定位来源
- **背面/背面额外包含上下文**：视频观点需要保留论证逻辑链，不能只有一个结论句
- **引用视频时间戳**：在背面末尾可选添加 `📹 来源: 《视频标题》` 作为参考

示例：

```json
{
  "deckName": "Invest::Trading",
  "modelName": "Basic",
  "fields": {
    "Front": "【Invest::Trading · 止损】<br>为什么多数散户的止损设置方式是错的？",
    "Back": "<b>常见错误：按固定百分比止损（如-5%）</b><br><br>问题在于百分比是主观的，与市场波动无关。正确做法是<b>按技术位止损</b>——支撑位下方、趋势线下方、或ATR的倍数。<br><br><b>核心逻辑：</b>止损应该放在「如果被触发，说明你的判断错了」的位置，而非「你亏了多少钱」的位置。<br><br>📹 来源: 《止损的正确姿势》"
  },
  "tags": ["trading", "risk-management"]
}
```

### 写入 Anki

引用 qk-anki 的脚本（位于 `/Users/qianqian/.claude/skills/qk-anki/scripts/`）：

```python
import sys
sys.path.insert(0, "/Users/qianqian/.claude/skills/qk-anki/scripts")

from anki_client import check_connection, ensure_deck, add_notes, sync, get_model_fields
from cache_manager import add_to_cache, format_cache_summary

# 1. 检查 AnkiConnect
if check_connection():
    # 确认模型字段名（不同语言 Anki 字段名不同）
    # 详见 qk-anki SKILL.md Step 3.5
    fields_basic = get_model_fields("Basic")
    fields_cloze = get_model_fields("填空题")

    # 2. 确保卡组存在
    for deck in set(c["deckName"] for c in cards):
        ensure_deck(deck)

    # 3. 批量创建
    result = add_notes(cards)
    success = sum(1 for nid in result if nid is not None)

    # 4. 同步
    sync()
else:
    # 降级为缓存
    add_to_cache(cards, source=f"视频: {video_title}")
    print(format_cache_summary())
```

**重要：** 创建卡片前必须用 `get_model_fields()` 确认模型字段名。当前用户 Anki 环境的字段映射见 qk-anki SKILL.md Step 3.5 的表格。

### 缓存降级

AnkiConnect 不可用时，卡片写入本地缓存 `~/.anki_cache/pending_cards.json`，告知用户后续用 `/qk-anki sync` 同步。

## Step 5: 反馈结果

### 进度输出

用表格形式汇总结果，清晰展示所有卡片信息：

```
## Step 5: 反馈结果

### ✅ 视频→Anki 流水线完成

| 项目 | 详情 |
|------|------|
| 视频标题 | xxx |
| 视频主题 | xxx |
| 卡组 | xxx |
| 卡片数量 | N 张（全部写入 Anki / M张缓存） |
| 写入方式 | AnkiConnect 直接写入 / 本地缓存 |

### 📇 已生成的 N 张卡片

| # | 类型 | 问题/正面 |
|---|------|----------|
| 1 | Basic | 问题内容... |
| 2 | Cloze | 填空内容... |
| ... | ... | ... |

> 💡 打开 Anki 即可开始复习。若卡片未出现，点「同步」按钮手动刷新。
```

向用户报告：
- 视频信息（标题、主题）
- 生成了多少张卡片
- 每张卡的类型和正面/问题内容（表格形式）
- 归入的卡组
- 写入方式（AnkiConnect / 缓存）
- 若为缓存模式，提醒 `/qk-anki sync`

## 常见场景

### 场景 1：处理新视频

```
用户: 这个B站视频帮我做成Anki卡片 https://www.bilibili.com/video/BV1xxXXXXXXX count=5
```

→ 完整流水线：下载 → 转录 → 文章 → 5张核心观点卡片

### 场景 2：已有字幕，跳过AI文章

```
用户: /qk-video2anki https://www.youtube.com/watch?v=XXXX --skip-article count=8
```

→ 跳过 AI 文章转换，直接用 SRT 字幕提取 8 张知识点卡片

### 场景 3：缓存同步

```
用户: 之前那个视频的卡片还在缓存吗？帮我同步到 Anki
```

→ 使用 `/qk-anki sync` 流程同步缓存

### 场景 4：本地已有视频

```
用户: 把我下载好的视频转成卡片，在 ~/stock/ashare_datas 里
```

→ 使用 `--skip-download` 跳过下载，直接处理已有视频

## 依赖

- **conda `stock` 环境**：`video-process` CLI 已安装
- **ffmpeg**：音频提取必需（`brew install ffmpeg`）
- **mlx-whisper**：Apple Silicon 语音转录
- **Anki + AnkiConnect 插件**：卡片写入目标（不可用则缓存）

## 注意事项

- 视频处理耗时较长（下载 + 转录 + AI 文章），尤其是长视频，需告知用户预期等待时间
- `video-process` 默认使用 `large-v3` 模型，中文转录精度最高但较慢
- 若视频之前已处理过（产物已存在），`video-process` 会自动跳过已完成的步骤
- 卡片内容聚焦**观点和认知**，不机械摘抄字幕原文
- 卡组和模板选择遵循 qk-anki 规范，优先记忆效果而非类型多样性
