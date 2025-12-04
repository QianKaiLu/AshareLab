import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datas.query_stock import query_latest_bars, get_stock_info_by_code
from pathlib import Path
from indicators.kdj import add_kdj_to_dataframe
from indicators.macd import add_macd_to_dataframe
from indicators.bbi import add_bbi_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe
from draws.kline_theme import ThemeRegistry, KlineTheme
from tools.colors import hex_to_rgba
import akshare as ak
import markdown

code = '002959'
df = ak.stock_news_em(symbol=code)
print(df)
