import akshare as ak
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path
import time
import json

"""
我需要构建一个 a 股数据库，数据来源主要是 akshare，用于之后的画图、筛选、技术分析等。
首先我需要基于 akshare 获取 A 股股票列表，并存储到 SQLite 数据库中，请问表结构怎么设计， python 中如何创建数据库？
"""

DB_DIR = Path(__file__).parent.parent / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "ashare_data.db"

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
    create_table_query = """
    CREATE TABLE IF NOT EXISTS stock_base_info (
        code TEXT PRIMARY KEY, -- 股票代码(纯数字 code)
        name TEXT, -- 公司简称
        org_name_en TEXT, -- 公司英文名称
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

if __name__ == "__main__":
    create_data_base()
    delete_table_if_exists("stock_base_info")
    create_stock_info_table()