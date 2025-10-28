from datetime import datetime
from typing import Optional
import pandas as pd

def ms_timestamp_to_date(timestamp):
    """安全将毫秒时间戳转为 YYYY-MM-DD，失败返回 None"""
    try:
        if timestamp is None:
            return None
        ts = float(timestamp)
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except Exception:
        return None

def format_date_input_to_yyyy_mm_dd(date_str: str) -> str:
    """
    Format input date string to 'YYYY-MM-DD'.
    """
    dt = pd.to_datetime(date_str, errors='raise')
    return dt.strftime("%Y-%m-%d")
