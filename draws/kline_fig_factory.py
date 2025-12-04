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

def standard_fig(code: str, n: int = 60, width: int = 600, height: int = 600, theme_name: str = "vintage_ticker") -> go.Figure:
    theme = ThemeRegistry.get(name=theme_name)
    
    stock_info = get_stock_info_by_code(code)
    df = query_latest_bars(code=code, n=300)
    
    if df.empty:
        raise ValueError(f"No data found for code: {code}")
    
    if stock_info.empty or code not in stock_info.index:
        raise ValueError(f"No stock info found for code: {code}")

    add_bbi_to_dataframe(df, inplace=True)
    add_zxdkx_to_dataframe(df, inplace=True)
    add_volume_ma_to_dataframe(df, inplace=True)

    df = df.tail(n)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        row_heights=[0.7, 0.2]
    )
    
    dates = df['date'].dt.strftime('%m-%d').tolist()  # 或 '%Y-%m-%d' 看你喜好

    # 2. 用整数索引（0, 1, 2, ..., N-1）作为 x 坐标
    x_index = list(range(len(df)))

    fig.add_trace(
        go.Candlestick(
            x=x_index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            increasing=dict(
                fillcolor=theme.up_color,
                line=dict(color=theme.up_color, width=2)),
            decreasing=dict(
                fillcolor=theme.down_color,
                line=dict(color=theme.down_color, width=2)),
            showlegend=False
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=x_index, 
            y=df['bbi'], 
            mode='lines', 
            name='bbi',
            line=dict(color=theme.bbi_color, width=1.5, dash='dot'),
            showlegend=True
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=x_index, 
            y=df['z_white'], 
            mode='lines', 
            name='fast line',
            line=dict(color=theme.quick_line_color, width=1.2, dash='solid'),
            showlegend=True
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=x_index, 
            y=df['z_yellow'], 
            mode='lines', 
            name='slow line',
            line=dict(color=theme.slow_line_color, width=1.2, dash='solid'),
            showlegend=True
        ),
        row=1, col=1
    )

    colors = [theme.up_color if c > o else theme.down_color for o, c in zip(df['open'], df['close'])]
    fig.add_trace(
        go.Bar(
            x=x_index,
            y=df['volume'],
            name='volume',
            marker=dict(
                color=colors, 
                opacity=1.0,
                line=dict(width=0)
            ),
            showlegend=False,
        ),
        row=2, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=x_index, 
            y=df['volume_ma_5'], 
            mode='lines', 
            name='VOL MA5',
            line=dict(color=theme.line_color_0, width=1, dash='solid'),
            showlegend=False
        ),
        row=2, col=1
    )

    nticks = min(len(dates), 7)
    step = max(1, len(dates) // nticks)
    tick_indices = list(range(0, len(dates), step))
    tick_labels = [dates[i] for i in tick_indices]

    fig.update_xaxes(
        tickvals=tick_indices,
        ticktext=tick_labels,
        tickangle= -45,
        tickfont=dict(size=9, color=theme.text_color, family='Arial'),
        ticklen=5,
        tickwidth=1,
        row=1, col=1
    )

    fig.update_xaxes(
        tickvals=tick_indices,
        ticktext=tick_labels,
        tickangle= -45,
        tickfont=dict(size=9, color=theme.text_color, family='Arial'),
        ticklen=5,
        tickwidth=1,
        row=2, col=1
    )
        
    fig.update_layout(
        title=dict(
            text=f'{stock_info.at[code, "name"]} ({code})',
            x=0.5,
            y=0.955,
            xanchor='center',
            font=dict(size=16, color=theme.text_color, family='sans-serif')
        ),
        plot_bgcolor=theme.card_background,
        paper_bgcolor=theme.card_background,
        font=dict(color=theme.text_color, size=10),
        showlegend=True,
        legend=dict(
            font=dict(size=10, color=theme.text_color),
            orientation='h',
            yanchor='bottom',
            y=0.96,
            xanchor='right',
            x=1.02,
            bgcolor=hex_to_rgba(theme.card_background, 0.6),
            # bordercolor=hex_to_rgba(theme.text_color, 0.3),
            # borderwidth=0.5,
            itemwidth=30,
            itemsizing='constant',
            traceorder='normal',
        ),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            rangeslider_visible=False
        ),
        yaxis=dict(
            title='Price',
            title_standoff=10,
            title_font = dict(size=10, color=theme.text_color),
            tickfont = dict(size=9, color=theme.text_color),
            showgrid=True,
            nticks=10,
            gridcolor=theme.grid_color,
            griddash='dot',
            gridwidth=1,
            fixedrange=True,
            zeroline=True,
            tickformat=".2f"
        ),
        yaxis2=dict(
            title='Vol',
            title_standoff=6,
            title_font = dict(size=10, color=theme.text_color),
            tickfont = dict(size=9, color=theme.text_color),
            showticklabels=True,
            showgrid=True,
            nticks=4,   
            griddash='dot',
            gridwidth=1,
            gridcolor=theme.grid_color,
            fixedrange=True,
            zeroline=True,
            tickformat=".2s"
        ),
        margin=dict(l=40, r=20, t=60, b=40),
        height=height,
        width=width
    )
    
    return fig