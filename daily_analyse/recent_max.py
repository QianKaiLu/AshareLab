import akshare as ak
import sqlite3
import pandas as pd
from pathlib import Path
from tools.log import get_fetch_logger
from tools.stock_tools import get_exchange_by_code, to_dot_ex_code
from tools.times import ms_timestamp_to_date
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any
from datetime import datetime, timedelta
from datas.create_database import DB_PATH, DAILY_BAR_TABLE, EARLIEST_DATE, get_db_connection
from datas.query_stock import query_daily_bars, query_latest_bars, get_latest_date_with_data
from tools.export import export_bars_to_csv
import time
from contextlib import closing
from ai.ai_kbar_analyses import analyze_kbar_data_openai
from tools.markdown_lab import save_md_to_file_name, render_markdown_to_image_file_name
from datas.query_stock import get_stock_info_by_code
import tushare as ts
from ratelimit import limits, sleep_and_retry

def is_20_high(df: pd.DataFrame) -> bool:
    if df.empty or len(df) < 20:
        return False
    recent_close = df.iloc[-1]['close']
    high_20 = df['high'].rolling(window=20).max().iloc[-1]
    return recent_close >= high_20