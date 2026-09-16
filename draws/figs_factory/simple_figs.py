"""报表配图工厂：吃 DataFrame 的折线图与 K 线图。

与 `ztalk_fig_v2` / `standard_fig` 的**根本区别**：那两个只接受 `code`，自己拿
`query_bars_by_days` 去查个股表。市场日报要画的东西不在那张表里——活跃市值在
`manual_data/0AMV.csv`、上证指数在 `index_bars_daily`——所以另起一个**吃 DataFrame**
的版本，既有的 K 线链路一行不动。

X 轴一律用 `range(len(df))` 配 `tickvals/ticktext`，不用日期当 x：这样跳过非交易日
不会留空档（项目里 `ztalk_fig_v2.py:46` 就是这个惯例）。

用法:
    from draws.figs_factory.simple_figs import line_fig, candle_fig, save_fig
    save_fig(line_fig(df, [("zt", "涨停家数")], title="涨停家数"), path, 600, 340)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from draws.kline_theme import ThemeRegistry

# 与市场日报图版的深暖色正文对齐；色值定义见 draws/kline_theme.py 的 espresso
DEFAULT_THEME = "espresso"

MAX_TICKS = 8


def _theme(name: str):
    return ThemeRegistry.get(name=name)


def _x_axis(df: pd.DataFrame) -> tuple[list[int], dict]:
    """返回 (x_index, update_xaxes 的参数字典)。

    时间列名兼容 `date`（日线）与 `dt`（分钟线）——两者的标签格式不同：
    日线只到日，分钟线还要带上时刻（同一交易日有 8 根 30 分钟 bar，只标月-日会看不出区别）。
    """
    x = list(range(len(df)))
    tcol = "date" if "date" in df.columns else ("dt" if "dt" in df.columns else None)
    if tcol:
        ts = pd.to_datetime(df[tcol])
        fmt = "%m-%d" if tcol == "date" else "%m-%d %H:%M"
        labels = ts.dt.strftime(fmt).tolist()
        nticks = min(len(labels), MAX_TICKS)
        step = max(1, len(labels) // nticks)
        idx = list(range(0, len(labels), step))
        last = len(labels) - 1
        if idx[-1] != last:
            # 末尾强制标出最新那天；但与前一个刻度挨太近时会叠字，此时**替换**而非追加
            if last - idx[-1] < max(2, step // 2):
                idx[-1] = last
            else:
                idx.append(last)
        cfg = {"tickvals": idx, "ticktext": [labels[i] for i in idx]}
    else:
        cfg = {}
    return x, cfg


def _base_layout(fig: go.Figure, theme, title: str, height: int) -> None:
    fig.update_layout(
        title=dict(text=title, x=0.01, xanchor="left",
                   font=dict(size=14, color=theme.text_color, family=theme.text_font)),
        height=height,
        plot_bgcolor=theme.plot_background,
        paper_bgcolor=theme.card_background,
        font=dict(color=theme.text_color, size=11, family=theme.text_font),
        margin=dict(l=52, r=64, t=44, b=34),
        showlegend=True,
        legend=dict(font=dict(size=10, color=theme.text_color),
                    orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, showline=False,
                     tickfont=dict(size=9, color=theme.text_color, family=theme.text_font))
    fig.update_yaxes(showgrid=True, gridcolor=theme.grid_color, gridwidth=0.5,
                     zeroline=False, showline=False,
                     tickfont=dict(size=9, color=theme.text_color, family=theme.text_font))


def line_fig(
    df: pd.DataFrame,
    series: Sequence[tuple[str, str]],
    title: str = "",
    height: int = 320,
    theme_name: str = DEFAULT_THEME,
    y_label: str = "",
    annotate_last: bool = True,
    annotate_suffix: str = "",
    annotate_digits: int = 0,
) -> go.Figure:
    """折线图。

    Args:
        df: 含 `date` 列（可选，用于 x 轴标签）与各 series 的列
        series: [(列名, 图例名), ...]，按顺序取 line_color_0/1/2 上色
        annotate_last: 在每条线末端标注末值——报告图里读者最关心「现在多少」
        annotate_suffix / annotate_digits: 末端标注的单位与小数位。
            **百分比必须带 `%` 且保留一位小数** —— 否则 8.8 会被格式化成「9」，
            读者会当成「9 只」而不是「9%」（2026-09-16 实测踩过）
    """
    theme = _theme(theme_name)
    x, xcfg = _x_axis(df)
    fig = go.Figure()

    palette = [theme.line_color_0, theme.line_color_1, theme.line_color_2]

    for i, (col, label) in enumerate(series):
        if col not in df.columns:
            continue
        color = palette[i % len(palette)]
        y = pd.to_numeric(df[col], errors="coerce")
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", name=label,
            line=dict(color=color, width=2, shape="spline", smoothing=0.6),
            marker=dict(size=4, color=color),
        ))
        if annotate_last and y.notna().any():
            last_i = int(y.last_valid_index())
            # 多线末值常常很接近（比如都趴在 3~4%），不上下错开就会叠字；单线则贴着线端
            yshift = 0 if len(series) == 1 else (7 if i % 2 == 0 else -7)
            fig.add_annotation(
                x=x[last_i], y=float(y.loc[last_i]),
                text=f"{y.loc[last_i]:,.{annotate_digits}f}{annotate_suffix}",
                showarrow=False,
                xanchor="left", xshift=6, yshift=yshift,
                font=dict(color=color, size=10, family=theme.text_font),
            )

    _base_layout(fig, theme, title, height)
    fig.update_xaxes(**xcfg)
    if y_label:
        fig.update_yaxes(title=dict(text=y_label, font=dict(size=10, color=theme.text_color)))
    return fig


def candle_fig(
    df: pd.DataFrame,
    title: str = "",
    height: int = 400,
    theme_name: str = DEFAULT_THEME,
    ma_lines: Sequence[int] = (),
    volume: bool = False,
    display_bars: Optional[int] = None,
) -> go.Figure:
    """K 线图。`ma_lines` 给均线周期，如 (20, 60)。

    **`display_bars` 用来做指标预热**：传的 df 可以比要展示的多，均线在**完整序列**
    上算完再切最后 `display_bars` 根来画。不这样做的话，取 60 根画 MA60 就只有
    1 个有效值、线根本画不出来；取 160 根画 MACD 则开头三十多根是空的。

    调用方只需多取一段数据传进来，切分交给这里。

    up/down 用主题的 `up_color`/`down_color`——`espresso` 是**红涨绿跌**，
    与 A 股看盘习惯一致，不要调 `invert_candle_colors()`。
    """
    theme = _theme(theme_name)
    # 均线在完整序列上算（含预热段），下面只画尾部 display_bars 根
    ma_full = {w: pd.to_numeric(df["close"], errors="coerce").rolling(w).mean()
               for w in ma_lines if len(df) >= w}

    view = df.tail(display_bars).reset_index(drop=True) if display_bars else df
    x, xcfg = _x_axis(view)
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=x, open=view["open"], high=view["high"], low=view["low"], close=view["close"],
        increasing=dict(fillcolor=theme.up_color, line=dict(color=theme.up_color, width=1)),
        decreasing=dict(fillcolor=theme.down_color, line=dict(color=theme.down_color, width=1)),
        name="K线", showlegend=False,
    ))

    ma_palette = [theme.line_color_0, theme.line_color_1]
    for i, (w, ma) in enumerate(ma_full.items()):
        fig.add_trace(go.Scatter(
            x=x, y=ma.tail(len(view)).reset_index(drop=True), mode="lines", name=f"MA{w}",
            line=dict(color=ma_palette[i % len(ma_palette)], width=1.4),
        ))

    _base_layout(fig, theme, title, height)
    fig.update_xaxes(**xcfg)
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig


def candle_macd_fig(
    df: pd.DataFrame,
    title: str = "",
    height: int = 520,
    theme_name: str = DEFAULT_THEME,
    ma_lines: Sequence[int] = (),
    price_ratio: float = 0.72,
    display_bars: Optional[int] = None,
) -> go.Figure:
    """K 线 + MACD 双面板。上图价格（可带均线），下图 MACD（DIF/DEA 线 + 柱）。

    **入参需已算好 MACD 列**（`macd_dif` / `macd_dea` / `macd_bar`）——本函数不引
    `indicators`，保持图工厂只管画、不管算。

    `display_bars` 同 `candle_fig`：调用方在**完整序列**上算好 MACD（含预热段）
    再传进来，这里只画尾部。MACD 需要约 35 根才收敛，若只取展示用的根数直接算，
    开头一大段会是空的。

    为什么不复用既有的 `ztalk_fig_v2`：它只接受 `code` 并自己去查个股表，
    指数与分钟线都用不了（同 `candle_fig` 的理由）。
    """
    theme = _theme(theme_name)
    ma_full = {w: pd.to_numeric(df["close"], errors="coerce").rolling(w).mean()
               for w in ma_lines if len(df) >= w}

    view = df.tail(display_bars).reset_index(drop=True) if display_bars else df
    x, xcfg = _x_axis(view)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.04, row_heights=[price_ratio, 1 - price_ratio],
    )

    fig.add_trace(go.Candlestick(
        x=x, open=view["open"], high=view["high"], low=view["low"], close=view["close"],
        increasing=dict(fillcolor=theme.up_color, line=dict(color=theme.up_color, width=1)),
        decreasing=dict(fillcolor=theme.down_color, line=dict(color=theme.down_color, width=1)),
        name="K线", showlegend=False,
    ), row=1, col=1)

    ma_palette = [theme.line_color_0, theme.line_color_1]
    for i, (w, ma) in enumerate(ma_full.items()):
        fig.add_trace(go.Scatter(
            x=x, y=ma.tail(len(view)).reset_index(drop=True), mode="lines", name=f"MA{w}",
            line=dict(color=ma_palette[i % len(ma_palette)], width=1.4),
        ), row=1, col=1)

    # MACD：柱按正负上色（正=红涨、负=绿跌，与 K 线同口径）
    if "macd_bar" in view.columns:
        bar = pd.to_numeric(view["macd_bar"], errors="coerce")
        fig.add_trace(go.Bar(
            x=x, y=bar, name="MACD柱", showlegend=False,
            marker=dict(color=[theme.up_color if (pd.notna(v) and v >= 0)
                               else theme.down_color for v in bar]),
        ), row=2, col=1)
    for col, name in (("macd_dif", "DIF"), ("macd_dea", "DEA")):
        if col in view.columns:
            fig.add_trace(go.Scatter(
                x=x, y=pd.to_numeric(view[col], errors="coerce"), mode="lines", name=name,
                line=dict(color=theme.line_color_0 if name == "DIF" else theme.line_color_1,
                          width=1.3),
            ), row=2, col=1)

    _base_layout(fig, theme, title, height)
    fig.update_xaxes(**xcfg)
    fig.update_xaxes(showgrid=False, zeroline=False, row=2, col=1)
    fig.update_yaxes(showgrid=True, gridcolor=theme.grid_color, gridwidth=0.5,
                     zeroline=False, row=2, col=1)
    fig.update_layout(xaxis_rangeslider_visible=False, barmode="relative")
    return fig


def save_fig(fig: go.Figure, path: Path, width: int = 600,
             height: Optional[int] = None, scale: int = 3) -> Path:
    """落 PNG。kaleido 在 conda stock 环境里可用（项目里 `kline_card.py:45` 同一用法）。

    `scale=3` 是为了在高分屏上不糊——报告内容区 560 CSS px，图按 600 出再缩到 100% 宽。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    h = height or int(fig.layout.height or 320)
    fig.write_image(str(path), format="png", width=width, height=h, scale=scale)
    if not path.is_file():
        raise RuntimeError(f"图片未落盘: {path}")
    return path
