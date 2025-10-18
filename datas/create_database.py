import akshare as ak
import sqlite3
import pandas as pd
from datetime import datetime
import time
import json

def get_all_a_stocks():
    """
    获取所有 A 股股票代码（剔除 ST、*ST、退市等）
    返回格式：['SH600000', 'SZ000001', ...]
    """
    stock_info_df = ak.stock_info_a_code_name()
    # 过滤掉 ST/*ST（可选）
    stock_info_df = stock_info_df[~stock_info_df['name'].str.contains(r'\*?ST')]
    # 构造 symbol 格式：上海是 SH + 6位，深圳是 SZ + 6位
    stock_info_df['symbol'] = stock_info_df['code'].apply(
        lambda x: f"SH{x}" if x.startswith('6') else f"SZ{x}"
    )
    return stock_info_df[['symbol', 'name']].to_dict('records')