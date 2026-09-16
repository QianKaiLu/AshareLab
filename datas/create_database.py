import akshare as ak
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path
import time
import json
from tools.log import get_fetch_logger
from contextlib import contextmanager

DB_DIR = Path(__file__).parent.parent / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "ashare_data.db"

STOCK_INFO_TABLE = "stock_base_info"
DAILY_BAR_TABLE = "stock_bars_daily_qfq"
INDEX_BAR_TABLE = "index_bars_daily"
INDEX_MIN_TABLE = "index_bars_min"

EARLIEST_DATE = "20050101"

logger = get_fetch_logger()

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def delete_table_if_exists(table_name: str):
    with get_db_connection() as conn:
        drop_table_query = f"DROP TABLE IF EXISTS {table_name};"
        conn.execute(drop_table_query)
        conn.commit()

def create_stock_info_table():
    with get_db_connection() as conn:
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {STOCK_INFO_TABLE} (
            code TEXT PRIMARY KEY, -- 股票代码(纯数字 code)
            exchange_code TEXT, -- 交易所代码 SH/SZ/BJ
            exchange_name TEXT, -- 交易所名称
            name TEXT, -- 公司简称
            org_name_en TEXT, -- 公司英文名称
            org_short_name_en TEXT, -- 公司英文简称
            full_name TEXT, -- 公司全称
            main_operation_business TEXT, -- 主要经营业务
            operating_scope TEXT, -- 经营范围
            org_introduction TEXT, -- 公司简介
            classi_name TEXT, -- 所有制性质名称
            list_date TEXT, -- 上市日期
            idn_code TEXT, -- 行业 code etc.BK0025
            idn_name TEXT -- 行业名称 etc."汽车整车"
        );
        """
        conn.execute(create_table_query)
        conn.commit()

def create_daily_bar_table():
    with get_db_connection() as conn:
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {DAILY_BAR_TABLE} (
            code TEXT NOT NULL, -- 股票代码 (裸 6 位数字，如 000001)
            date DATE NOT NULL, -- 交易日期
            open REAL, -- 开盘价
            close REAL, -- 收盘价
            high REAL, -- 最高价
            low REAL, -- 最低价
            volume INTEGER, -- 成交量
            amount REAL, -- 成交额
            amplitude REAL, -- 振幅
            change_pct REAL, -- 涨跌幅
            price_change REAL, -- 涨跌额
            turnover_rate REAL, -- 换手率
            PRIMARY KEY (code, date)
        );
        """
        conn.execute(create_table_query)

        # Add index for faster date-range queries
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{DAILY_BAR_TABLE}_date ON {DAILY_BAR_TABLE} (date);")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{DAILY_BAR_TABLE}_code ON {DAILY_BAR_TABLE} (code);")

        conn.commit()

def create_index_bar_table():
    with get_db_connection() as conn:
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {INDEX_BAR_TABLE} (
            symbol TEXT NOT NULL, -- 指数代码 (带交易所前缀，如 sh000001)
            date DATE NOT NULL, -- 交易日期
            open REAL, -- 开盘点位
            close REAL, -- 收盘点位
            high REAL, -- 最高点位
            low REAL, -- 最低点位
            volume INTEGER, -- 成交量 (指数为成分股汇总；统一为「股」，新浪原生口径)
            amount REAL, -- 成交额 (当前两个数据源都不提供，预留列)
            change_pct REAL, -- 涨跌幅，由本库计算
            price_change REAL, -- 涨跌额，由本库计算
            PRIMARY KEY (symbol, date)
        );
        """
        conn.execute(create_table_query)

        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{INDEX_BAR_TABLE}_date ON {INDEX_BAR_TABLE} (date);")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{INDEX_BAR_TABLE}_symbol ON {INDEX_BAR_TABLE} (symbol);")

        conn.commit()

def create_index_min_table():
    """指数分钟线。

    **只存基础粒度（30 分钟）**，60/120 由 `datas/fetch_index_min_bars.py` 的
    `aggregate_bars()` 在读时合成。这样有两个好处：一是源本身就缺 120 分钟，
    二是避免「原生 60 分钟」与「由 30 分钟合成的 60 分钟」两套数据并存而互相打架。
    """
    with get_db_connection() as conn:
        conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {INDEX_MIN_TABLE} (
            symbol TEXT NOT NULL, -- 指数代码 (带交易所前缀，如 sh000001)
            period INTEGER NOT NULL, -- 周期（分钟），当前只存 30
            dt TEXT NOT NULL, -- 时刻，YYYY-MM-DD HH:MM（bar 的**结束**时刻）
            open REAL, close REAL, high REAL, low REAL,
            volume INTEGER, -- 成交量 (股)
            PRIMARY KEY (symbol, period, dt)
        );
        """)
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{INDEX_MIN_TABLE}_dt "
                     f"ON {INDEX_MIN_TABLE} (dt);")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{INDEX_MIN_TABLE}_symbol "
                     f"ON {INDEX_MIN_TABLE} (symbol);")
        conn.commit()


def prepare_database(recreate: bool = False):
    if recreate:
        delete_table_if_exists(f"{STOCK_INFO_TABLE}")
        delete_table_if_exists(f"{DAILY_BAR_TABLE}")
        delete_table_if_exists(f"{INDEX_BAR_TABLE}")
        delete_table_if_exists(f"{INDEX_MIN_TABLE}")
    create_stock_info_table()
    create_daily_bar_table()
    create_index_bar_table()
    create_index_min_table()
    with get_db_connection() as conn:
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        conn.commit()

if __name__ == "__main__":
    # prepare_database(recreate=True)
    with get_db_connection() as conn:
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        conn.commit()
    # delete_table_if_exists(f"{DAILY_BAR_TABLE}")
    # create_daily_bar_table()