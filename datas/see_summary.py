import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datas.query_stock import query_latest_bars
from pathlib import Path
from indicators.kdj import add_kdj_to_dataframe
from indicators.macd import add_macd_to_dataframe
from indicators.bbi import add_bbi_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe
from draws.kline_theme import ThemeRegistry, KlineTheme

theme = ThemeRegistry.get(name="vintage_ticker")

code = '002959'
df = query_latest_bars(code=code, n=30)

add_bbi_to_dataframe(df, inplace=True)
add_zxdkx_to_dataframe(df, inplace=True)

print(df.tail(10))

fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.02,
    row_heights=[0.7, 0.3],
    specs=[[{"secondary_y": False}], [{"secondary_y": False}]]
)

fig.add_trace(
    go.Candlestick(
        x=df['date'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='日 K 线',
        increasing=dict(line=dict(color=theme.up_color, width=1)),
        decreasing=dict(line=dict(color=theme.down_color, width=1))
    ),
    row=1, col=1
)

fig.add_trace(
    go.Scatter(x=df['date'], y=df['bbi'], mode='lines', name='bbi',
               line=dict(color=theme.bbi_color, width=1.5, dash='dot')),
    row=1, col=1
)

colors = [theme.up_color if c > o else theme.down_color for o, c in zip(df['open'], df['close'])]
fig.add_trace(
    go.Bar(
        x=df['date'],
        y=df['volume'],
        name='成交量',
        marker=dict(color=colors, opacity=theme.volume_opacity),
        showlegend=False
    ),
    row=2, col=1
)
    
fig.update_layout(
    title=dict(
        text=f'{code} 日K线图',
        x=0.5,
        xanchor='center',
        font=dict(size=20, color=theme.text_color)
    ),
    plot_bgcolor=theme.card_background,
    paper_bgcolor=theme.card_background,
    font=dict(color=theme.text_color, size=12),
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        showticklabels=True,
        rangeslider_visible=False
    ),
    yaxis=dict(
        title='Price',
        showgrid=True,
        gridcolor=theme.grid_color,
        zeroline=False
    ),
    yaxis2=dict(
        title='Volume',
        showgrid=True,
        gridcolor=theme.grid_color,
        zeroline=False
    ),
    legend=dict(
        orientation='h',
        yanchor='bottom',
        y=1.02,
        xanchor='right',
        x=1,
        bgcolor='rgba(0,0,0,0)',
        font=dict(color=theme.text_color)
    ),
    margin=dict(l=50, r=50, t=80, b=50),
    height=1000,
    width=600
)

fig.show()