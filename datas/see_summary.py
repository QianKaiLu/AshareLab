import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datas.query_stock import query_latest_bars
from pathlib import Path
from indicators.kdj import add_kdj_to_dataframe
from indicators.macd import add_macd_to_dataframe
from indicators.bbi import add_bbi_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe

code = '002959'
df = query_latest_bars(code=code, n=60)

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
        increasing=dict(line=dict(color="#ef4846", width=1)),
        decreasing=dict(line=dict(color="#28a85d", width=1))
    ),
    row=1, col=1
)

fig.add_trace(
    go.Scatter(x=df['date'], y=df['bbi'], mode='lines', name='bbi',
               line=dict(color="#e8ac2b", width=1.5, dash='dot')),
    row=1, col=1
)

colors = ['#ef4846' if c > o else '#28a85d' for o, c in zip(df['open'], df['close'])]
fig.add_trace(
    go.Bar(
        x=df['date'],
        y=df['volume'],
        name='成交量',
        marker=dict(color=colors, opacity=0.8),
        showlegend=False
    ),
    row=2, col=1
)

fig.update_layout(
    title=dict(
        text=f'{code} 日K线图',
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
        title='Price',
        showgrid=True,
        gridcolor='#333',
        zeroline=False
    ),
    yaxis2=dict(
        title='Volume',
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

fig.show()

# output_dir = Path(__file__).parent.parent / "output"
# output_dir.mkdir(exist_ok=True)
# file_path = output_dir / "kline_chart_professional.png"
# fig.write_image(file_path, width=1100, height=700, scale=2)

# print(f"✅ charts saved to：{file_path}")
