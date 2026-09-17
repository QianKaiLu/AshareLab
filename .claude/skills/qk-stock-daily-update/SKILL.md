---
name: qk-stock-daily-update
description: A 股日常行情更新流水线。同步股票池（补新股/剔退市，每周一次）→ 增量抓日线 → 回填换手率 → 更新指数日线 → 更新指数分钟线 → 数据质量校验。触发场景：(1) 用户说「更新行情」「拉最新数据」「日更」「同步股票数据」「更新数据库」(2) 用户说「刷新股票池」「补新股」「剔退市」(3) 用户输入 /qk-stock-daily-update (4) 用户在做选股/画图/研报前发现数据不是最新。支持 --force-pool、--skip-pool、--skip-index、--skip-min、--dry-run 参数。
---

# QK Stock Daily Update — A 股行情日更流水线

## 概述

把 `database/ashare_data.db` 对齐到最新交易日。六步流水线，每步失败不阻断后续：

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
5. 指数日线（13 只宽基 → 独立表 index_bars_daily）
   ↓
6. 指数分钟线（上证 30 分钟 → 独立表 index_bars_min）
   ↓
校验：最新日期 / 落后股票数 / OHLC 异常 / 涨跌幅异常 / 换手率空值 / 指数覆盖
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

耗时几乎全在个股那步：当天数据还没抓时，要为全市场每只发一次请求（受 tushare 限流约束，实测 5561 只约 21 分钟）；数据已是最新时该步秒过，全程约 1 分钟。指数和分钟线都是秒级。**必须后台跑**：

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
| `--skip-index` | 跳过指数日线，只更个股 | 指数源出问题时隔离排查 |
| `--skip-min` | 跳过指数分钟线 | 分钟线源出问题时隔离排查 |
| `--dry-run` | 只报告池子差异，不写库、不抓行情 | 想先看会增删哪些股票 |
| `--pool-interval N` | 改池子同步间隔（默认 7 天） | 想更频繁地跟踪新股 |

## 进度跟踪

`conda run` 缓冲输出，所以**不要靠 tail 日志判断进度**，查库：

```bash
# 已到最新交易日的股票数
sqlite3 database/ashare_data.db "SELECT COUNT(*) FROM (SELECT code FROM stock_bars_daily_qfq GROUP BY code HAVING MAX(date)=(SELECT MAX(date) FROM stock_bars_daily_qfq));"

# 指数是否跟上（第 5 步才跑，最后才动）
sqlite3 database/ashare_data.db "SELECT symbol, MAX(date) FROM index_bars_daily GROUP BY symbol;"

# 指数分钟线是否跟上（第 6 步，最后才动）
sqlite3 database/ashare_data.db "SELECT symbol, MAX(dt) FROM index_bars_min GROUP BY symbol;"
```

进程结束后日志才完整可读。

## 退出码

- `0` — 完成，无告警
- `1` — 完成但有告警（最新日期未达标 / 数据质量异常），日志里有 `⚠` 行

**退出码 1 有两种含义，别混。** 脚本抛异常也是 1（`conda run` 一律显示 `failed`）。
分辨方法：看日志里有没有 `=== 校验 ===` 段——**有**才是「跑完但有告警」，
**没有**就是中途崩了，往上翻 traceback。2026-09-17 就踩过：分钟线统计少一个键，
第 6 步崩溃，把校验段一起带走了，日志看着像正常告警。

## 关键设计（改动前必读）

**池子必须在行情之前同步。** 抓取范围由 `stock_base_info` 决定，新股不在池里就永远抓不到。

**退市有删除上限。** 单次超过 30 只则跳过不删。代码表抓取不完整时会把在市股票误判为退市，而删掉的行情要重抓 20 年。同理代码表少于 5000 条时整个同步会放弃。

**新股走 akshare 全量。** 库中无锚点时 tushare 的缩放方案不可用，worker 会直接返回失败，由第 3 步的 akshare 轮补全量历史。所以「tushare 轮失败 N 只」在有新股时是正常的。

**雪球详情大概率补不上。** `stock_individual_basic_info_xq` 现在要求登录态，对所有代码返回 `400016`。日志里「雪球详情补齐 0/N 只」是预期行为，只影响行业字段，不影响行情。

**指数日线是独立表 + 独立模块。** 13 只宽基指数落在 `index_bars_daily`，代码是 `datas/fetch_index_bars.py`。三个必须知道的点：

