import akshare as ak
import sqlite3
import pandas as pd
from pathlib import Path
from tools.log import get_fetch_logger
from tools.stock_tools import get_exchange_by_code, to_dot_ex_code, MARKED_CLOSE_HOUR, latest_trade_day
from tools.times import ms_timestamp_to_date
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any
from datetime import datetime, timedelta
from datas.create_database import DB_PATH, DAILY_BAR_TABLE, EARLIEST_DATE, get_db_connection
from datas.query_stock import query_daily_bars, query_latest_bars, get_latest_date_by_code
from tools.export import export_bars_to_csv
import time 
from contextlib import closing
from ai.ai_kbar_analyses import analyze_kbar_data_openai
from tools.markdown_lab import save_md_to_file_name, render_markdown_to_image_file_name
from datas.query_stock import get_stock_info_by_code
import tushare as ts
from ratelimit import limits, sleep_and_retry
from tools.tushare_rate_limiter import tushare_token_rate_limiter

logger = get_fetch_logger()
FETCH_WORKERS = 10

# eastmoney 被限流/封禁时连续失败的计数，达到阈值后直接走新浪源，避免每只股票都白试一次东财
_eastmoney_failures = 0
_EASTMONEY_BREAKER = 10

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
    global _eastmoney_failures
    if _eastmoney_failures >= _EASTMONEY_BREAKER:
        logger.warning(f"{code}: eastmoney 连续失败 {_eastmoney_failures} 次，直接使用新浪源")
        return fetch_daily_bar_from_sina(code=code, from_date=from_date, to_date=to_date, adjust=adjust)

    if from_date is None:
        from_date = EARLIEST_DATE

    # default to today if marked close hour has passed
    if to_date is None:
        to_date = latest_trade_day().strftime("%Y%m%d")

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
        required_columns = ['date', 'high', 'low', 'close', 'open', 'volume']
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
            df[col] = pd.to_numeric(df[col], errors='coerce').round(2)
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype('int64') * 100

        df.drop_duplicates(subset=['code', 'date'], keep='last', inplace=True)
        df.sort_values(by='date', inplace=True)
        df.reset_index(drop=True, inplace=True)

        start_str = df['date'].min().strftime("%Y-%m-%d")
        end_str = df['date'].max().strftime("%Y-%m-%d")
        # logger.info(f"Fetched {len(df)} daily bars for {code} [{start_str} ~ {end_str}]")

        _eastmoney_failures = 0
        return df
    except Exception as e:
        _eastmoney_failures += 1
        logger.error(f"Error fetching data for {code}: {e}", exc_info=True)
        logger.warning(f"{code}: eastmoney 源失败（连续 {_eastmoney_failures} 次），切换新浪源")
        return fetch_daily_bar_from_sina(code=code, from_date=from_date, to_date=to_date, adjust=adjust)


def fetch_daily_bar_from_sina(
    code: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    adjust: str = "qfq"
) -> Optional[pd.DataFrame]:
    """
    Fetch daily stock bars from sina（东财的兜底源）。
    新浪 qfq 同样以最新交易日为基准；历史深处的复权规则与东财有细微差异（累计 <~15%），
    全量初始化场景无拼接问题，增量场景建议等东财恢复后重跑全量对齐口径。
    """
    if from_date is None:
        from_date = EARLIEST_DATE

    # default to today if marked close hour has passed
    if to_date is None:
        to_date = latest_trade_day().strftime("%Y%m%d")

    try:
        exch, _ = get_exchange_by_code(code)
        df = ak.stock_zh_a_daily(
            symbol=exch.lower() + code,
            start_date=from_date,
            end_date=to_date,
            adjust=adjust
        )

        if df is None or df.empty:
            logger.warning(f"No daily bar data returned from sina for code={code}")
            return None

        # 新浪口径：amount 为元、volume 为股，与东财一致，无需换算
        df = df.rename(columns={'turnover': 'turnover_rate'})
        df['turnover_rate'] = pd.to_numeric(df['turnover_rate'], errors='coerce') * 100  # 小数 → %（round 在下方统一做）
        df['change_pct'] = (df['close'].pct_change() * 100).round(2)
        df['price_change'] = (df['close'].diff()).round(2)
        df['amplitude'] = ((df['high'] - df['low']) / df['close'].shift(1) * 100).round(2)
        df['code'] = code

        # 首行无前一日数据，补 0（东财该字段有值，但 0 不影响指标）
        df[['change_pct', 'price_change', 'amplitude', 'turnover_rate']] = \
            df[['change_pct', 'price_change', 'amplitude', 'turnover_rate']].fillna(0)

        # Drop invalid dates
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date']).copy()

        # Convert data types
        for col in ['open', 'close', 'high', 'low', 'amount', 'amplitude', 'change_pct', 'price_change', 'turnover_rate']:
            df[col] = pd.to_numeric(df[col], errors='coerce').round(2)
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype('int64')

        df = (
            df
            .drop_duplicates(subset=['code', 'date'], keep='last')
            .sort_values('date')
            .reset_index(drop=True)
        )

        final_columns = [
            'code', 'date', 'open', 'close', 'high', 'low',
            'volume', 'amount', 'amplitude', 'change_pct',
            'price_change', 'turnover_rate'
        ]
        available_columns = [col for col in final_columns if col in df.columns]
        df = df[available_columns]

        return df
    except Exception as e:
        logger.error(f"Error fetching data from sina for {code}: {e}", exc_info=True)
        return None


