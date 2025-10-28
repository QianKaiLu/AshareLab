import akshare as ak
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path
import time
import json

DB_DIR = Path(__file__).parent.parent / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "ashare_data.db"

STOCK_INFO_TABLE = "stock_base_info"
DAILY_BAR_TABLE = "stock_bars_daily_qfq"

def create_data_base():
    conn = sqlite3.connect(DB_PATH)
    conn.close()

def delete_table_if_exists(table_name: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    drop_table_query = f"DROP TABLE IF EXISTS {table_name};"
    cursor.execute(drop_table_query)
    conn.commit()
    conn.close()

def create_stock_info_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    cursor.execute(create_table_query)
    conn.commit()
    conn.close()

def create_daily_bar_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {DAILY_BAR_TABLE} (
        code TEXT NOT NULL, -- 股票代码 (带交易所前缀)
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
    cursor.execute(create_table_query)

    # Add index for faster date-range queries
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{DAILY_BAR_TABLE}_date ON {DAILY_BAR_TABLE} (date);")
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{DAILY_BAR_TABLE}_code ON {DAILY_BAR_TABLE} (code);")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_data_base()
    delete_table_if_exists(f"{STOCK_INFO_TABLE}")
    delete_table_if_exists(f"{DAILY_BAR_TABLE}")
    create_stock_info_table()
    create_daily_bar_table()