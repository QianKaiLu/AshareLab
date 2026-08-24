"""修复库中 close<=0 的历史行。

两组问题性质不同：

1. 14 只深市老股（0xxxxx，6487 行）
   东财/新浪用加法式复权：从历史价里减去累计分红。老股累计分红逼近甚至超过
   早期股价时，历史价被减成负数。baostock 用涨跌幅复权法（乘法式），同期恒为正。
   两法在这些股票上系统性分叉（比值范围低至 0.0019，多数行漂移 >0.5%），
   所以只替换负价行会拼出自相矛盾的序列——必须整只全历史替换。
   已验证：14 只的行数与最新收盘价均与库中完全一致，替换后增量锚定仍成立。

2. 34 只北交所代码（920xxx，185 行）
   OHLC 全为 0 但 volume 有值，集中在 2018-2020，是这些代码改制前
   （新三板时期）的脏数据，源头如此。baostock 不支持北交所，无替代源，
   只能删除——0 价无法参与任何指标计算。

用法:
    python workflow/repair_negative_prices.py --dry-run   # 只报告，不写库
    python workflow/repair_negative_prices.py             # 执行修复
"""
import argparse
import sqlite3
import sys

import pandas as pd

from datas.create_database import DAILY_BAR_TABLE, EARLIEST_DATE, get_db_connection
from datas.fetch_stock_bars import (
    fetch_daily_bar_from_baostock,
    save_daily_bars_to_database,
)
from datas.query_stock import query_daily_bars
from tools.log import get_fetch_logger

logger = get_fetch_logger()

# 替换前的安全阈值：最新收盘价偏差超过此值说明两源基准不同，不可整段替换
LATEST_CLOSE_TOLERANCE_PCT = 0.5


def find_negative_price_codes() -> tuple[list[str], list[str]]:
    """返回 (可用 baostock 修复的沪深代码, 只能删行的北交所代码)。"""
    query = f"SELECT DISTINCT code FROM {DAILY_BAR_TABLE} WHERE close <= 0 ORDER BY code"
    with get_db_connection() as conn:
        codes = [row[0] for row in conn.execute(query).fetchall()]

    # baostock 只有 sh / sz；北交所代码以 8 / 9 开头
    replaceable = [c for c in codes if not c.startswith(('8', '9'))]
    delete_only = [c for c in codes if c.startswith(('8', '9'))]
    return replaceable, delete_only


def replace_stock_history(code: str, dry_run: bool) -> tuple[bool, str]:
    """用 baostock 全历史覆盖单只股票。返回 (是否成功, 说明)。"""
    fresh = fetch_daily_bar_from_baostock(code, from_date=EARLIEST_DATE)
    if fresh is None or fresh.empty:
        return False, "baostock 取数失败"

    neg = int((fresh['close'] <= 0).sum())
    if neg:
        return False, f"baostock 数据本身含 {neg} 行非正价，放弃"

    old = query_daily_bars(code, from_date=EARLIEST_DATE)
    if old.empty:
        return False, "库中无数据"

    old_last = float(old['close'].iloc[-1])
    new_last = float(fresh['close'].iloc[-1])
    diff_pct = (new_last / old_last - 1) * 100 if old_last else float('nan')
    if abs(diff_pct) > LATEST_CLOSE_TOLERANCE_PCT:
        return False, (f"最新收盘价偏差 {diff_pct:+.2f}% 超阈值"
                       f"（{old_last:.2f} → {new_last:.2f}），基准不一致，放弃")

    old_neg = int((old['close'] <= 0).sum())
    detail = (f"{len(old)} → {len(fresh)} 行, 修掉 {old_neg} 行负价, "
              f"最新价 {new_last:.2f} (偏差 {diff_pct:+.2f}%)")

    if dry_run:
        return True, f"[dry-run] {detail}"

    # 先删后插：baostock 与库中行集可能有细微差异，避免留下孤立旧行
    with get_db_connection() as conn:
        conn.execute(f"DELETE FROM {DAILY_BAR_TABLE} WHERE code = ?", (code,))
        conn.commit()
    save_daily_bars_to_database(fresh)

    check = query_daily_bars(code, from_date=EARLIEST_DATE)
    remaining = int((check['close'] <= 0).sum()) if not check.empty else -1
    if remaining != 0:
        return False, f"替换后仍有 {remaining} 行非正价"
    return True, detail


def delete_nonpositive_rows(codes: list[str], dry_run: bool) -> int:
    """删除指定代码中 close<=0 的行（无替代源可用）。"""
    if not codes:
        return 0

    placeholders = ','.join('?' for _ in codes)
    count_sql = (f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} "
                 f"WHERE close <= 0 AND code IN ({placeholders})")
    with get_db_connection() as conn:
        n, = conn.execute(count_sql, codes).fetchone()

    if dry_run or not n:
        return n

    with get_db_connection() as conn:
        conn.execute(
            f"DELETE FROM {DAILY_BAR_TABLE} WHERE close <= 0 AND code IN ({placeholders})",
            codes,
        )
        conn.commit()
    return n


