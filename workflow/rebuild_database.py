"""从 0 重建数据库：清表 → 抓股票池 → 全量抓日线 → 补换手率 → 校验。

与 fetch_latest_klines.py 的区别：
- 显式建表（create_database.py 的 __main__ 只设 PRAGMA，不建表）
- 直接用 akshare 源：空库无锚点，tushare 缩放方案不可用，
  走 tushare 轮只会让每只股票白查两次库然后落进 failed_codes
- 全量抓到的是真前复权（基准日 = 今天），后续增量以此为锚

东财目前整体不可用，fetch_daily_bar_from_akshare 会在前 10 只各失败一次后
熔断并全程改走新浪源，这对重建正是想要的结果。
"""
import sys
import time
from datetime import timedelta

from datas.create_database import (
    DAILY_BAR_TABLE,
    STOCK_INFO_TABLE,
    get_db_connection,
    prepare_database,
)
from datas.fetch_all_market import fetch_stock_bars_parallel
from datas.fetch_stock_bars import (
    backfill_turnover_rate,
    find_dates_missing_turnover_rate,
)
from datas.fetch_stock_info import fetch_stock_infos
from datas.query_stock import query_all_stock_code_list
from tools.log import get_fetch_logger
from tools.stock_tools import latest_trade_day

logger = get_fetch_logger()

# 股票池低于此数视为抓取中途 abort，停止后续步骤：
# 行情范围完全由池子决定，缺股票不会有任何提示
MIN_POOL_SIZE = 5000

start_time = time.time()
target_date = latest_trade_day()
logger.info(f"=== 重建开始，目标最新交易日 {target_date} ===")


def stage(name: str):
    logger.info(f"--- [{name}] {timedelta(seconds=int(time.time() - start_time))} ---")


# ---------------------------------------------------------------- 1. 清表重建
# 只清日线表：股票池代价高（雪球详情接口易失效），可用则复用，
# 这样脚本中断后可直接重跑
stage("1/5 建表并清空日线")
prepare_database(recreate=False)
with get_db_connection() as conn:
    conn.execute(f"DELETE FROM {DAILY_BAR_TABLE}")
    conn.commit()
logger.info(f"已清空 {DAILY_BAR_TABLE}，WAL 模式已开启")

# ---------------------------------------------------------------- 2. 股票池
stage("2/5 股票池")
codes = query_all_stock_code_list()

if len(codes) < MIN_POOL_SIZE:
    logger.info(f"现有池子 {len(codes)} 只，不足 {MIN_POOL_SIZE}，重新抓取")
    fetch_stock_infos(rebuild=True)
    codes = query_all_stock_code_list()

pool_size = len(codes)
logger.info(f"股票池 {pool_size} 只")

if pool_size < MIN_POOL_SIZE:
    logger.error(
        f"💔 股票池仅 {pool_size} 只（阈值 {MIN_POOL_SIZE}），"
        f"疑似抓取中途 abort。已停止，未抓行情。"
        f"\n   雪球详情接口若返回 400016（需登录态），"
        f"可先跑 workflow/restore_stock_pool.py <备份库> 从备份恢复池子。"
    )
    sys.exit(1)

# ---------------------------------------------------------------- 3. 全量日线
stage("3/5 全量抓取日线（akshare qfq，东财熔断后走新浪）")
failed = fetch_stock_bars_parallel(codes, source="akshare")
logger.info(f"首轮失败 {len(failed)} 只")

if failed:
    stage("3b/5 重试失败项")
    failed = fetch_stock_bars_parallel(failed, source="akshare")
    logger.info(f"重试后仍失败 {len(failed)} 只: {list(failed)[:50]}")

# ---------------------------------------------------------------- 4. 换手率
# 新浪与东财的 qfq 接口都返回换手率，正常情况这步无事可做；
# 只有经 tushare 写入的行才会缺（tushare daily 无此字段）
stage("4/5 检查换手率缺口")
missing_dates = find_dates_missing_turnover_rate()
if missing_dates:
    logger.info(f"{len(missing_dates)} 个交易日缺换手率，开始回填")
    updated = backfill_turnover_rate(missing_dates)
    logger.info(f"换手率回填 {updated} 行")
else:
    logger.info("无缺口，跳过")

# ---------------------------------------------------------------- 5. 校验
stage("5/5 校验")
with get_db_connection() as conn:
    pool_n, = conn.execute(f"SELECT COUNT(*) FROM {STOCK_INFO_TABLE}").fetchone()
    rows, bar_codes, min_d, max_d = conn.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT code), MIN(date), MAX(date) FROM {DAILY_BAR_TABLE}"
    ).fetchone()
    at_latest, = conn.execute(
        f"SELECT COUNT(*) FROM (SELECT code FROM {DAILY_BAR_TABLE} "
        f"GROUP BY code HAVING MAX(date) = ?)", (target_date.strftime("%Y-%m-%d"),)
    ).fetchone()
    tr_null, = conn.execute(
        f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} WHERE turnover_rate IS NULL"
    ).fetchone()
    # 换手率量纲：新浪给小数需 ×100，若口径错会整体偏 100 倍
    tr_med, = conn.execute(
        f"SELECT AVG(turnover_rate) FROM {DAILY_BAR_TABLE} WHERE date = ?",
        (target_date.strftime("%Y-%m-%d"),)
    ).fetchone()

logger.info(f"股票池        : {pool_n}")
logger.info(f"日线行数      : {rows:,}  覆盖 {bar_codes} 只")
logger.info(f"日期范围      : {min_d} ~ {max_d}")
logger.info(f"抓到最新交易日: {at_latest}/{bar_codes} 只")
logger.info(f"换手率为空    : {tr_null} 行")
logger.info(f"最新日均换手率: {tr_med:.2f}%（A 股常态 0.5~5，偏 100 倍说明量纲错）"
            if tr_med else "最新日均换手率: 无数据")

total = time.time() - start_time
logger.info(f"=== 重建完成，耗时 {timedelta(seconds=int(total))} ===")
