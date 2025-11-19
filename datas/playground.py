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

# newsapi = NewsApiClient(api_key='dc5b76fac93f4740ab3ec029c4ceeb44')
# results = newsapi.get_everything(q='小米', language='zh')
# print(results)

# # 获取顶部头条新闻
# top_headlines = newsapi.get_top_headlines(
#     q='technology',            # 关键词（可选）
#     sources='bbc-news,the-verge',
#     category='business',
#     language='en',
#     country='us'
# )
# # 打印新闻标题
# for article in top_headlines['articles']:
#     print(article['title'])
#     print(article['url'])
#     print('-' * 80)

# news = ak.stock_news_em(symbol='600418')
# print(news)

ts.set_token('d2f856055cefeb4a3a43784054478263d38d77072561d7fdba5e8f4e')
# pro = ts.pro_api('2cf551afc37b607a31ddb855966986de8b8ec67aa856914b4a893b51')
df = ts.pro_bar(ts_code='002415.SZ', start_date='20251001', end_date='20251119', adj='qfq')
print(df.dtypes)

# df = fetch_daily_bar_from_akshare(code='002594', from_date='20251001', to_date='20251119', adjust='qfq')
# print(df[["code", "date", "open", "close", "high", "low", "volume"]])