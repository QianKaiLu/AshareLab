import akshare as ak
import sqlite3
import pandas as pd
from pathlib import Path
import json
from tools.log import get_fetch_logger
from tools.stock_tools import to_std_code
from tools.tools import ms_timestamp_to_date, format_date_input_to_yyyy_mm_dd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any
from datetime import datetime
from datas.create_database import DB_PATH, DAILY_BAR_TABLE, EARLIEST_DATE, STOCK_INFO_TABLE, get_db_connection
from contextlib import closing

logger = get_fetch_logger()

def query_daily_bars(
    code: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Optional[pd.DataFrame]:
    """
    Query daily bar data from SQLite database by stock code and date range.
    
    Args:
        code: Stock code e.g. "002594"
        from_date: Start date as string (format: YYYYMMDD or YYYY-MM-DD), optional
        to_date: End date as string (format: YYYYMMDD or YYYY-MM-DD), optional
    
    Returns:
        pd.DataFrame with daily bars, sorted by date; or None if no data found
    """
    conn = None
    try:
        std_code = to_std_code(code)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", 
            (DAILY_BAR_TABLE,)
        )
        if cursor.fetchone() is None:
            logger.warning(f"Table '{DAILY_BAR_TABLE}' does not exist in database.")
            return None
        
        query = f"SELECT * FROM {DAILY_BAR_TABLE} WHERE code = ?"
        params: list[Any] = [std_code]

        if from_date:
            formatted_from = format_date_input_to_yyyy_mm_dd(from_date)
            query += " AND date >= ?"
            params.append(formatted_from)

        if to_date:
            formatted_to = format_date_input_to_yyyy_mm_dd(to_date)
            query += " AND date <= ?"
            params.append(formatted_to)

        query += " ORDER BY date ASC"

        # Execute query
        df = pd.read_sql_query(query, conn, params=params, parse_dates=['date'])

        if df.empty:
            logger.info(f"No daily bar data found for {std_code} between {from_date} and {to_date}")
            return None

        # Log result
        start_str = df['date'].min().strftime("%Y-%m-%d")
        end_str = df['date'].max().strftime("%Y-%m-%d")
        logger.info(f"📌 Queried {len(df)} rows for {std_code} [{start_str} ~ {end_str}]")

        return df

    except Exception as e:
        logger.error(f"❌ Error querying daily bar data for {code}: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def query_latest_bars(
    code: str,
    n: int = 1
) -> Optional[pd.DataFrame]:
    """
    Query the latest N trading days' daily bar data using efficient SQL LIMIT.
    
    Args:
        code (str): Stock code, e.g. '321', '000321', 'SH600000', '600000.SH'
        n (int): Number of most recent trading days to query. Must be >= 1.

    Returns:
        pd.DataFrame sorted by date ascending; or None if not found
    """
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")

    conn = None
    try:
        std_code = to_std_code(code)
    except Exception as e:
        logger.warning(f"Invalid stock code '{code}': {e}")
        return None

    try:
        conn = sqlite3.connect(DB_PATH)

        cursor = conn.cursor()
        columns = [
            'code', 'date', 'open', 'close', 'high', 'low',
            'volume', 'amount', 'amplitude', 'change_pct',
            'price_change', 'turnover_rate'
        ]
        query = f"""
        SELECT *
        FROM {DAILY_BAR_TABLE}
        WHERE code = ?
        ORDER BY date DESC
        LIMIT ?
        """

        df = pd.read_sql_query(
            query, conn,
            params=(std_code, n),
            parse_dates=['date']
        )

        if df.empty:
            logger.info(f"No data found for {std_code} in latest {n} days.")
            return None

        result = df[::-1].reset_index(drop=True)

        if result.empty:
            return None

        start_str = result['date'].min().strftime("%Y-%m-%d")
        end_str = result['date'].max().strftime("%Y-%m-%d")
        count = len(result)
        logger.info(f"📈 Got last {count} trading day(s) for {std_code} [{start_str} ~ {end_str}]")

        return result

    except Exception as e:
        logger.error(f"❌ Failed to query latest {n} bars for {std_code}: {e}", exc_info=True)
        return None

    finally:
        if conn:
            conn.close()

def get_latest_date_with_data(
    code: str
) -> Optional[datetime]:
    """
    Get the latest date for which daily bar data exists for the given stock code.
    
    Args:
        code (str): Stock code, e.g. '321', '000321', 'SH600000', '600000.SH'
    """
    try:
        std_code = to_std_code(code)
    except Exception as e:
        logger.warning(f"Invalid stock code '{code}': {e}")
        return None

    earliest_date = pd.to_datetime(EARLIEST_DATE)

    try:
        with sqlite3.connect(DB_PATH) as conn:
            query = f"SELECT MAX(date) FROM {DAILY_BAR_TABLE} WHERE code = ?"
            result = conn.execute(query, (std_code,)).fetchone()

            if result[0] is not None:
                latest_date = pd.to_datetime(result[0])
                return latest_date
            return earliest_date

    except Exception as e:
        return earliest_date

def get_stock_info(
        code: str
)-> Optional[pd.DataFrame]:
    """
    Get the stock name for the given stock code.
    """
    try:
        std_code = to_std_code(code)
    except Exception as e:
        logger.warning(f"Invalid stock code '{code}': {e}")
        return None

def get_stock_info_by_code(code: str) -> pd.DataFrame:
    """
    Get stock information for a single stock code.
    """
    try:
        std_code = to_std_code(code)
    except Exception as e:
        logger.warning(f"Invalid stock code '{code}': {e}")
        return pd.DataFrame()

    query = f"SELECT * FROM {STOCK_INFO_TABLE} WHERE code = ?"
    with get_db_connection() as conn:
        df = pd.read_sql_query(query, conn, params=(std_code,))

    if df.empty:
        return pd.DataFrame()
    
    df.set_index('code', inplace=True)
    return df


def get_stock_info_by_codes(codes: list) -> pd.DataFrame:
    """
    Get stock information for multiple stock codes.
    """
    std_codes = []
    for code in codes:
        try:
            std_code = to_std_code(code)
            std_codes.append(std_code)
        except Exception as e:
            logger.warning(f"Invalid stock code '{code}': {e}")
            continue

    if not std_codes:
        return pd.DataFrame()

    placeholders = ','.join('?' for _ in std_codes)
    query = f"SELECT * FROM {STOCK_INFO_TABLE} WHERE code IN ({placeholders})"
    with get_db_connection() as conn:
        df = pd.read_sql_query(query, conn, params=std_codes)

    df.set_index('code', inplace=True)
    return df
    
if __name__ == "__main__":
    # Test query_daily_bars
    codes = ['600570', '000332', '1']
    df = get_stock_info_by_code(codes[0])
    print(df['name'])