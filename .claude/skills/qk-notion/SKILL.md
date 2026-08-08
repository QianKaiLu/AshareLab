---
name: qk-notion
description: 将内容写入 Notion。支持 Markdown 文件、网页URL、stdin 或纯文本。调用 qk-notion CLI 写入 Notion 页面。触发场景：(1) 用户要求将内容保存到 Notion (2) 用户说「写入notion」「保存到notion」「notion笔记」「添加到notion」等 (3) 用户提供网页链接要求抓取并存入 Notion (4) 用户输入 /qk-notion write 并提供内容来源 (5) 用户要求查看 Notion 页面结构或子页面列表。支持 --dry-run 预览、-t 指定标题、-p 指定父页面。
---

# QK Notion — 内容写入 Notion

## 概述

将任意内容写入 Notion 页面。底层调用 `qk-notion` CLI（需 conda `stock` 环境），自动识别输入类型（文件/URL/stdin/文本）并写入。

## 三个子命令

| 子命令 | 功能 |
|--------|------|
| `write` | 将内容写入 Notion（文件/URL/stdin/文本） |
| `children` | 列出子页面结构 |
| `batch` | 批量导入（文件 glob 或 URL 列表） |

## write — 写入内容

### 基本用法

```bash
conda run -n stock qk-notion write <source> -p <parent_page_id>
```

### 输入来源自动识别

| 输入 | 行为 |
|------|------|
| `https://...` | 自动抓取网页 → 转 Markdown → 写入 |
| `docs/notes.md` | 读取文件 → 写入 |
| `-` | 从标准输入读取 → 写入 |
| 普通文本 | 直接作为 Markdown 写入 |

### 关键参数

| 参数 | 说明 |
|------|------|
| `-p PAGE_ID` | 父页面 ID（创建子页面） |
| `-d DB_ID` | 数据库 data_source ID（创建数据库条目，与 -p 互斥） |
| `-t TITLE` | 显式标题（缺省时从 # H1 提取） |
| `--dry-run` | 预览不写入 |
| `--token TOKEN` | Notion token（默认读 `$NOTION_TOKEN`） |

### 标题处理

- 优先使用 `-t` 指定的标题
- 未指定则自动从内容的 `# H1` 提取
- 两者都没有时警告，但不阻止写入

### 进度输出

- 输入加载时：`📄 读取文件: xxx` / `🌐 抓取网页: xxx`
- 成功时：`✅ 创建成功` + URL + 标题
- 失败时：`❌ 创建失败: 错误信息`

## children — 查看页面结构

```bash
conda run -n stock qk-notion children <page_id>
conda run -n stock qk-notion children <page_id> -r          # 递归
conda run -n stock qk-notion children <page_id> -r --flat   # 扁平列表
```

## batch — 批量导入

```bash
# 批量导入文件
conda run -n stock qk-notion batch -f "output/*.md" -p <page_id>

# 批量导入 URL（urls.txt 每行一个，# 开头为注释）
conda run -n stock qk-notion batch -u urls.txt -p <page_id>

# 预览模式
conda run -n stock qk-notion batch -f "output/*.md" --dry-run
```

## 常见场景

### 场景 1：将对话/生成的内容写入 Notion

```
用户: 把我们刚才讨论的这些内容保存到 Notion
```

→ Claude 整理内容为 Markdown → `echo "..." | conda run -n stock qk-notion write - -p <page_id>`

### 场景 2：网页文章保存

```
用户: 这篇文章帮我存到 Notion https://mp.weixin.qq.com/s/xxxx
```

→ `conda run -n stock qk-notion write https://mp.weixin.qq.com/s/xxxx -p <page_id>`

### 场景 3：Markdown 文件导入

```
用户: 把 output/*.md 批量导入到我的 Notion 笔记里
```

→ `conda run -n stock qk-notion batch -f "output/*.md" -p <page_id>`

### 场景 4：查看页面结构

```
用户: 看看我的 Notion 笔记下面有哪些子页面
```

→ `conda run -n stock qk-notion children <page_id> -r`

### 场景 5：预览（不实际写入）

```
用户: 先看看这个网页转成什么样再决定要不要保存
```

→ 加 `--dry-run` 预览

## 依赖

- **conda `stock` 环境**：`qk-notion` CLI 已安装
- **`$NOTION_TOKEN`**：Notion API token（`.env` 或 `--token` 指定）
- **Playwright**：网页抓取需要（`pip install playwright && playwright install chromium`）
- **Notion 集成**：需在 Notion 中将目标页面授权给集成

## 注意事项

- 写入前确认 `-p` 或 `-d` 已提供，否则 CLI 会报错
- 网页抓取依赖 Playwright，首次需 `playwright install chromium`
- 网页抓取耗时较长（每个 URL 需数秒渲染），批量时用 `-c` 控制并发
- Notion API 速率限制约 3 req/s，默认 `-c 3`
- `batch` 目前只支持写入到父页面（`-p`），不支持数据库
