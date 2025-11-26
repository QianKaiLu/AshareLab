# import plotly.graph_objects as go
# from plotly.subplots import make_subplots
import pandas as pd
import akshare as ak
from datas.query_stock import query_latest_bars
from pathlib import Path
# import yfinance as yf
import requests
# from newsapi import NewsApiClient
import tushare as ts
from datas.fetch_stock_bars import fetch_daily_bar_from_akshare
from datas.stock_index_list import hs300_code_list, csi500_code_list
from indicators.kdj import add_kdj_to_dataframe
from indicators.macd import add_macd_to_dataframe
from indicators.bbi import add_bbi_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe

# pro = ts.pro_api(token='2cf551afc37b607a31ddb855966986de8b8ec67aa856914b4a893b51')
# code = '002594.SZ'
# # 获取原始日线
# df = pro.daily(ts_code=code, start_date='20250101', end_date='20251119')
# # 获取复权因子
# adj = pro.adj_factor(ts_code=code, start_date='20250101', end_date='20251119')
# # 合并
# df = df.merge(adj[['trade_date', 'adj_factor']], on='trade_date')
# df = df.sort_values('trade_date').reset_index(drop=True)
# latest_adj = df['adj_factor'].iloc[-1]
# df['close'] = df['close'] * df['adj_factor'] / latest_adj
# df['open'] = df['open'] * df['adj_factor'] / latest_adj
# df['high'] = df['high'] * df['adj_factor'] / latest_adj
# df['low'] = df['low'] * df['adj_factor'] / latest_adj

df = query_latest_bars('002050', 1000)
add_kdj_to_dataframe(df, inplace=True)
add_bbi_to_dataframe(df, inplace=True)
add_macd_to_dataframe(df, inplace=True)
add_zxdkx_to_dataframe(df, inplace=True)
print(df.tail(30)[['date', 'close', 'bbi', 'z_white', 'z_yellow']])