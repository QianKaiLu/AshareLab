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
from draws.kline_fig_factory import standard_fig

fig = standard_fig(code='600423', n=60, width=600, height=600, theme_name="vintage_ticker_pro")
fig.show()