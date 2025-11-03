import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datas.query_stock import query_daily_bars
from pathlib import Path

code = '002959'
df = query_daily_bars(code=code, from_date='20250601')

column_mapping = {'date': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}
df = df.rename(columns=column_mapping)

df['MA5'] = df['Close'].rolling(window=5).mean()
df['MA60'] = df['Close'].rolling(window=60).mean()

fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.02,
    row_heights=[0.7, 0.3],
    specs=[[{"secondary_y": False}], [{"secondary_y": False}]]
)

fig.add_trace(
    go.Candlestick(
        x=df['Date'],
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='K线',
        increasing=dict(line=dict(color='#ef5350', width=1)),
        decreasing=dict(line=dict(color='#26a69a', width=1))
    ),
    row=1, col=1
)

fig.add_trace(
    go.Scatter(x=df['Date'], y=df['MA5'], mode='lines', name='MA5',
               line=dict(color='#42a5f5', width=1.5)),
    row=1, col=1
)
fig.add_trace(
    go.Scatter(x=df['Date'], y=df['MA60'], mode='lines', name='MA60',
               line=dict(color='#ff7043', width=1.5, dash='dot')),
    row=1, col=1
)

colors = ['#ef5350' if c > o else '#26a69a' for o, c in zip(df['Open'], df['Close'])]
fig.add_trace(
    go.Bar(
        x=df['Date'],
        y=df['Volume'],
        name='成交量',
        marker=dict(color=colors, opacity=0.6),
        showlegend=False
    ),
    row=2, col=1
)

fig.update_layout(
    title=dict(
        text=f'{code} 日K线图（含MA5/MA60与成交量）',
        x=0.5,
        xanchor='center',
        font=dict(size=20, color='white')
    ),
    plot_bgcolor='#1e1e1e',
    paper_bgcolor='#1e1e1e',
    font=dict(color='white', size=12),
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        showticklabels=True,
        rangeslider_visible=False
    ),
    yaxis=dict(
        title='价格',
        showgrid=True,
        gridcolor='#333',
        zeroline=False
    ),
    yaxis2=dict(
        title='成交量',
        showgrid=True,
        gridcolor='#333',
        zeroline=False
    ),
    legend=dict(
        orientation='h',
        yanchor='bottom',
        y=1.02,
        xanchor='right',
        x=1,
        bgcolor='rgba(0,0,0,0.3)'
    ),
    margin=dict(l=50, r=50, t=80, b=50),
    height=700,
    width=1100
)

output_dir = Path(__file__).parent.parent / "output"
output_dir.mkdir(exist_ok=True)
file_path = output_dir / "kline_chart_professional.png"
fig.write_image(file_path, width=1100, height=700, scale=2)

print(f"✅ charts saved to：{file_path}")
