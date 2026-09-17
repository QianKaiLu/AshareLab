"""从 0 重建数据库：清表 → 抓股票池 → 全量抓日线 → 恢复北交所 → 补换手率 → 校验。

与 fetch_latest_klines.py 的区别：
- 显式建表（create_database.py 的 __main__ 只设 PRAGMA，不建表）
- 全量抓取走**新浪多进程**：空库无锚点，tushare 缩放方案不可用，
  走 tushare 轮只会让每只股票白查两次库然后落进 failed_codes
- 全量抓到的是真前复权（基准日 = 今天），后续增量以此为锚

## 为什么入口必须有 `if __name__ == "__main__"` 保护

全量抓取用 ProcessPoolExecutor（spawn），spawn 启动子进程时会 `import __main__`。
本脚本没有保护的话，每启动一个子进程就会把整个重建流程重跑一遍——递归爆炸。

## 为什么是多进程而不是多线程

akshare 的新浪行情接口内部用 py_mini_racer（V8）算复权因子，V8 实例不是线程安全的：
3 线程跑 200 只必崩（`address_pool_manager.cc Check failed: !pool->IsInitialized()`）。
每进程独立持 V8 则稳定且更快（实测 4 进程 0.077s/只，3 线程直接崩）。
详见 datas/fetch_all_market.fetch_full_history_parallel。

## 北交所（92xxxx）单独处理

新浪与 baostock 都不支持北交所，tushare 的 pro_bar 又受 adj_factor「1 次/分钟」限流
（343 只要 5.7 小时）。所以清表前先把北交所行情转存到临时表，抓完沪深后再搬回来——
保持它原有的 tushare 口径不变。脚本中断重跑时临时表会被重建，不会累积。
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
from datas.fetch_all_market import (
    FULL_FETCH_WORKERS,
    fetch_full_history_parallel,
)
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

# 北交所：4xxxxx / 8xxxxx / 92xxxx。不复用 get_exchange_by_code——它认 8/9 开头，
# 但对 4 开头（430xxx 那批）会抛 ValueError。
BJ_PREFIXES = ("4", "8", "92")
BJ_SQL_FILTER = "(code LIKE '4%' OR code LIKE '8%' OR code LIKE '92%')"
BJ_TMP_TABLE = f"{DAILY_BAR_TABLE}_bj_tmp"


def is_bse(code: str) -> bool:
    """北交所代码判断（与 BJ_SQL_FILTER 口径一致）。"""
    return code.startswith(BJ_PREFIXES)


def main() -> int:
    start_time = time.time()
    target_date = latest_trade_day()
    logger.info(f"=== 重建开始，目标最新交易日 {target_date} ===")

    def stage(name: str):
        logger.info(f"--- [{name}] {timedelta(seconds=int(time.time() - start_time))} ---")

    # ------------------------------------------------------------ 1. 清表重建
    # 只清日线表：股票池代价高（雪球详情接口易失效），可用则复用，
    # 这样脚本中断后可直接重跑。
    # 北交所先转存——清表会把它一起删掉，而它重建不回来（见模块 docstring）。
    stage("1/6 建表并清空日线（北交所先转存）")
    prepare_database(recreate=False)
    with get_db_connection() as conn:
        conn.execute(f"DROP TABLE IF EXISTS {BJ_TMP_TABLE}")
        conn.execute(f"CREATE TABLE {BJ_TMP_TABLE} AS "
                     f"SELECT * FROM {DAILY_BAR_TABLE} WHERE {BJ_SQL_FILTER}")
        bj_codes, bj_rows = conn.execute(
            f"SELECT COUNT(DISTINCT code), COUNT(*) FROM {BJ_TMP_TABLE}").fetchone()
        conn.execute(f"DELETE FROM {DAILY_BAR_TABLE}")
        conn.commit()
    logger.info(f"已清空 {DAILY_BAR_TABLE}，WAL 模式已开启；"
                f"北交所 {bj_codes} 只 / {bj_rows:,} 行转存至 {BJ_TMP_TABLE}")

    # ---------------------------------------------------------------- 2. 股票池
    stage("2/6 股票池")
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
        return 1

    # ---------------------------------------------------------------- 3. 全量日线
    main_codes = [c for c in codes if not is_bse(c)]
    stage(f"3/6 全量抓取日线（新浪 {FULL_FETCH_WORKERS} 进程，{len(main_codes)} 只）")
    failed = fetch_full_history_parallel(main_codes)
    logger.info(f"首轮失败 {len(failed)} 只")

    if failed:
        stage("3b/6 重试失败项")
        failed = fetch_full_history_parallel(failed)
        logger.info(f"重试后仍失败 {len(failed)} 只: {list(failed)[:50]}")

    # ------------------------------------------------------------ 4. 恢复北交所
    stage("4/6 恢复北交所行情")
    with get_db_connection() as conn:
        conn.execute(f"INSERT OR REPLACE INTO {DAILY_BAR_TABLE} "
                     f"SELECT * FROM {BJ_TMP_TABLE}")
        conn.execute(f"DROP TABLE {BJ_TMP_TABLE}")
        conn.commit()
    logger.info(f"北交所 {bj_codes} 只 / {bj_rows:,} 行已搬回 {DAILY_BAR_TABLE}")

    # ---------------------------------------------------------------- 5. 换手率
    # 新浪的 qfq 接口自带换手率，正常情况这步无事可做；
    # 只有经 tushare 写入的行才会缺（tushare daily 无此字段），即恢复回来的北交所那批
    stage("5/6 检查换手率缺口")
    missing_dates = find_dates_missing_turnover_rate()
    if missing_dates:
        logger.info(f"{len(missing_dates)} 个交易日缺换手率，开始回填")
        updated = backfill_turnover_rate(missing_dates)
        logger.info(f"换手率回填 {updated} 行")
    else:
        logger.info("无缺口，跳过")

    # ---------------------------------------------------------------- 6. 校验
    stage("6/6 校验")
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
        bad_ohlc, = conn.execute(
            f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} WHERE open<=0 OR high<=0 "
            f"OR low<=0 OR close<=0 OR high<low OR close>high OR close<low").fetchone()
        # 换手率量纲：新浪给小数需 ×100，若口径错会整体偏 100 倍
        tr_med, = conn.execute(
            f"SELECT AVG(turnover_rate) FROM {DAILY_BAR_TABLE} WHERE date = ?",
            (target_date.strftime("%Y-%m-%d"),)
        ).fetchone()

    logger.info(f"股票池        : {pool_n}")
    logger.info(f"日线行数      : {rows:,}  覆盖 {bar_codes} 只")
    logger.info(f"日期范围      : {min_d} ~ {max_d}")
    logger.info(f"抓到最新交易日: {at_latest}/{bar_codes} 只")
    logger.info(f"OHLC 非正     : {bad_ohlc} 行")
    logger.info(f"换手率为空    : {tr_null} 行")
    logger.info(f"最新日均换手率: {tr_med:.2f}%（A 股常态 0.5~5，偏 100 倍说明量纲错）"
                if tr_med else "最新日均换手率: 无数据")

    problems = []
    if at_latest < bar_codes:
        problems.append(f"{bar_codes - at_latest} 只未到最新交易日 {target_date}")
    if bad_ohlc:
        problems.append(f"OHLC 非正 {bad_ohlc} 行")
    if failed:
        problems.append(f"仍有 {len(failed)} 只抓取失败")

    total = time.time() - start_time
    if problems:
        for p in problems:
            logger.warning(f"⚠ {p}")
        logger.info(f"=== 重建完成（有告警），耗时 {timedelta(seconds=int(total))} ===")
        return 1

    logger.info(f"=== 重建完成，耗时 {timedelta(seconds=int(total))} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
