import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import akshare as ak
from datas.query_stock import query_latest_bars
from pathlib import Path
import yfinance as yf
import requests
from newsapi import NewsApiClient

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

# # 沪深300成分股
df_300 = ak.index_stock_cons(symbol="000300")
print("沪深300成分股：")
print(df_300)
# # 中证500成分股
# df_500 = ak.index_stock_cons(symbol="000905")
# print("中证500成分股：")
# print(df_500.count())