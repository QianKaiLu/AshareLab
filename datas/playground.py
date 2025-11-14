import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import akshare as ak
from datas.query_stock import query_latest_bars
from pathlib import Path

# 沪深300成分股
df_300 = ak.index_stock_cons(symbol="000300")
print("沪深300成分股：")
print(df_300.count())
# 中证500成分股
df_500 = ak.index_stock_cons(symbol="000905")
print("中证500成分股：")
print(df_500.count())