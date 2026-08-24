"""日常行情更新：池子同步（每周）→ 增量行情 → 换手率回填 → 数据质量校验。

设计要点：
- 池子同步默认每 7 天一次（.pool_synced 的 mtime 记时间），--force-pool 可强制。
  池子必须在行情之前同步：抓取范围由池子决定，新股不在池里就永远抓不到。
- 退市股连带删除历史行情，并设了单次上限（默认 30 只），超限则跳过不删——
  代码表抓取不完整时会把在市股票误判为退市，删掉的行情要重抓 20 年。
- 新股在池子同步后自然进入抓取范围：worker 发现库中无该股数据，会走 akshare 全量。
- 每步失败不阻断后续：行情抓不到不该妨碍换手率回填，反之亦然。

用法:
    python workflow/daily_update.py                # 常规日更
    python workflow/daily_update.py --force-pool   # 强制刷新池子
    python workflow/daily_update.py --skip-pool    # 只更行情
    python workflow/daily_update.py --dry-run      # 只报告池子差异，不写库
"""
import argparse
import sys
import time
from datetime import timedelta

from datas.create_database import DAILY_BAR_TABLE, get_db_connection, prepare_database
from datas.fetch_all_market import fetch_stock_bars_parallel
from datas.fetch_stock_bars import (
    backfill_turnover_rate,
    find_dates_missing_turnover_rate,
)
from datas.query_stock import query_all_stock_code_list
from datas.sync_stock_pool import (
    POOL_SYNC_INTERVAL_DAYS,
    needs_pool_sync,
    pool_sync_age_days,
    refresh_missing_details,
    sync_stock_pool,
)
from tools.log import get_fetch_logger
from tools.stock_tools import latest_trade_day