def delete_zero_ohlc_rows(dry_run: bool) -> int:
    """删除 OHLC 为 0 但 close 有值的残行。

    本地库（新浪源）通常不收停牌日，个别股票却留下了 open/high/low=0、volume=0
    的半截行（已用 baostock 确认这些日期确为停牌）。没有 OHLC 的 K 线无法参与
    形态与指标计算，删除比保留更安全。
    """
    condition = ("(open <= 0 OR high <= 0 OR low <= 0) AND close > 0")
    with get_db_connection() as conn:
        n, = conn.execute(
            f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} WHERE {condition}").fetchone()

    if dry_run or not n:
        return n

    with get_db_connection() as conn:
        conn.execute(f"DELETE FROM {DAILY_BAR_TABLE} WHERE {condition}")
        conn.commit()
    return n


def repair_nonfinite_change_pct(dry_run: bool) -> int:
    """重算 change_pct 中的 Inf / NaN。

    这些值是取数时对零价前收做除法留下的（(close/0 - 1) → Inf）。
    零价行删除后它们就成了陈旧值，需按实际前一交易日收盘价重算。
    """
    select_sql = f"""
        SELECT code, date, close, change_pct
        FROM {DAILY_BAR_TABLE}
        WHERE change_pct > 1e300 OR change_pct < -1e300 OR change_pct IS NULL
    """
    with get_db_connection() as conn:
        broken = conn.execute(select_sql).fetchall()

    if not broken:
        return 0

    updates = []
    with get_db_connection() as conn:
        for code, date, close, _ in broken:
            prev = conn.execute(
                f"SELECT close FROM {DAILY_BAR_TABLE} "
                f"WHERE code = ? AND date < ? ORDER BY date DESC LIMIT 1",
                (code, date),
            ).fetchone()
            if prev is None or not prev[0] or prev[0] <= 0:
                # 首行或前收仍不可用：涨跌幅无从计算，置 0（与其他源首行口径一致）
                updates.append((0.0, code, date))
            else:
                updates.append((round((close / prev[0] - 1) * 100, 2), code, date))

    if dry_run:
        return len(updates)

    with get_db_connection() as conn:
        conn.executemany(
            f"UPDATE {DAILY_BAR_TABLE} SET change_pct = ? WHERE code = ? AND date = ?",
            updates,
        )
        conn.commit()
    return len(updates)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只报告，不写库")
    args = parser.parse_args()

    with get_db_connection() as conn:
        before, = conn.execute(
            f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} WHERE close <= 0").fetchone()
    logger.info(f"=== 修复开始，当前 close<=0 共 {before} 行 "
                f"{'[dry-run]' if args.dry_run else ''} ===")

    replaceable, delete_only = find_negative_price_codes()
    logger.info(f"沪深（baostock 整段替换）: {len(replaceable)} 只")
    logger.info(f"北交所（只能删行）      : {len(delete_only)} 只")

    # ---- 1. 整段替换
    ok, failed = [], []
    for i, code in enumerate(replaceable, 1):
        success, detail = replace_stock_history(code, args.dry_run)
        mark = "✓" if success else "✗"
        logger.info(f"  [{i}/{len(replaceable)}] {mark} {code}: {detail}")
        (ok if success else failed).append(code)

    # ---- 2. 删除北交所脏数据
    deleted = delete_nonpositive_rows(delete_only, args.dry_run)
    logger.info(f"北交所零价行: {'待删' if args.dry_run else '已删'} {deleted} 行")

    # ---- 3. 删除 OHLC 残行（新浪源留下的停牌半截行）
    zero_ohlc = delete_zero_ohlc_rows(args.dry_run)
    logger.info(f"OHLC 为 0 的残行: {'待删' if args.dry_run else '已删'} {zero_ohlc} 行")

    # ---- 4. 重算 Inf / NaN 涨跌幅（零价行删除后遗留的陈旧值）
    fixed_chg = repair_nonfinite_change_pct(args.dry_run)
    logger.info(f"Inf/NaN change_pct: {'待重算' if args.dry_run else '已重算'} {fixed_chg} 行")

    # ---- 5. 校验
    with get_db_connection() as conn:
        after, = conn.execute(
            f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} WHERE close <= 0").fetchone()
        nonpos_ohlc, = conn.execute(
            f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} "
            f"WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0").fetchone()
        nonfinite, = conn.execute(
            f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} "
            f"WHERE change_pct > 1e300 OR change_pct < -1e300 OR change_pct IS NULL").fetchone()
        total, codes_n = conn.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT code) FROM {DAILY_BAR_TABLE}").fetchone()

    logger.info(f"=== 结果 ===")
    logger.info(f"替换成功 {len(ok)} 只，失败 {len(failed)} 只"
                + (f": {failed}" if failed else ""))
    logger.info(f"close<=0        : {before} → {after} 行")
    logger.info(f"任一 OHLC<=0    : {nonpos_ohlc} 行")
    logger.info(f"Inf/NaN 涨跌幅  : {nonfinite} 行")
    logger.info(f"全库: {total:,} 行 / {codes_n} 只")

    if failed and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