- **指数代码带交易所前缀（`sh000001`），不能用 `tools/stock_tools.py`**。`to_std_code('sh000001')` 会得到 `000001`，与平安银行撞车主键；`get_exchange_by_code` 对 `000300` 误判深交所、对 `399300` 直接抛异常。
- **两个源各有静默失败模式，所以有兜底 + 新鲜度校验**。akshare 新浪的 `sh000985` 数据停在 2016 却不报错；腾讯的 `bj899050` 只返回 1 根、且对指数有 2000 根上限。校验的基准是**个股表的 `MAX(date)`**（真实交易日历），不是 `latest_trade_day()`（它不认节假日）。
- **成交量已统一成「股」**。腾讯原生是「手」，模块内乘了 100 对齐新浪，否则主源/兜底源切换会污染 volume 序列。

指数池要增删，改 `datas/fetch_index_bars.py` 的 `INDEX_POOL` 常量即可（每项是 `(symbol, 名称, 主源, 兜底源)`），并实测新 symbol 在两个源上的可用性 —— **别只看能不能取到数，要看末日期是不是最新**。

**指数分钟线同样是独立表 + 独立模块。** 代码是 `datas/fetch_index_min_bars.py`，落在 `index_bars_min`。五个必须知道的点：

- **只抓 30 分钟存库，60 / 120 读时合成**（`query_index_min_bars(symbol, period=60)` 内部调 `aggregate_bars()`）。新浪支持 scale = 5/15/30/60/240，**不支持 120**；而 60 若既原生抓又由 30 合成，两者的边界对齐与午休处理不同，会制造「同一指标两个值」。**一个来源，一套口径。**
- **合成按交易时段分组**（上午 / 下午各自成组），不按固定窗口切 —— 那样会切出 12:30 / 14:30 / 16:30 这种跨午休的边界，最后一根只含 1 根 30 分钟 bar。半日市会产出不足整组的 bar，默认保留并在 `bars` 列标出实际根数。
- **每次日更是全量覆盖重抓 + UPSERT，不是增量**。新浪一次最多返回 5000 根（约 2.5 年），日更把整段重写一遍。表不会因此膨胀（UPSERT 命中已有行），但「日更只写增量」这句话对分钟线不成立；日志里的「写入 5000 行」是 UPSERT 影响行数，首次跑才等于新增。
- **默认只跟上证（`sh000001`）**。分钟数据量比日线大一个量级，按需再扩：改 `DEFAULT_SYMBOLS` 即可。
- **只有一个源（新浪），没有兜底源，也没有新鲜度校验**。指数日线有腾讯兜底 + `stale` 列表，分钟线抓不到只在日志里打一行 warning。缺了要翻日志才发现。

**警告不等于失败。** 「指数落后于基准」只打 warning 不进 `problems`，不影响退出码（与「换手率为空」同一先例）。源滞后一天不该让整个日更报错。

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

### 场景 5：只想单独更指数

```
用户: 指数数据补一下 / 指数怎么没更新
```

→ 不必跑整个日更（个股那步要 20 分钟），直接单独跑模块：

```bash
cd /Users/qianqian/stock/AshareLab
PYTHONPATH=. conda run --live-stream -n stock python -c "from datas.fetch_index_bars import update_all_indices; print(update_all_indices())"
```

约 15 秒（13 只串行 + 0.5s 间隔）。返回的统计里看 `failed` / `stale` 两个列表。
查数据用 `datas/query_stock.py` 的 `query_index_bars()` / `query_index_latest_bars()`，
**不要直接写 SQL 查 `index_bars_daily`**。默认基准是中证500（`sh000905`）。

### 场景 6：只想单独更指数分钟线

```
用户: 分钟线补一下 / 分钟线怎么没更新
```

→ 同样不必跑整个日更，直接跑模块（约 5 秒，当前只 1 只）：

```bash
cd /Users/qianqian/stock/AshareLab
PYTHONPATH=. conda run --live-stream -n stock python -m datas.fetch_index_min_bars
```

查数据用 `datas/query_stock.py` 的 `query_index_min_bars()`，`period` 传 30 / 60 / 120，
**不要直接写 SQL 查 `index_bars_min`**。盘中形态分析见 `market/intraday.py`。

### 场景 7：库损坏或要重建

**重建前先备份**（2.7G，约 5 秒）：

```bash
cp database/ashare_data.db database/ashare_data.db.bak-$(date +%Y%m%d)
PYTHONPATH=. conda run --live-stream -n stock python workflow/rebuild_database.py
```

