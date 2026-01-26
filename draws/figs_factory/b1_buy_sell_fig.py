import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datas.query_stock import query_latest_bars, get_stock_info_by_code, query_bars_by_days
from pathlib import Path
from indicators.bbi import add_bbi_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe
from indicators.kdj import add_kdj_to_dataframe
from indicators.macd import add_macd_to_dataframe
from draws.kline_theme import ThemeRegistry, KlineTheme
from tools.colors import hex_to_rgba
from draws.figs_factory.ploty_tools import compute_row_paper_domains, add_row_background
from typing import Optional
import numpy as np
from dataclasses import dataclass, field
from enum import Enum

class TradeSide(Enum):
    BUY = "buy"
    SELL = "sell"

class DrawType(Enum):
    TagText = "tag_text"
    VerticalLine = "line"

@dataclass
class TradeSignal:
    date: str
    side: TradeSide = TradeSide.BUY
    price: Optional[float] = None
    draw_type: DrawType = DrawType.TagText
    
def b1_buy_sell_fig(code: str, n: int = 60, width: int = 600, height: int = 600, to_date: Optional[str] = None, trade_signals: Optional[list[TradeSignal]] = None, theme_name: str = "vintage_ticker") -> go.Figure:
    theme = ThemeRegistry.get(name=theme_name)
    
    stock_info = get_stock_info_by_code(code)
    df = query_bars_by_days(code=code, days=500, to_date=to_date)
    
    if df.empty:
        raise ValueError(f"No data found for code: {code}")
    
    if stock_info.empty or code not in stock_info.index:
        raise ValueError(f"No stock info found for code: {code}")

    add_bbi_to_dataframe(df, inplace=True)
    add_zxdkx_to_dataframe(df, inplace=True)
    add_volume_ma_to_dataframe(df, inplace=True)
    add_kdj_to_dataframe(df, inplace=True)
    add_macd_to_dataframe(df, inplace=True)

    df = df.tail(n)

    vertical_spacing = 0.05
    row_heights = [0.6, 0.2, 0.18]
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=vertical_spacing,
        row_heights=row_heights
    )
    
    # dates = df['date'].dt.strftime('%m-%d').tolist()
    dates = df['date'].dt.strftime('%m-%d').tolist()
    x_index = list(range(len(df)))

    smoothing = 1.0
    # Candlestick
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
            y=df['z_white'], 
            mode='lines', 
            name='白线',
            line=dict(color=theme.quick_line_color, width=1.2, dash='dot', shape='spline', smoothing=smoothing),
            showlegend=True
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=x_index, 
            y=df['z_yellow'], 
            mode='lines', 
            name='黄线',
            line=dict(color=theme.slow_line_color, width=1.2, dash='solid', shape='spline', smoothing=smoothing),
            showlegend=True
        ),
        row=1, col=1
    )

    if trade_signals:
        # 构建日期到索引的映射（df 的 date 是 datetime）
        date_to_index = {
            date.strftime('%Y-%m-%d'): i 
            for i, date in enumerate(df['date'])
        }

        for signal in trade_signals:
            if signal.date in date_to_index:
                x = date_to_index[signal.date]
                if signal.price is not None:
                    y = signal.price
                else:
                    y = df['high'].iloc[x] if signal.side == TradeSide.BUY else df['low'].iloc[x]
                text = "B" if signal.side == TradeSide.BUY else "S"
                color = "green" if signal.side == TradeSide.BUY else "red"
                
                fig.add_annotation(
                    x=x, y=y,
                    text=text,
                    showarrow=False,
                    font=dict(color="white", size=10, weight="bold"),
                    bgcolor=color,
                    borderpad=2,  # 内边距
                    ax=0, ay=0,
                    row=1, col=1
                )

    # Vol
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
            line=dict(color=theme.line_color_0, width=1, dash='solid', shape='spline', smoothing=smoothing),
            showlegend=False
        ),
        row=2, col=1
    )
    fig.add_annotation(
        x=x_index[len(df)-1], 
        y=df['volume_ma_5'].iloc[-1],
        text="MA5",
        showarrow=False,
        xanchor='left',
        font=dict(color=theme.line_color_0, size=10),
        xshift=5,
        row=2, col=1
    )
        
    # kdj
    last_idx = len(df) - 1
    fig.add_trace(
        go.Scatter(
            x=x_index, 
            y=df['kdj_k'], 
            mode='lines', 
            name='K', 
            line=dict(color=theme.line_color_0, width=1, dash='dot', shape='spline', smoothing=smoothing), 
            showlegend=False),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=x_index, 
            y=df['kdj_d'], 
            mode='lines', 
            name='D', 
            line=dict(color=theme.line_color_1, width=1, dash='dot',shape='spline', smoothing=smoothing), 
            showlegend=False
            ),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=x_index, 
            y=df['kdj_j'],
            mode='lines', 
            name='J', 
            line=dict(color=theme.line_color_2, width=1, shape='spline', smoothing=smoothing), 
            showlegend=False
            ),
        row=3, col=1
    )
    fig.add_annotation(
        x=x_index[last_idx], 
        y=df['kdj_k'].iloc[-1],
        text="K",
        showarrow=False,
        xanchor='left',
        font=dict(color=theme.line_color_0, size=10),
        xshift=5,
        row=3, col=1
    )
    fig.add_annotation(
        x=x_index[last_idx], 
        y=df['kdj_d'].iloc[-1],
        text="D",
        showarrow=False,
        xanchor='left',
        font=dict(color=theme.line_color_1, size=10),
        xshift=5,
        row=3, col=1
    )
    fig.add_annotation(
        x=x_index[last_idx], 
        y=df['kdj_j'].iloc[-1],
        text="J",
        showarrow=False,
        xanchor='left',
        font=dict(color=theme.line_color_2, size=10),
        xshift=5,
        row=3, col=1
    )

    tick_indices = np.linspace(0, len(dates) - 1, num=min(10, len(dates)), endpoint=True, dtype=int)
    tick_labels = [dates[i] for i in tick_indices]

    fig.update_xaxes(
        tickvals=tick_indices,
        ticktext=tick_labels,
        tickangle= -45,
        tickfont=dict(size=9, color=theme.text_color, family=theme.text_font),
        ticklen=5,
        tickwidth=1,
        row=3, col=1
    )
    
    fig.update_layout(
        title=dict(
            text=f'{stock_info.at[code, "name"]} ({code})',
            x=0.5,
            y=0.955,
            xanchor='center',
            font=dict(size=16, color=theme.text_color, family=theme.text_font)
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
            title_standoff=6,
            title_font = dict(size=10, color=theme.text_color),
            tickfont = dict(size=9, color=theme.text_color, family="Courier New, monospace"),
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
            tickfont = dict(size=9, color=theme.text_color, family="Courier New, monospace"),
            showticklabels=True,
            showgrid=True,
            nticks=4,   
            griddash='dot',
            gridwidth=1,
            gridcolor=theme.grid_color,
            fixedrange=True,
            zeroline=True,
            zerolinecolor=theme.grid_color,
            zerolinewidth=0.5,
            tickformat=".2s"
        ),
        yaxis3=dict(
            title='KDJ', 
            title_standoff=6, 
            title_font = dict(size=10, color=theme.text_color),
            tickfont = dict(size=9, color=theme.text_color, family="Courier New, monospace"),
            showgrid=True, 
            gridcolor=theme.grid_color, 
            griddash='dot',
            zeroline=False,
            fixedrange=True
            ),
        xaxis3=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=True,
            rangeslider_visible=False
        ),
        margin=dict(l=50, r=5, t=60, b=40),
        height=height,
        width=width
    )
    
    return fig

if __name__ == "__main__":
    trade_signals = [
        TradeSignal(date="2025-11-12", side=TradeSide.BUY, draw_type=DrawType.VerticalLine),
        TradeSignal(date="2026-01-20", side=TradeSide.SELL, draw_type=DrawType.TagText)
    ]
    fig = b1_buy_sell_fig(code='002970', n=60, width=600, height=800, trade_signals=trade_signals, theme_name="desert_dusk")
    fig.show()