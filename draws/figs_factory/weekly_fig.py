"""周线 K 线 + 周线 KDJ 图。

用途是核对 `indicators/kdj_weekly.py` 的取值：图上画的周 K 与 KDJ 直接由日线重采样
成周线后计算，和行情软件的周线图口径一致，可以逐周对着软件读数比。

面板：周 K（含 BBI）/ 周成交量 / 周线 KDJ（标注 15、85 超卖超买线）。
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from datas.query_stock import get_stock_info_by_code, query_bars_by_days
from draws.kline_theme import ThemeRegistry
from indicators.bbi import bbi
from indicators.kdj import kdj
from indicators.kdj_weekly import resample_weekly
from tools.colors import hex_to_rgba
from typing import Optional


def weekly_fig(
    code: str,
    weeks: int = 60,
    width: int = 900,
    height: int = 800,
    to_date: Optional[str] = None,
    theme_name: str = "vintage_ticker",
) -> tuple[go.Figure, pd.DataFrame]:
    """返回 (图, 周线 DataFrame)。DataFrame 一并返回，便于打表核对数值。"""
    theme = ThemeRegistry.get(name=theme_name)

    stock_info = get_stock_info_by_code(code)
    if stock_info.empty or code not in stock_info.index:
        raise ValueError(f"No stock info found for code: {code}")

    # 周线要 60 根，日线得取够：每周 5 个交易日，再留出 KDJ 的 9 周窗口
    days = max(500, (weeks + 15) * 5)
    daily = query_bars_by_days(code=code, days=days, to_date=to_date)
    if daily is None or daily.empty:
        raise ValueError(f"No data found for code: {code}")

    wk = resample_weekly(daily)
    k = kdj(wk["high"], wk["low"], wk["close"])
    wk = wk.join(k)
    wk["bbi"] = bbi(wk["close"])

    wk = wk.tail(weeks).reset_index(drop=True)

    vertical_spacing = 0.05
    row_heights = [0.55, 0.15, 0.3]
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=vertical_spacing, row_heights=row_heights,
    )

    dates = wk["date"].dt.strftime("%y-%m-%d").tolist()
    x = list(range(len(wk)))
    last = len(wk) - 1
    smoothing = 1.0

    # --- 周 K ---
    fig.add_trace(
        go.Candlestick(
            x=x, open=wk["open"], high=wk["high"], low=wk["low"], close=wk["close"],
            increasing=dict(fillcolor=theme.up_color, line=dict(color=theme.up_color, width=2)),
            decreasing=dict(fillcolor=theme.down_color, line=dict(color=theme.down_color, width=2)),
            showlegend=False,
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x, y=wk["bbi"], mode="lines", name="BBI(周)",
            line=dict(color=theme.bbi_color, width=1.5, dash="dot", shape="spline", smoothing=smoothing),
        ),
        row=1, col=1,
    )

    # --- 周成交量 ---
    colors = [theme.up_color if c > o else theme.down_color for o, c in zip(wk["open"], wk["close"])]
    fig.add_trace(
        go.Bar(x=x, y=wk["volume"], name="volume",
               marker=dict(color=colors, opacity=1.0, line=dict(width=0)), showlegend=False),
        row=2, col=1,
    )

    # --- 周线 KDJ ---
    for col, cname, color in (
        ("kdj_k", "K", theme.line_color_0),
        ("kdj_d", "D", theme.line_color_1),
        ("kdj_j", "J", theme.line_color_2),
    ):
        fig.add_trace(
            go.Scatter(
                x=x, y=wk[col], mode="lines", name=cname,
                line=dict(color=color, width=1.6 if col == "kdj_j" else 1,
                          dash="solid" if col == "kdj_j" else "dot",
                          shape="spline", smoothing=smoothing),
                showlegend=False,
            ),
            row=3, col=1,
        )
        fig.add_annotation(
            x=x[last], y=wk[col].iloc[-1], text=f"{cname} {wk[col].iloc[-1]:.1f}",
            showarrow=False, xanchor="left", xshift=5,
            font=dict(color=color, size=10), row=3, col=1,
        )

    # 用户的口径：J ≤ 15 超卖，≥ 85 超买
    for lvl, txt in ((15, "15 超卖"), (85, "85 超买")):
        fig.add_hline(
            y=lvl, line=dict(color=hex_to_rgba(theme.text_color, 0.35), width=1, dash="dash"),
            annotation_text=txt, annotation_position="right",
            annotation_font=dict(size=8, color=hex_to_rgba(theme.text_color, 0.6)),
            row=3, col=1,
        )
    fig.add_hline(y=0, line=dict(color=hex_to_rgba(theme.text_color, 0.2), width=1), row=3, col=1)

    nticks = min(len(dates), 12)
    step = max(1, len(dates) // nticks)
    tick_indices = list(range(0, len(dates), step))
    tick_labels = [dates[i] for i in tick_indices]
    fig.update_xaxes(
        tickvals=tick_indices, ticktext=tick_labels, tickangle=-45,
        tickfont=dict(size=9, color=theme.text_color, family=theme.text_font),
        ticklen=5, tickwidth=1, row=3, col=1,
    )

    name = stock_info.at[code, "name"]
    span = f'{dates[0]} ~ {dates[-1]}  共 {len(wk)} 周'
    tickfont = dict(size=9, color=theme.text_color, family="Courier New, monospace")
    fig.update_layout(
        title=dict(
            text=f"{name} ({code})  周线<br><sub>{span}</sub>",
            x=0.5, y=0.965, xanchor="center",
            font=dict(size=15, color=theme.text_color, family=theme.text_font),
        ),
        plot_bgcolor=theme.card_background,
        paper_bgcolor=theme.card_background,
        font=dict(color=theme.text_color, size=10),
        showlegend=True,
        legend=dict(
            font=dict(size=10, color=theme.text_color), orientation="h",
            yanchor="bottom", y=0.965, xanchor="right", x=1.0,
            bgcolor=hex_to_rgba(theme.card_background, 0.6),
            itemwidth=30, itemsizing="constant",
        ),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, rangeslider_visible=False),
        yaxis=dict(
            title="Price", title_standoff=6, title_font=dict(size=10, color=theme.text_color),
            tickfont=tickfont, showgrid=True, nticks=10, gridcolor=theme.grid_color,
            griddash="dot", gridwidth=1, fixedrange=True, tickformat=".2f",
        ),
        yaxis2=dict(
            title="Vol", title_standoff=6, title_font=dict(size=10, color=theme.text_color),
            tickfont=tickfont, showgrid=True, nticks=3, gridcolor=theme.grid_color,
            griddash="dot", fixedrange=True, tickformat=".2s",
        ),
        yaxis3=dict(
            title="KDJ(周)", title_standoff=6, title_font=dict(size=10, color=theme.text_color),
            tickfont=tickfont, showgrid=True, nticks=6, gridcolor=theme.grid_color,
            griddash="dot", zeroline=False, fixedrange=True,
        ),
        xaxis3=dict(showgrid=False, zeroline=False, showticklabels=True, rangeslider_visible=False),
        margin=dict(l=55, r=60, t=70, b=45),
        height=height, width=width,
    )
    return fig, wk


if __name__ == "__main__":
    fig, wk = weekly_fig(code="002594", weeks=60, width=900, height=800, theme_name="vintage_ticker")
    fig.show()
