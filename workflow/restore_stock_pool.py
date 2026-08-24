"""从备份恢复 stock_base_info，并补齐新上市股票。

雪球 stock_individual_basic_info_xq 现要求登录态（400016），逐股详情抓不了。
但备份里的详情字段完好，且 ak.stock_info_a_code_name() 仍可用，
所以：备份的 base_info 全量搬过来 + 新代码补基础字段（详情留空）。

用法: python workflow/restore_stock_pool.py <备份库路径>
"""
import sqlite3
import sys

import akshare as ak

from datas.create_database import DB_PATH, STOCK_INFO_TABLE, create_stock_info_table
from tools.log import get_fetch_logger
from tools.stock_tools import get_exchange_by_code, to_std_code

logger = get_fetch_logger()

backup_path = sys.argv[1] if len(sys.argv) > 1 else None
if not backup_path:
    logger.error("需要指定备份库路径")
    sys.exit(1)

create_stock_info_table()

# ---- 1. 从备份搬 base_info
with sqlite3.connect(DB_PATH) as conn:
    conn.execute("ATTACH DATABASE ? AS bak", (backup_path,))
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({STOCK_INFO_TABLE})")]
    col_list = ", ".join(cols)
    cur = conn.execute(
        f"INSERT OR REPLACE INTO {STOCK_INFO_TABLE} ({col_list}) "
        f"SELECT {col_list} FROM bak.{STOCK_INFO_TABLE}"
    )
    restored = cur.rowcount
    conn.commit()
    conn.execute("DETACH DATABASE bak")
logger.info(f"从备份恢复 {restored} 只")

# ---- 2. 补新上市（雪球详情字段留空，行情抓取只需 code）
fresh = ak.stock_info_a_code_name()
fresh["code"] = fresh["code"].map(to_std_code)

with sqlite3.connect(DB_PATH) as conn:
    existing = {r[0] for r in conn.execute(f"SELECT code FROM {STOCK_INFO_TABLE}")}
    added = []
    for row in fresh.itertuples():
        if row.code in existing:
            continue
        try:
            ex_code, ex_name = get_exchange_by_code(row.code)
        except ValueError as e:
            logger.warning(f"跳过 {row.code}: {e}")
            continue
        conn.execute(
            f"INSERT OR REPLACE INTO {STOCK_INFO_TABLE} "
            f"(code, name, exchange_code, exchange_name) VALUES (?, ?, ?, ?)",
            (row.code, row.name, ex_code, ex_name),
        )
        added.append(row.code)
    conn.commit()

logger.info(f"新增 {len(added)} 只（详情字段待雪球恢复后补）: {added}")

with sqlite3.connect(DB_PATH) as conn:
    total, = conn.execute(f"SELECT COUNT(*) FROM {STOCK_INFO_TABLE}").fetchone()
    no_industry, = conn.execute(
        f"SELECT COUNT(*) FROM {STOCK_INFO_TABLE} WHERE idn_name IS NULL"
    ).fetchone()
logger.info(f"股票池共 {total} 只，其中 {no_industry} 只缺行业字段")
