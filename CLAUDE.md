# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

AshareLab 是 A 股分析 + 媒体处理的个人工具集，两条相对独立的主线共用一套基础设施（日志、路径、AI 接口）：

1. **股票分析**：行情抓取 → SQLite → 技术指标 → 选股策略（hunter）→ K 线卡片 / AI 研报
2. **内容流水线**：视频下载 → Whisper 转字幕 → AI 整理成 Markdown → 写入 Notion

## 运行环境

代码必须在 conda `stock` 环境下运行。非交互调用统一用：

```bash
conda run -n stock python <script.py>
conda run -n stock video-process "<url>" --no-open
conda run -n stock qk-notion write <source> -p <page_id>
```

脚本以模块路径导入（`from datas.query_stock import ...`），所以直接运行时需要项目根在 `PYTHONPATH` 上。`.vscode/settings.json` 已配置终端 `PYTHONPATH=${workspaceFolder}`；命令行下用 `python -m workflow.hunt_both` 或 `PYTHONPATH=. python workflow/hunt_both.py`。部分 `workflow/` 脚本自己 `sys.path.append` 了根目录，可直接跑。

安装 CLI：`pip install -e .`（注册 `video-process`、`qk-notion`）。

## 常用命令

```bash
# 数据更新（先做这步，其余分析都依赖本地库）
conda run -n stock python datas/create_database.py      # 建表 / 迁移
conda run -n stock python datas/fetch_all_market.py     # 全市场并行抓取
conda run -n stock python workflow/fetch_latest_klines.py

# 选股
conda run -n stock python workflow/hunt_breakout_pullback.py
conda run -n stock python workflow/hunt_wyckoff.py
conda run -n stock python workflow/hunt_both.py         # 两策略取交集

# 可视化 / AI
conda run -n stock python workflow/draw_stock_cards.py
conda run -n stock python workflow/ai_analyses_stock.py

# 视频 → 文章
conda run -n stock video-process "<视频URL>" --no-open
```

**没有测试套件**：仓库里既无 `tests/` 目录也无 pytest 配置。新增测试需要自己搭 `tests/` 并加 pytest 配置。验证改动目前靠直接跑对应的 `workflow/` 脚本看输出。

## 架构要点

### 数据层

所有查询都走 `datas/query_stock.py`，不要在别处写裸 SQL。库固定在 `database/ashare_data.db`（WAL 模式，约 2.4G，不入 git）。

- 价格一律**前复权（qfq）**，表 `stock_bars_daily_qfq`；基础信息表 `stock_base_info`
- 日期以字符串 `YYYYMMDD` 存储，日期运算用 `tools/times.py`
- 抓取以 AKShare 为主、Tushare 兜底；Tushare 限流靠 `config.py` 里的 token 数组 + `tools/tushare_rate_limiter.py` 轮换
- 批量写入用「队列 + 单写线程」模式，避免多线程写 SQLite

### 指标层

`indicators/` 每个模块提供 `add_<name>_to_dataframe(df, inplace=True)`，就地给 DataFrame 加列。分析前先加指标，再判断信号：

```python
df = query_bars_by_days(code, days=500)
add_kdj_to_dataframe(df, inplace=True)      # → kdj_k / kdj_d / kdj_j
add_macd_to_dataframe(df, inplace=True)     # → MACD_DIF / MACD_DEA / MACD_BAR
```

现有指标：`macd`、`kdj`、`rsi`、`bbi`、`volume_ma`、`zxdkx`、`price_limit`（涨跌停幅度与归一化实体 `body_norm`，出货判定主尺子，需传 `code` 按板块/日期取幅度）。

### 选股框架：hunter 与 hunters 的分工

**这是最容易搞混的地方**，两个目录不是历史遗留，职责不同：

- `hunter/` = 引擎与基础件。`hunt_machine.py` 定义 `HuntMachine`（ThreadPoolExecutor 并行扫描）、`HuntInput`（惰性取数）、`HuntResult`（带 `union` / `intersection` 静态方法用于组合策略）；`hunt_pools.py` 提供股票池（全市场 / hs300 / hs300+csi500 / 加 csi2000）；`filters/` 是可复用的条件判断
- `hunters/` = 具体策略实现，如 `z_b1_hunter.py`、`z_b2_hunter.py`、`macd_divergence_hunter.py`、`z_distribution_hunter.py`（出货识别，与买点 hunter 分工相反：回答「要不要回避」，按 必走/至少走一半/稳一手 × 20日高危/60日观察 分层）。它们 import `hunter/` 的引擎，并用 `hunters/hunt_output.py` 的 `draw_hunt_results()` 出图

