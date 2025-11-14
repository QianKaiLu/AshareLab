import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datas.query_stock import query_latest_bars
from pathlib import Path

def draw_kline():
    code = '002959'
    df = query_latest_bars(code=code, n=60)

    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()

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
            name='K线',
            increasing=dict(line=dict(color='#ef5350', width=1)),
            decreasing=dict(line=dict(color='#26a69a', width=1))
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(x=df['date'], y=df['MA5'], mode='lines', name='MA5',
                   line=dict(color='#42a5f5', width=1.5)),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=df['date'], y=df['MA20'], mode='lines', name='MA20',
                   line=dict(color='#ff7043', width=1.5, dash='dot')),
        row=1, col=1
    )

    colors = ['#ef5350' if c > o else '#26a69a' for o, c in zip(df['open'], df['close'])]
    fig.add_trace(
        go.Bar(
            x=df['date'],
            y=df['volume'],
            name='成交量',
            marker=dict(color=colors, opacity=0.6),
            showlegend=False
        ),
        row=2, col=1
    )

    fig.update_layout(
        title=dict(
            text=f'{code} 日K线图（含MA5/MA20与成交量）',
            x=0.5,
            xanchor='center'
        ),
        xaxis_rangeslider_visible=False,
        template='seaborn',
        height=700
    )

    fig.show()

if __name__ == "__main__":
    draw_kline()