def fetch_daily_bar_from_tushare(
    code: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    adjust: str = "qfq",
    last_adjusted_close: Optional[float] = None,
) -> Optional[pd.DataFrame]:
    """
    Fetch daily stock bars from tushare.
    前复权不调 adj_factor 接口（官方限流 1 次/分钟，全市场不可行）。
    要求 from_date 为库中最新交易日：窗口最旧一根即锚点日，
    scale = last_adjusted_close / 锚点日原始收盘，窗口内各根按此整体缩放——
    锚点日恒等于库中 qfq 值，锚点日之后保持真实涨跌幅（含除权跳空），
    与库中历史（以同一基准日计算）无缝拼接。
    窗口跨大额除权时由调用方检测后改走 akshare。
    last_adjusted_close 为 None（首次全量）时返回原始价，调用方应改用 akshare qfq。
    """
    if from_date is None:
        from_date = EARLIEST_DATE

    # default to today if marked close hour has passed
    if to_date is None:
        to_date = latest_trade_day().strftime("%Y%m%d")

    dot_ex_code = to_dot_ex_code(code)

    max_retries = 3
    for attempt in range(max_retries):
        token = tushare_token_rate_limiter()
        try:
            pro = ts.pro_api(token=token)
            df = pro.daily(
                ts_code=dot_ex_code,
                start_date=from_date,
                end_date=to_date
            )

            if df.empty:
                logger.warning(f"No daily bar data returned from tushare for code={code}")
                return None

            df = df.sort_values('trade_date').reset_index(drop=True)

            if adjust == "qfq" and last_adjusted_close is not None:
                raw_anchor_close = float(df['close'].iloc[0])
                if raw_anchor_close > 0:
                    scale = last_adjusted_close / raw_anchor_close
                    for col in ['open', 'high', 'low', 'close', 'change']:
                        df[col] = df[col] * scale

            # tushare daily 无振幅字段，按 (high-low)/pre_close 补算（与 akshare 口径一致）
            df['amplitude'] = ((df['high'] - df['low']) / df['pre_close'] * 100).round(2)

            column_mapping = {
                'trade_date': 'date',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'vol': 'volume',
                'amount': 'amount',
                'pct_chg': 'change_pct',
                'change': 'price_change'
            }

            df = df.rename(columns=column_mapping)

            # required columns
            required_columns = ['date', 'high', 'low', 'close', 'open', 'volume']
            missing_cols = [col for col in required_columns if col not in df.columns]
            if missing_cols:
                logger.error(f"Missing required columns after mapping: {missing_cols} for {code}")
                return None

            df['code'] = code

            final_columns = [
                'code', 'date', 'open', 'close', 'high', 'low',
                'volume', 'amount', 'amplitude', 'change_pct',
                'price_change'
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
            for col in ['open', 'close', 'high', 'low', 'amplitude', 'change_pct', 'price_change']:
                df[col] = pd.to_numeric(df[col], errors='coerce').round(2)
            # tushare 成交额单位是千元，转成元以与 akshare 口径一致
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce').round(2) * 1000
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype('int64') * 100

            df = (
                df
                .drop_duplicates(subset=['code', 'date'], keep='last')
                .sort_values('date')
                .reset_index(drop=True)
            )

            start_str = df['date'].min().strftime("%Y-%m-%d")
            end_str = df['date'].max().strftime("%Y-%m-%d")
            # logger.info(f"Fetched {len(df)} daily bars for {code} [{start_str} ~ {end_str}]")

            return df

        except Exception as e:
            msg = str(e)
            if '频率超限' in msg or '每分钟' in msg or '每小时' in msg:
                wait = 15 * (attempt + 1)
                logger.warning(f"Tushare rate limited for {code}, retry {attempt+1}/{max_retries} after {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"Error fetching data for {code}: {e}", exc_info=True)
                return None

    logger.error(f"Failed to fetch {code} after {max_retries} retries (rate limited)")
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
            # logger.info(f"💾 Upserted {len(write_df)} records into {DAILY_BAR_TABLE}")
        except Exception as e:
            logger.error(f"💔 Failed to upsert bars: {e}", exc_info=True)

def update_daily_bars_for_code(
    code: str,
    source: str = "akshare"
):
    """
    Update daily bars for a specific stock code by fetching new data from the source.
    Args:
        code: stock code, e.g. 300001
        source: data source, "akshare" or "tushare"
    """
    if source not in {"akshare", "tushare"}:
        raise ValueError(f"Unsupported source: {source}. Choose from 'akshare', 'tushare'.")
    
    latest_date = get_latest_date_by_code(code)
    if latest_date is None:
        logger.warning(f"No valid date found for {code}, skipping update.")
        return
    
    to_date = latest_trade_day()
    
    if latest_date.date() >= to_date:
        # logger.info(f"No update needed for {code}, latest date {latest_date.date()} is up-to-date.")
        return

    # 增量窗口从库中最新交易日起（tushare 锚定缩放要求窗口最旧一根 = 锚点日）
    from_date = latest_date.strftime("%Y%m%d")
    df_new = None
    if source == "akshare":
        df_new = fetch_daily_bar_from_akshare(code=code, from_date=from_date)
    elif source == "tushare":
        last_bars = query_latest_bars(code, n=1)
        last_adjusted_close = float(last_bars['close'].iloc[-1]) if not last_bars.empty else None
        df_new = fetch_daily_bar_from_tushare(
            code=code, from_date=from_date,
            last_adjusted_close=last_adjusted_close)
    if df_new is not None:
        save_daily_bars_to_database(df_new)

if __name__ == "__main__":
    # Example usage: fetch and save daily bars for a specific stock code
    test_code = "002415"
    update_daily_bars_for_code(code=test_code, source="akshare")
    