出货识别的探测器在 `hunter/distribution_signals.py`（S1~S5 + 换庄失效），是文稿《主力出货的 5 种典型方式》的量化版；只看量价位置，用 `price_limit` 归一化实体。需要代码判断板块幅度的策略，给 `HuntMachine.hunt()` 传 `with_code=True`，analyzer 签名变 `analyzer(df, code)`。

策略函数是纯函数：吃 DataFrame，命中返回 dict（附带指标值），不命中返回 `None` / `False`。

```python
def hunt_xxx(df: pd.DataFrame) -> Optional[dict]:
    if df is None or df.empty:
        return None
    add_kdj_to_dataframe(df, inplace=True)
    ...
    return {"kdj_j": j_val} if matched else None
```

并发规模：抓数据 8 workers，扫描 20 workers。

### 绘图层

`draws/` 分三层：主题（`kline_theme.py` 的 ThemeRegistry）→ 图工厂（`kline_fig_factory.py`，2 面板标准图 / 4 面板 ztalk 图）→ 卡片渲染（`kline_card.py`，Plotly → PIL → Base64）。`card_list.py` 拼多股卡片墙。

### AI 层

`ai/ai_api_profile.py` 用工厂函数返回 `ApiProfile`（OpenAI 兼容协议），可选千问 / DeepSeek / 豆包。选模型时注意成本与场景：字幕整理这类长文本轻任务用 `DEEPSEEK_FLASH()`，研报推理用 `DEEPSEEK_REASONER()` 或 `QWEN_MAX()`。

提示词两种形态：K 线分析用 `ai/*.jinja` 模板，字幕处理用 `ai/prompts/srt_prompts.py` 里的常量（`SRT_TO_ARTICLE_PROMPT`、`SRT_TO_KEY_POINTS_PROMPT` 等，按用途选）。

### 媒体流水线

`media_factory/` 是能力层：`yt_dlp.py` 下载（B 站需 Chrome cookie）、`video_handler.py` 抽音频、`whisper_mlx.py` 转录（仅 Apple Silicon）。长音频由 `whisper_to_srt_long()` 自动切段转录再 `merge_srt_files()` 合并，避免爆内存。

`cli/video_process/main.py` 把这些串成 4 步流水线（下载 → 抽音频 → 转录 → AI 成文），**每步都检查产物是否已存在，存在即跳过**，所以中断后重跑等于续传。详细参数见 `cli/video_process/README.md`。

### Notion

`notion/` 提供同步（`notion_sync_client.py`）和异步（`notion_async_client.py`）两套客户端，`notion_markdown.py` 负责 Markdown → Notion blocks。`cli/qk_notion/main.py` 暴露 `write` / `children` / `batch` 三个子命令，输入类型（URL / 文件 / stdin / 纯文本）自动识别。

## 约定

- 日志用 `tools/log.py` 的 `get_fetch_logger()`（抓取）/ `get_analyze_logger()`（分析），输出到 `logs/`，不要自建 logger。CLI 有自己的彩色 logger（控制台无时间戳，文件记 WARNING+）
- 产物统一落 `output/`，路径用 `tools/path.py` 的 `EXPORT_PATH` / `export_file_path()`
- 股票代码两种格式：6 位标准码（`000001`）和带交易所后缀（`000001.SZ`），转换用 `tools/stock_tools.py`
- PEP 8 + 类型标注；提交信息简短现在时（`volume ma`、`latest trade day`）
- `output/`、`logs/`、`database/*.db` 不入 git

## 密钥

`.env` 存 `QIANWEN_API_KEY`、`DEEPSEEK_API_KEY`、`DOUBAO_API_KEY`、`NOTION_TOKEN`，由 `config.py` / `ai/ai_api_profile.py` 读取。注意 `config.py` 里的 Tushare token 数组是硬编码明文，新增 token 别沿用这个做法。

## 已知问题

`setup.py` 的 `stock-info` 入口指向 `tools.cli:main`，该模块不存在；实际实现在 `cli/stock_info.py:75`。安装后运行 `stock-info` 会失败。
