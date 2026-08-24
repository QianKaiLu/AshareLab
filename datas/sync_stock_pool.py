"""股票池增量同步：补新股、剔退市、回补缺失详情。

权威来源是 ak.stock_info_a_code_name()（全市场代码表）。与 fetch_stock_infos()
的区别是不 DROP 表——那个函数先清表再逐股抓雪球详情，中途 abort 会留下残缺的池子，
而池子决定行情抓取范围，缺股票不会有任何提示。

雪球 stock_individual_basic_info_xq 目前要求登录态、对所有代码返回 400016，
所以新股先只写 code / name / exchange（行情抓取只需要 code），
详情字段留给 refresh_missing_details() 在雪球恢复后补。
"""
from collections import namedtuple
from datetime import datetime, timedelta
from typing import Optional

import akshare as ak

from datas.create_database import (
    DAILY_BAR_TABLE,
    DB_DIR,
    STOCK_INFO_TABLE,
    create_stock_info_table,
    get_db_connection,
)
from datas.fetch_stock_info import fetch_and_save_stock_info
from tools.log import get_fetch_logger
from tools.stock_tools import get_exchange_by_code, to_std_code

logger = get_fetch_logger()

# 与 datas/stock_index_list.py 的 .dummy 同一套做法：用空文件的 mtime 记上次同步时间
POOL_SYNC_MARKER = DB_DIR / ".pool_synced"
POOL_SYNC_INTERVAL_DAYS = 7

# 代码表低于此数视为抓取不完整，放弃本次同步：否则会把大批在市股票当成退市删掉
MIN_CODE_LIST_SIZE = 5000

# 单次允许剔除的上限。A 股一年退市约 50 只，一周不该到两位数；
# 超过说明代码表有问题，宁可跳过也不能误删历史行情
MAX_DELIST_PER_SYNC = 30

# 无行情源支持的品种，直接不入池：
# 689 = 科创板 CDR（存托凭证，如 689009 九号公司）。东财返回 RemoteDisconnected、
# 新浪返回 "No value to decode"，每轮日更都会白试两次且永远失败。
# 注意只排 689，正常科创板是 688（614 只），不能误伤。
UNSUPPORTED_CODE_PREFIXES = ("689",)

_InfoRow = namedtuple("_InfoRow", ["code", "name"])


def pool_sync_age_days() -> Optional[float]:
    """距上次成功同步的天数；从未同步过返回 None。"""
    if not POOL_SYNC_MARKER.exists():
        return None
    mtime = datetime.fromtimestamp(POOL_SYNC_MARKER.stat().st_mtime)
    return (datetime.now() - mtime).total_seconds() / 86400


def needs_pool_sync(interval_days: int = POOL_SYNC_INTERVAL_DAYS) -> bool:
    age = pool_sync_age_days()
    return age is None or age >= interval_days


