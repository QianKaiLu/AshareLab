---
name: qk-stock-daily-update
description: A 股日常行情更新流水线。同步股票池（补新股/剔退市，每周一次）→ 增量抓日线 → 回填换手率 → 数据质量校验。触发场景：(1) 用户说「更新行情」「拉最新数据」「日更」「同步股票数据」「更新数据库」(2) 用户说「刷新股票池」「补新股」「剔退市」(3) 用户输入 /qk-stock-daily-update (4) 用户在做选股/画图/研报前发现数据不是最新。支持 --force-pool、--skip-pool、--dry-run 参数。
---

# QK Stock Daily Update — A 股行情日更流水线

## 概述

把 `database/ashare_data.db` 对齐到最新交易日。四步流水线，每步失败不阻断后续：

```
1. 股票池同步（默认每 7 天一次）
   ak.stock_info_a_code_name() 为权威 → 补新股 / 剔退市 / 同步简称
   ↓
2. 增量行情（tushare 主源，锚定缩放）
   ↓
3. akshare 兜底（失败项 + 新股全量）
   ↓
4. 换手率回填（daily_basic 按交易日）
   ↓
校验：最新日期 / 落后股票数 / OHLC 异常 / 涨跌幅异常 / 换手率空值
```

## 运行环境（必读）

**所有命令必须切到 conda `stock` 环境**，否则 akshare / tushare / baostock 全部 ImportError。
两种写法，非交互场景一律用第一种：

```bash
# 推荐：conda run 直接指定环境，不改变当前 shell
conda run --live-stream -n stock python <script.py>

# 交互式终端里也可以先激活
conda activate stock
```

另外项目脚本以模块路径导入（`from datas.query_stock import ...`），
所以必须让项目根在 `PYTHONPATH` 上：命令前加 `PYTHONPATH=.`，且工作目录为项目根。

两个必需参数缺一不可：

- `PYTHONPATH=.` — 缺了会 `ModuleNotFoundError: No module named 'datas'`
- `--live-stream` — 缺了 `conda run` 会缓冲全部输出到进程结束，日志一直是 0 字节，看起来像卡死

## 调用方式

耗时视落后天数而定（当天已更新约 35 秒，落后一周约 3-10 分钟），**必须后台跑**：

```bash
cd /Users/qianqian/stock/AshareLab
PYTHONPATH=. conda run --live-stream -n stock python workflow/daily_update.py > logs/daily_$(date +%Y%m%d).log 2>&1
```

## 参数

| 参数 | 说明 | 适用场景 |
|------|------|---------|
| （无） | 常规日更，池子按 7 天间隔自动判断 | **默认** |
| `--force-pool` | 忽略间隔，强制同步池子 | 知道刚有新股上市/退市 |
| `--skip-pool` | 跳过池子，只更行情 | 盘后快速更新 |
| `--dry-run` | 只报告池子差异，不写库、不抓行情 | 想先看会增删哪些股票 |
| `--pool-interval N` | 改池子同步间隔（默认 7 天） | 想更频繁地跟踪新股 |

## 进度跟踪

`conda run` 缓冲输出，所以**不要靠 tail 日志判断进度**，查库：

```bash
# 已到最新交易日的股票数
sqlite3 database/ashare_data.db "SELECT COUNT(*) FROM (SELECT code FROM stock_bars_daily_qfq GROUP BY code HAVING MAX(date)=(SELECT MAX(date) FROM stock_bars_daily_qfq));"
```

进程结束后日志才完整可读。

## 退出码

- `0` — 完成，无告警
- `1` — 完成但有告警（最新日期未达标 / 数据质量异常），日志里有 `⚠` 行

## 关键设计（改动前必读）

**池子必须在行情之前同步。** 抓取范围由 `stock_base_info` 决定，新股不在池里就永远抓不到。

**退市有删除上限。** 单次超过 30 只则跳过不删。代码表抓取不完整时会把在市股票误判为退市，而删掉的行情要重抓 20 年。同理代码表少于 5000 条时整个同步会放弃。

**新股走 akshare 全量。** 库中无锚点时 tushare 的缩放方案不可用，worker 会直接返回失败，由第 3 步的 akshare 轮补全量历史。所以「tushare 轮失败 N 只」在有新股时是正常的。

**雪球详情大概率补不上。** `stock_individual_basic_info_xq` 现在要求登录态，对所有代码返回 `400016`。日志里「雪球详情补齐 0/N 只」是预期行为，只影响行业字段，不影响行情。

## 常见场景

### 场景 1：日常更新

```
用户: 更新一下行情
```
→ 后台跑上面「调用方式」里的完整命令，完成后报告校验结果

### 场景 2：只想看池子会怎么变

```
用户: 看看有没有新股或退市的
```
→ `PYTHONPATH=. conda run --live-stream -n stock python workflow/daily_update.py --dry-run`

### 场景 3：新股上市了要立刻拉

```
用户: 今天有新股上市，把数据补上
```
→ `PYTHONPATH=. conda run --live-stream -n stock python workflow/daily_update.py --force-pool`

### 场景 4：校验报了数据质量异常

日志出现 `⚠ 数据质量异常（OHLC N 行 / 涨跌幅 M 行）`：

→ 先看范围，确认后去掉 `--dry-run` 执行：

```bash
PYTHONPATH=. conda run --live-stream -n stock python workflow/repair_negative_prices.py --dry-run
```

### 场景 5：库损坏或要重建

**重建前先备份**（2.5G，约 10 秒）：

```bash
cp database/ashare_data.db database/ashare_data.db.bak-$(date +%Y%m%d)
PYTHONPATH=. conda run --live-stream -n stock python workflow/rebuild_database.py
```

可重入（只清日线、保留池子），约 27 分钟。

## 相关脚本

| 脚本 | 用途 |
|------|------|
| `workflow/daily_update.py` | 本流水线 |
| `workflow/repair_negative_prices.py` | 修负价 / 零价 / Inf 涨跌幅 |
| `workflow/rebuild_database.py` | 从 0 重建（可重入） |
| `workflow/restore_stock_pool.py` | 从备份恢复池子（雪球挂时用） |
| `datas/sync_stock_pool.py` | 池子同步模块，可单独 dry-run |

## 数据源现状（2026-08-24 实测）

| 源 | 状态 | 备注 |
|---|---|---|
| tushare `daily` | 正常 | 增量主源，**不返回换手率** |
| tushare `daily_basic` | 正常 | 回填换手率，限流按 token 独立计 |
| akshare / 新浪 | 正常 | 0.4s/只，字段完整 |
| akshare / 东财 | **不可用** | 连接层瞬时拒绝，自动回退新浪 |
| baostock | 可用 | 独立校验源，非线程安全，不支持北交所 |
| 雪球详情 | **需登录态** | 只影响行业字段 |

## 注意事项

- 数据库约 2.5G，日更只写增量，不会显著增长
- `latest_trade_day()` 只认周末不认节假日，长假期间会对全市场空跑一轮请求（无害，但耗时）
- 池子同步时间戳记在 `database/.pool_synced` 的 mtime 上