logger = get_fetch_logger()


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-pool", action="store_true",
                        help="忽略 7 天间隔，强制同步股票池")
    parser.add_argument("--skip-pool", action="store_true",
                        help="跳过股票池同步，只更新行情")
    parser.add_argument("--dry-run", action="store_true",
                        help="只报告池子差异，不写库（不抓行情）")
    parser.add_argument("--pool-interval", type=int, default=POOL_SYNC_INTERVAL_DAYS,
                        help=f"池子同步间隔天数（默认 {POOL_SYNC_INTERVAL_DAYS}）")
    args = parser.parse_args()

    start = time.time()
    target_date = latest_trade_day()
    logger.info(f"=== 日常更新开始，目标最新交易日 {target_date} ===")

    prepare_database(recreate=False)

    def stage(name: str):
        logger.info(f"--- [{name}] {timedelta(seconds=int(time.time() - start))} ---")

    # ------------------------------------------------------------ 1. 股票池
    age = pool_sync_age_days()
    age_text = "从未同步" if age is None else f"{age:.1f} 天前"
    if args.skip_pool:
        stage(f"1/4 股票池（跳过，上次 {age_text}）")
    elif args.force_pool or needs_pool_sync(args.pool_interval):
        stage(f"1/4 股票池同步（上次 {age_text}）")
        result = sync_stock_pool(dry_run=args.dry_run)

        if result.get("skipped"):
            logger.warning(f"池子同步已跳过: {result['skipped']}")
        else:
            prefix = "[dry-run] " if args.dry_run else ""
            logger.info(f"{prefix}新增 {len(result['added'])} 只"
                        + (f": {result['added']}" if result['added'] else ""))
            logger.info(f"{prefix}退市 {len(result['delisted'])} 只"
                        + (f": {result['delisted']}，连带删除 {result['deleted_bars']} 行行情"
                           if result['delisted'] else ""))
            if result.get("renamed"):
                logger.info(f"{prefix}简称更新 {result['renamed']} 只")
            logger.info(f"{prefix}池子共 {result['total']} 只")

        # 雪球详情：能补就补，补不上不影响行情
        if not args.dry_run:
            ok, tried = refresh_missing_details()
            if tried:
                logger.info(f"雪球详情补齐 {ok}/{tried} 只"
                            + ("（雪球需登录态时会全部失败，属预期）" if ok == 0 else ""))
    else:
        stage(f"1/4 股票池（{age_text}同步过，间隔未到 {args.pool_interval} 天，跳过）")

    if args.dry_run:
        logger.info("=== dry-run 结束，未抓行情 ===")
        return 0

    # ------------------------------------------------------------ 2. 增量行情
    codes = query_all_stock_code_list()
    stage(f"2/4 增量行情（{len(codes)} 只，tushare 主源）")
    failed = fetch_stock_bars_parallel(codes, source="tushare")
    logger.info(f"tushare 轮失败 {len(failed)} 只")

    # 新股（库中无锚点）在 tushare 轮会直接落进 failed，由这一轮走 akshare 全量补
    if failed:
        stage(f"3/4 akshare 兜底（{len(failed)} 只）")
        still_failed = fetch_stock_bars_parallel(failed, source="akshare")
        if still_failed:
            logger.warning(f"仍失败 {len(still_failed)} 只: {list(still_failed)[:30]}")
    else:
        stage("3/4 akshare 兜底（无需）")

    # ------------------------------------------------------------ 4. 换手率
    missing_dates = find_dates_missing_turnover_rate()
    if missing_dates:
        stage(f"4/4 换手率回填（{len(missing_dates)} 个交易日）")
        updated = backfill_turnover_rate(missing_dates)
        logger.info(f"换手率更新 {updated} 行")
    else:
        stage("4/4 换手率（无缺口）")

    # ------------------------------------------------------------ 校验
    target_str = target_date.strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        rows, bar_codes, max_date = conn.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT code), MAX(date) FROM {DAILY_BAR_TABLE}"
        ).fetchone()
        at_latest, = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT code FROM {DAILY_BAR_TABLE} "
            f"GROUP BY code HAVING MAX(date) = ?)", (target_str,)).fetchone()
        stale, = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT code FROM {DAILY_BAR_TABLE} "
            f"GROUP BY code HAVING MAX(date) < ?)", (target_str,)).fetchone()
        bad_ohlc, = conn.execute(
            f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} WHERE open<=0 OR high<=0 "
            f"OR low<=0 OR close<=0 OR high<low OR close>high OR close<low").fetchone()
        bad_chg, = conn.execute(
            f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} WHERE change_pct>1e300 "
            f"OR change_pct<-1e300 OR change_pct IS NULL").fetchone()
        tr_null, = conn.execute(
            f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} WHERE turnover_rate IS NULL"
        ).fetchone()

    logger.info("=== 校验 ===")
    logger.info(f"全库          : {rows:,} 行 / {bar_codes} 只，最新 {max_date}")
    logger.info(f"已到最新交易日: {at_latest}/{bar_codes} 只（落后 {stale} 只）")
    logger.info(f"OHLC 异常     : {bad_ohlc} 行")
    logger.info(f"涨跌幅异常    : {bad_chg} 行")
    logger.info(f"换手率为空    : {tr_null} 行")

    problems = []
    if max_date != target_str:
        problems.append(f"库中最新日期 {max_date} 未达目标 {target_str}")
    if bad_ohlc or bad_chg:
        problems.append(f"数据质量异常（OHLC {bad_ohlc} 行 / 涨跌幅 {bad_chg} 行）"
                        f"，可运行 workflow/repair_negative_prices.py")

    elapsed = timedelta(seconds=int(time.time() - start))
    if problems:
        for p in problems:
            logger.warning(f"⚠ {p}")
        logger.info(f"=== 完成（有告警），耗时 {elapsed} ===")
        return 1

    logger.info(f"=== 完成，耗时 {elapsed} ===")
    return 0


if __name__ == "__main__":
    sys.exit(run())
