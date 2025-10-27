import akshare as ak
import sqlite3
import pandas as pd
from pathlib import Path
import json
from tools.log import get_fetch_logger
from tools.stock_tools import get_exchange_by_code
from tools.tools import ms_timestamp_to_date
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any
from datetime import datetime
from datas.create_database import DB_PATH, DAILY_BAR_TABLE, delete_table_if_exists, create_daily_bar_table

logger = get_fetch_logger()
FETCH_WORKERS = 10
START_DATE_DEFAULT = "20100101"

def fetch_daily_bar(
    code: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    adjust: str = "qfq"  # qfq:前复权, hfq:后复权, "" :不复权
) -> Optional[pd.DataFrame]:
    """
    fetch daily stock bars from akshare
    Args:
        code: stock code with exchange prefix, e.g. SH600000
        from_date: start date in YYYYMMDD format
        to_date: end date in YYYYMMDD format
        adjust: adjustment type, "qfq" for 前复权, "hfq" for 后复权, "" for no adjustment
    Returns:
        DataFrame with daily bars or None if failed
    """
    if from_date is None:
        from_date = START_DATE_DEFAULT

    # default to today   
    if to_date is None:
        to_date = datetime.now().strftime("%Y%m%d")

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=from_date,
            end_date=to_date,
            adjust=adjust
        )

        if df.empty:
            logger.warning(f"No daily bar data returned from akshare for code={code}")
            return None
        
        column_mapping = {
            '日期': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            '成交额': 'amount',
            '振幅': 'amplitude',
            '涨跌幅': 'change_pct',
            '涨跌额': 'price_change',
            '换手率': 'turnover_rate'
        }
        df = df.rename(columns=column_mapping)

        # required columns
        required_columns = ['date', 'high', 'low', 'close', 'open', 'volume', 'amount', 'amplitude', 'change_pct', 'price_change', 'turnover_rate']
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            logger.error(f"Missing required columns after mapping: {missing_cols} for {code}")
            return None

        df['code'] = code

        final_columns = [
            'code', 'date', 'open', 'close', 'high', 'low',
            'volume', 'amount', 'amplitude', 'change_pct', 
            'price_change', 'turnover_rate'
        ]
        available_columns = [col for col in final_columns if col in df.columns]
        df = df[available_columns]

        df['date'] = pd.to_datetime(df['date'])
        for col in ['open', 'close', 'high', 'low', 'amount', 'amplitude', 'change_pct', 'price_change', 'turnover_rate']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype('int64') * 100

        df.drop_duplicates(subset=['code', 'date'], keep='last', inplace=True)
        df.sort_values(by='date', inplace=True)
        df.reset_index(drop=True, inplace=True)

        start_str = df['date'].min().strftime("%Y-%m-%d")
        end_str = df['date'].max().strftime("%Y-%m-%d")
        logger.info(f"Fetched {len(df)} daily bars for {code} [{start_str} ~ {end_str}]")

        return df
    except Exception as e:
        logger.error(f"Error fetching data for {code}: {e}", exc_info=True)
        return None

def save_to_database(df: pd.DataFrame, table_name: str = DAILY_BAR_TABLE, db_path: Path = DB_PATH):
    """
    将清洗好的日线数据保存到 SQLite 数据库
    """
    if df.empty:
        print("Warning: Empty DataFrame, nothing to save.")
        return

    conn = sqlite3.connect(db_path)
    try:
        df.to_sql(
            name=table_name,
            con=conn,
            if_exists='append',      # 'fail', 'replace', 'append'
            index=False,             # 不要将 pandas 索引写入数据库
            method='multi',          # 加快插入速度
            chunksize=1000           # 分块插入大数据
        )
        print(f"✅ Successfully saved {len(df)} rows to `{table_name}`")
    except Exception as e:
        print(f"❌ Error saving to database: {e}")
    finally:
        conn.close()

def load_from_database(
    code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    table_name: str = DAILY_BAR_TABLE,
    db_path: Path = DB_PATH
) -> pd.DataFrame:
    """
    从数据库加载某只股票的日线数据
    """
    conn = sqlite3.connect(db_path)
    
    # 构建查询语句
    where_clauses = ["code = ?"]
    params = [code]

    if start_date:
        where_clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("date <= ?")
        params.append(end_date)

    where_str = " AND ".join(where_clauses)
    query = f"SELECT * FROM {table_name} WHERE {where_str} ORDER BY date ASC"

    df = pd.read_sql(query, conn, params=params, parse_dates=['date'])
    conn.close()

    return df
