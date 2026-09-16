import akshare as ak
import sqlite3
import pandas as pd
from pathlib import Path
import json
from tools.log import get_fetch_logger
from tools.stock_tools import to_std_code
from tools.times import ms_timestamp_to_date, format_date_input_to_yyyy_mm_dd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any
from datetime import datetime
from datas.create_database import DB_PATH, DAILY_BAR_TABLE, EARLIEST_DATE, INDEX_BAR_TABLE, STOCK_INFO_TABLE, get_db_connection
from contextlib import closing

logger = get_fetch_logger()

def query_daily_bars(
    code: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> pd.DataFrame:
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
            return pd.DataFrame()
        
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
            return pd.DataFrame()

        return df

    except Exception as e:
        logger.error(f"❌ Error querying daily bar data for {code}: {e}", exc_info=True)
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()
            
def query_bars_by_days(
    code: str,
    days: int,
    to_date: Optional[str] = None
) -> pd.DataFrame:
    """
    Query daily bar data for the last N trading days up to to_date.
    
    Args:
        code (str): Stock code, e.g. '321', '000321', 'SH600000', '600000.SH'
        days (int): Number of trading days to query. Must be >= 1.
        to_date (str, optional): End date as string (format: YYYYMMDD or YYYY-MM-DD). 
                                 If None, use the latest available date.
    Returns:
        pd.DataFrame sorted by date ascending; or None if not found
    """
    if days < 1:
        raise ValueError(f"days must be at least 1, got {days}")

    conn = None
    try:
        std_code = to_std_code(code)
    except Exception as e:
        logger.warning(f"Invalid stock code '{code}': {e}")
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(DB_PATH)
        
        params: list[Any] = [std_code]

        query = f"""
        SELECT *
        FROM {DAILY_BAR_TABLE}
        WHERE code = ?
        """

        if to_date:
            formatted_to = format_date_input_to_yyyy_mm_dd(to_date)
            query += " AND date <= ?"
            params.append(formatted_to)

        query += """
        ORDER BY date DESC
        LIMIT ?
        """
        params.append(days)

        df = pd.read_sql_query(
            query, conn,
            params=tuple(params),
            parse_dates=['date']
        )

        if df.empty:
            logger.info(f"No data found for {std_code} in last {days} days up to {to_date}.")
            return pd.DataFrame()

        result = df[::-1].reset_index(drop=True)

        if result.empty:
            return pd.DataFrame()

        return result

    except Exception as e:
        logger.error(f"❌ Failed to query last {days} bars for {std_code}: {e}", exc_info=True)
        return pd.DataFrame()

    finally:
        if conn:
            conn.close()

def query_latest_bars(
    code: str,
    n: int = 1
) -> pd.DataFrame:
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
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(DB_PATH)
        
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
            return pd.DataFrame()

        result = df[::-1].reset_index(drop=True)

        if result.empty:
            return pd.DataFrame()

        return result

    except Exception as e:
        logger.error(f"❌ Failed to query latest {n} bars for {std_code}: {e}", exc_info=True)
        return pd.DataFrame()

    finally:
        if conn:
            conn.close()

def get_latest_date_by_code(
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

def get_stock_info_by_name(name: str) -> pd.DataFrame:
    """
    Get stock information for a single stock name.
    """
    query = f"SELECT * FROM {STOCK_INFO_TABLE} WHERE name = ?"
    with get_db_connection() as conn:
        df = pd.read_sql_query(query, conn, params=(name,))

    if df.empty:
        return pd.DataFrame()
    
    df.set_index('code', inplace=True)
    return df

def get_stock_code_by_name(name: str) -> Optional[str]:
    """
    Get stock code for a given stock name (fuzzy match).
    """
    query = f"SELECT code FROM {STOCK_INFO_TABLE} WHERE name LIKE ?"
    # 注意：参数中加入通配符，而不是拼进 SQL 语句
    with get_db_connection() as conn:
        result = conn.execute(query, (f"%{name}%",)).fetchone()

    return result[0] if result else None  # 更简洁的写法

def format_stock_info(df: pd.DataFrame, level: str = "medium") -> str:
    if df.empty:
        return "❌ No stock info found"

    s = df.iloc[0]
    safe = lambda x: str(x) if pd.notna(x) else ""

    code = s.name
    name = safe(s['name'])
    exchange = f"{safe(s['exchange_name'])} ({safe(s['exchange_code'])})"
    list_date = safe(s['list_date'])
    industry = safe(s['idn_name'])

    if level == "brief":
        return f"{name} ({code}) — {industry}"
    
    elif level == "medium":
        return (
            f"Code: {code}\n"
            f"Name: {name}\n"
            f"Exchange: {exchange}\n"
            f"Listing Date: {list_date}\n"
            f"Industry: {industry}"
        )
    
    elif level == "detailed":
        return (
            f"Stock Code: {code}\n"
            f"Company Name: {name}\n"
            f"Full Name: {safe(s['full_name'])}\n"
            f"Exchange: {exchange}\n"
            f"Listing Date: {list_date}\n"
            f"Industry: {industry}\n"
            f"Main Business: {safe(s['main_operation_business'])}\n"
            f"Business Scope: {safe(s['operating_scope'])}\n"
            f"Introduction: {safe(s['org_introduction'])}"
        )
    
    else:
        raise ValueError("level must be 'brief', 'medium', or 'detailed'")

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

def query_stock_industry_map() -> dict[str, str]:
    """
    Map stock code -> industry name (stock_base_info.idn_name).

    Codes without an industry are omitted. Returns {} when the table is unavailable.
    """
    query = (f"SELECT code, idn_name FROM {STOCK_INFO_TABLE} "
             f"WHERE idn_name IS NOT NULL AND idn_name <> ''")
    try:
        with get_db_connection() as conn:
            rows = conn.execute(query).fetchall()
        return {str(r[0]): str(r[1]) for r in rows}
    except Exception as e:
        logger.error(f"❌ Error reading industry map: {e}", exc_info=True)
        return {}

def query_close_matrix(
    from_date: str,
    to_date: str,
    codes: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Pivot of daily closes for a date range: index=date, columns=code.

    Built for cross-sectional work (sector aggregation, breadth). Values are closes,
    not adjusted again — stock_bars_daily_qfq is already qfq. Missing cells (suspended
    days) stay NaN. Returns an empty DataFrame when nothing matches.
    """
    try:
        start = format_date_input_to_yyyy_mm_dd(from_date)
        end = format_date_input_to_yyyy_mm_dd(to_date)
    except Exception as e:
        logger.warning(f"Invalid date range {from_date}~{to_date}: {e}")
        return pd.DataFrame()

    query = (f"SELECT code, date, close FROM {DAILY_BAR_TABLE} "
             f"WHERE date >= ? AND date <= ?")
    params: list[Any] = [start, end]
    if codes:
        placeholders = ",".join("?" for _ in codes)
        query += f" AND code IN ({placeholders})"
        params.extend(codes)

    try:
        with get_db_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params, parse_dates=['date'])
        if df.empty:
            return pd.DataFrame()
        return df.pivot_table(index="date", columns="code", values="close", aggfunc="last")
    except Exception as e:
        logger.error(f"❌ Error building close matrix: {e}", exc_info=True)
        return pd.DataFrame()

def query_all_stock_code_list() -> pd.Series:
    """
    Query all stock basic information from the database.
    """
    query = f"SELECT code, name FROM {STOCK_INFO_TABLE}"
    with get_db_connection() as conn:
        df = pd.read_sql_query(query, conn)

    return df['code'].map(to_std_code)

# ------------------------------------------------------------------ 指数日线
# 指数代码空间与个股冲突：to_std_code('sh000001') == '000001' == 平安银行，
# 所以下面几个函数刻意不调 to_std_code，也不复用上面的个股查询函数。

def query_index_bars(
    symbol: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Query index daily bars by symbol (e.g. 'sh000001') and date range.

    Unlike the stock queries above, this does NOT run to_std_code: index symbols
    live in a separate namespace ('sh000001' would otherwise collapse onto the
    stock code '000001').

    Returns:
        pd.DataFrame sorted by date; empty DataFrame if nothing found.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        query = f"SELECT * FROM {INDEX_BAR_TABLE} WHERE symbol = ?"
        params: list[Any] = [symbol]

        if from_date:
            query += " AND date >= ?"
            params.append(format_date_input_to_yyyy_mm_dd(from_date))
        if to_date:
            query += " AND date <= ?"
            params.append(format_date_input_to_yyyy_mm_dd(to_date))

        query += " ORDER BY date ASC"
        df = pd.read_sql_query(query, conn, params=params, parse_dates=['date'])

        if df.empty:
            logger.info(f"No index bars found for {symbol} between {from_date} and {to_date}")
            return pd.DataFrame()
        return df

    except Exception as e:
        logger.error(f"❌ Error querying index bars for {symbol}: {e}", exc_info=True)
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def query_index_latest_bars(symbol: str, n: int = 1) -> pd.DataFrame:
    """
    Query the latest n index bars for symbol, returned in ascending date order.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        query = (f"SELECT * FROM {INDEX_BAR_TABLE} WHERE symbol = ? "
                 f"ORDER BY date DESC LIMIT ?")
        df = pd.read_sql_query(query, conn, params=(symbol, n), parse_dates=['date'])

        if df.empty:
            return pd.DataFrame()
        return df[::-1].reset_index(drop=True)

    except Exception as e:
        logger.error(f"❌ Error querying latest {n} index bars for {symbol}: {e}", exc_info=True)
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def get_latest_index_date(symbol: str) -> Optional[datetime]:
    """
    Get the latest date for which index bars exist for the given symbol.
    Returns None when the symbol has no data at all.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                f"SELECT MAX(date) FROM {INDEX_BAR_TABLE} WHERE symbol = ?", (symbol,)
            ).fetchone()
        return pd.to_datetime(row[0]) if row and row[0] else None
    except Exception as e:
        logger.error(f"❌ Error getting latest index date for {symbol}: {e}", exc_info=True)
        return None

def get_earliest_index_date(symbol: str) -> Optional[datetime]:
    """
    Get the earliest date for which index bars exist for the given symbol.
    Returns None when the symbol has no data at all.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                f"SELECT MIN(date) FROM {INDEX_BAR_TABLE} WHERE symbol = ?", (symbol,)
            ).fetchone()
        return pd.to_datetime(row[0]) if row and row[0] else None
    except Exception as e:
        logger.error(f"❌ Error getting earliest index date for {symbol}: {e}", exc_info=True)
        return None

def query_index_min_bars(
    symbol: str,
    period: int = 30,
    from_dt: Optional[str] = None,
    to_dt: Optional[str] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Query index minute bars, aggregated to `period` (30 / 60 / 120).

    Only 30-minute bars are stored; 60 / 120 are synthesized on read via
    `fetch_index_min_bars.aggregate_bars()`. Same reason as the daily index
    queries: symbol is 'sh000001'-style and must NOT go through to_std_code.

    Returns:
        pd.DataFrame with a datetime `dt` column, ascending; empty if nothing found.
    """
    from datas.create_database import INDEX_MIN_TABLE
    from datas.fetch_index_min_bars import BASE_PERIOD, aggregate_bars

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        query = f"SELECT * FROM {INDEX_MIN_TABLE} WHERE symbol = ? AND period = ?"
        params: list[Any] = [symbol, BASE_PERIOD]
        if from_dt:
            query += " AND dt >= ?"
            params.append(str(from_dt))
        if to_dt:
            query += " AND dt <= ?"
            params.append(str(to_dt))
        query += " ORDER BY dt ASC"

        df = pd.read_sql_query(query, conn, params=params)
        if df.empty:
            return pd.DataFrame()

        df["dt"] = pd.to_datetime(df["dt"])
        if period != BASE_PERIOD:
            df = aggregate_bars(df, period)
        if limit:
            df = df.tail(limit).reset_index(drop=True)
        return df

    except Exception as e:
        logger.error(f"❌ Error querying min bars for {symbol}: {e}", exc_info=True)
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()

def query_index_symbol_list() -> list[str]:
    """List all index symbols present in the database, sorted."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT symbol FROM {INDEX_BAR_TABLE} ORDER BY symbol"
            ).fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        logger.error(f"❌ Error listing index symbols: {e}", exc_info=True)
        return []

if __name__ == "__main__":
    # Test query_daily_bars
    # codes = ['600570', '000332', '1']
    # df = get_stock_info_by_code(codes[0])
    df = query_all_stock_code_list()
    print(df)