def sync_stock_pool(dry_run: bool = False,
                    max_delist: int = MAX_DELIST_PER_SYNC) -> dict:
    """把 stock_base_info 对齐到最新代码表。

    返回 {"added": [...], "delisted": [...], "deleted_bars": int, "total": int}。
    delisted 为空列表且 added 为空列表时表示池子已是最新。
    """
    create_stock_info_table()

    try:
        fresh_df = ak.stock_info_a_code_name()
    except Exception as e:
        logger.error(f"代码表抓取失败，跳过池子同步: {e}")
        return {"added": [], "delisted": [], "deleted_bars": 0, "total": 0,
                "skipped": "代码表抓取失败"}

    if fresh_df is None or len(fresh_df) < MIN_CODE_LIST_SIZE:
        got = 0 if fresh_df is None else len(fresh_df)
        logger.error(f"代码表仅 {got} 条（阈值 {MIN_CODE_LIST_SIZE}），"
                     f"疑似抓取不完整，跳过池子同步")
        return {"added": [], "delisted": [], "deleted_bars": 0, "total": 0,
                "skipped": f"代码表仅 {got} 条"}

    fresh: dict[str, str] = {}
    skipped_unsupported = 0
    for row in fresh_df.itertuples():
        try:
            code = to_std_code(str(row.code))
        except Exception as e:
            logger.warning(f"跳过异常代码 {row.code}: {e}")
            continue
        if code.startswith(UNSUPPORTED_CODE_PREFIXES):
            skipped_unsupported += 1
            continue
        fresh[code] = row.name

    if skipped_unsupported:
        logger.info(f"跳过 {skipped_unsupported} 只无行情源支持的品种"
                    f"（前缀 {UNSUPPORTED_CODE_PREFIXES}）")

    with get_db_connection() as conn:
        existing = {r[0] for r in conn.execute(f"SELECT code FROM {STOCK_INFO_TABLE}")}

    # 已在池中的不支持品种单独清理：走 delisted 会把「品种不支持」记成「已退市」，
    # 而且它们本就没有行情，不该占用退市删除上限
    purged = sorted(c for c in existing if c.startswith(UNSUPPORTED_CODE_PREFIXES))
    if purged and not dry_run:
        placeholders = ','.join('?' for _ in purged)
        with get_db_connection() as conn:
            conn.execute(
                f"DELETE FROM {DAILY_BAR_TABLE} WHERE code IN ({placeholders})", purged)
            conn.execute(
                f"DELETE FROM {STOCK_INFO_TABLE} WHERE code IN ({placeholders})", purged)
            conn.commit()
        existing -= set(purged)

    added = sorted(set(fresh) - existing)
    delisted = sorted(existing - set(fresh) - set(purged))

    # ---- 剔除退市：先卡阈值，再连带删掉行情
    deleted_bars = 0
    if delisted and len(delisted) > max_delist:
        logger.error(f"待剔除 {len(delisted)} 只超过上限 {max_delist}，"
                     f"疑似代码表异常，本次不删: {delisted[:20]}...")
        delisted = []
    elif delisted and not dry_run:
        placeholders = ','.join('?' for _ in delisted)
        with get_db_connection() as conn:
            cur = conn.execute(
                f"DELETE FROM {DAILY_BAR_TABLE} WHERE code IN ({placeholders})",
                delisted)
            deleted_bars = cur.rowcount
            conn.execute(
                f"DELETE FROM {STOCK_INFO_TABLE} WHERE code IN ({placeholders})",
                delisted)
            conn.commit()
    elif delisted and dry_run:
        placeholders = ','.join('?' for _ in delisted)
        with get_db_connection() as conn:
            deleted_bars, = conn.execute(
                f"SELECT COUNT(*) FROM {DAILY_BAR_TABLE} WHERE code IN ({placeholders})",
                delisted).fetchone()

    # ---- 补新股：只写基础字段，行情抓取只需要 code
    if added and not dry_run:
        records = []
        for code in added:
            try:
                ex_code, ex_name = get_exchange_by_code(code)
            except ValueError as e:
                logger.warning(f"跳过 {code}: {e}")
                continue
            records.append((code, fresh[code], ex_code, ex_name))
        with get_db_connection() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {STOCK_INFO_TABLE} "
                f"(code, name, exchange_code, exchange_name) VALUES (?, ?, ?, ?)",
                records)
            conn.commit()
        added = [r[0] for r in records]

    # ---- 同步在市股票的简称（改名不影响行情，但影响查询与出图）
    renamed = 0
    if not dry_run:
        with get_db_connection() as conn:
            current = dict(conn.execute(
                f"SELECT code, name FROM {STOCK_INFO_TABLE}").fetchall())
            changes = [(fresh[c], c) for c, n in current.items()
                       if c in fresh and n != fresh[c]]
            if changes:
                conn.executemany(
                    f"UPDATE {STOCK_INFO_TABLE} SET name = ? WHERE code = ?", changes)
                conn.commit()
            renamed = len(changes)

    with get_db_connection() as conn:
        total, = conn.execute(f"SELECT COUNT(*) FROM {STOCK_INFO_TABLE}").fetchone()

    if not dry_run:
        POOL_SYNC_MARKER.touch()

    return {"added": added, "delisted": delisted, "deleted_bars": deleted_bars,
            "renamed": renamed, "purged": purged, "total": total}


def refresh_missing_details(limit: Optional[int] = None) -> tuple[int, int]:
    """为缺行业字段的股票补雪球详情，返回 (成功数, 尝试数)。

    与 fetch_stock_infos() 不同，这里不因连续失败 abort：雪球整体不可用是常态，
    补不上不影响行情，下次再试即可。
    """
    query = (f"SELECT code, name FROM {STOCK_INFO_TABLE} "
             f"WHERE idn_name IS NULL ORDER BY code")
    if limit:
        query += f" LIMIT {int(limit)}"

    with get_db_connection() as conn:
        pending = conn.execute(query).fetchall()

    if not pending:
        return 0, 0

    success = 0
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for code, name in pending:
            try:
                if fetch_and_save_stock_info(_InfoRow(code=code, name=name), cursor):
                    success += 1
            except Exception as e:
                logger.warning(f"详情补齐失败 {code}: {str(e)[:80]}")
        conn.commit()

    return success, len(pending)


if __name__ == "__main__":
    import json
    print(json.dumps(sync_stock_pool(dry_run=True), ensure_ascii=False, indent=2))