可重入（只清日线、保留池子）。**实测 14 分 44 秒**（2026-09-17，5218 只沪深股票）。

四个必须知道的点：

- **全量抓取走新浪多进程（4 进程），不能用线程、也不能用 fork。** akshare 的新浪
  接口内部用 py_mini_racer（V8）算复权因子，V8 实例不是线程安全的——3 线程跑 200 只
  必崩（`address_pool_manager.cc Check failed`）；fork 会让子进程继承父进程的 V8
  状态，进程池同样崩（BrokenProcessPool）。只有 spawn + 每进程独立 V8 稳定，
  实测 4 进程 0.077s/只。详见 `datas/fetch_all_market.fetch_full_history_parallel`。
- **入口脚本必须保留 `if __name__ == "__main__"` 保护。** spawn 启动子进程时会
  `import __main__`，没有保护会把整个重建递归重跑。
- **北交所（92xxxx）单独处理。** 新浪与 baostock 都不支持，tushare 的 `pro_bar` 又受
  `adj_factor` 1 次/分钟限流（343 只需 5.7 小时）。脚本的做法是清表前把北交所行情
  转存到临时表 `stock_bars_daily_qfq_bj_tmp`，抓完沪深后再搬回来。
- **重建会换掉复权口径**：全库变成新浪乘法式（基准日 = 当天）。实测未被污染的股票
  与旧库逐点完全一致（000001、600026 抽查 2008/2015/2026 三个时点差异均为 0.00%），
  而被东财减法式污染过的（如中信特钢 000708）历史段会被修正回正确值。

重建后查三项：总行数与旧库一致、`OHLC 非正` 为 0、换手率无缺口。

## 相关脚本

| 脚本 | 用途 |
|------|------|
| `workflow/daily_update.py` | 本流水线 |
| `workflow/repair_negative_prices.py` | 修负价 / 零价 / Inf 涨跌幅 |
| `workflow/rebuild_database.py` | 从 0 重建（可重入） |
| `workflow/restore_stock_pool.py` | 从备份恢复池子（雪球挂时用） |
| `datas/sync_stock_pool.py` | 池子同步模块，可单独 dry-run |
| `datas/fetch_index_bars.py` | 指数日线模块，可单独跑（见场景 5） |
| `datas/fetch_index_min_bars.py` | 指数分钟线模块，可单独跑（见场景 6） |

## 数据源现状（2026-08-24 实测，分钟线三行为 2026-09-17 实测）

| 源 | 状态 | 备注 |
|---|---|---|
| tushare `daily` | 正常 | 增量主源，**不返回换手率** |
| tushare `daily_basic` | 正常 | 回填换手率，限流按 token 独立计 |
| akshare / 新浪 | 正常 | 0.4s/只，字段完整 |
| akshare / 东财 | **不可用** | 连接层瞬时拒绝，自动回退新浪 |
| baostock | 可用 | 独立校验源，非线程安全，不支持北交所 |
| 雪球详情 | **需登录态** | 只影响行业字段 |
| akshare `stock_zh_index_daily`（新浪） | 正常 | 指数主源，**无日期参数、每次返回全量**；`sh000985` 数据停在 2016 需绕过 |
| 腾讯 `web.ifzq.gtimg.cn` | 正常 | 指数兜底源，免费无 token；**指数上限 2000 根，`bj899050` 只返回 1 根** |
| 新浪 `CN_MarketData.getKLineData` | 正常 | **分钟线唯一源**，scale 支持 5/15/30/60/240（**无 120**），一次上限 5000 根 |
| 东财 `index_zh_a_hist_min_em` | **不可用** | 连接层被拒，与个股东财同一老问题 |
| 腾讯 `kline/mkline` | **不可用** | 重定向到 web3.ifzq.gtimg.cn，该域名连不通 |

## 注意事项

- 数据库约 2.5G，个股与指数日线只写增量；指数日线表约 5.4 万行、分钟线表约 5000 行，可忽略
- `latest_trade_day()` 只认周末不认节假日，长假期间会对全市场空跑一轮请求（无害，但耗时）
- 池子同步时间戳记在 `database/.pool_synced` 的 mtime 上
- **交易日历的权威来源是个股表的 `MAX(date)`**，不是 `latest_trade_day()`。判断「数据到没到最新」一律查库
- 指数池不含中证2000（`sh932000`）—— 两个源都取不到；小盘代理用国证2000（`sz399303`）
