import akshare as ak
import sqlite3
import pandas as pd
from pathlib import Path
from tools.log import get_fetch_logger
from tools.stock_tools import get_exchange_by_code
from tools.tools import ms_timestamp_to_date
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any
from datetime import datetime
from datas.create_database import DB_PATH, DAILY_BAR_TABLE, delete_table_if_exists, create_daily_bar_table
from datas.query_stock import query_daily_bars, query_latest_bars
from datas.export import export_bars_to_csv
import time
from contextlib import closing

logger = get_fetch_logger()
FETCH_WORKERS = 10
START_DATE_DEFAULT = "20100101"

def fetch_daily_bar_from_akshare(
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

        # Drop invalid dates
        original_len = len(df)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date']).copy()
        dropped_count = original_len - len(df)
        if dropped_count > 0:
            logger.warning(f"Dropped {dropped_count} rows with invalid dates for {code}")
            
        # Convert data types
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

def save_daily_bars_to_database(df: pd.DataFrame):
    """
    Save daily bar DataFrame to SQLite database with UPSERT behavior.
    If (code, date) exists → UPDATE; else → INSERT.
    Requires SQLite >= 3.24.0 and PRIMARY KEY(code, date) in table.
    """
    if df.empty:
        logger.warning("Warning: Empty DataFrame, nothing to save.")
        return

    write_df = df.copy()
    write_df['date'] = write_df['date'].dt.strftime("%Y-%m-%d")  # 转为字符串存入 SQLite

    def upsert_method(table, cursor, keys, data_iter):
        """Custom upsert for SQLite 3.24+ using ON CONFLICT DO UPDATE"""
        columns = ", ".join(keys)
        placeholders = ", ".join([f":{key}" for key in keys])
        conflict_target = "(code, date)"

        assignments = ", ".join([
            f"{col} = excluded.{col}"
            for col in keys
            if col not in ('code', 'date')
        ])

        sql = f"""
            INSERT INTO {table.name} ({columns})
            VALUES ({placeholders})
            ON CONFLICT {conflict_target} DO UPDATE SET
            {assignments};
        """

        try:
            cursor.executemany(
                sql,
                ({k: v for k, v in zip(keys, row)} for row in data_iter)
            )
        except Exception as e:
            logger.error(f"❌ Upsert failed: {e}\nSQL: {sql}")
            raise

    with sqlite3.connect(DB_PATH) as conn:
        try:
            write_df.to_sql(
                name=DAILY_BAR_TABLE,
                con=conn,
                if_exists='append',
                index=False,
                method=upsert_method,
                chunksize=5000
            )
            logger.info(f"💾 Upserted {len(write_df)} records into {DAILY_BAR_TABLE}")
        except Exception as e:
            logger.error(f"💔 Failed to upsert bars: {e}", exc_info=True)


if __name__ == "__main__":
    delete_table_if_exists(DAILY_BAR_TABLE)
    create_daily_bar_table()

    stock_codes = ['600570', '002594', '002714']
    for code in stock_codes:
        df_bars = fetch_daily_bar_from_akshare(code=code, from_date='20200101')
        if df_bars is not None:
            save_daily_bars_to_database(df_bars)
        else:
            logger.error(f"Failed to fetch daily bars for {code}")

    # time.sleep(2)  # wait for db writes to complete
    # df = query_latest_bars('600570', n=300)
    # export_bars_to_csv(df, only_base_info=True)
