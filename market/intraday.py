"""上证指数分钟级走势：30 / 60 / 120 分钟的指标位置与背离。

用途来自交易系统对分钟级别的两条定位：

    小级别入场   120/60 分钟关键位底部钝化 → 确认入场与加仓点
    多周期盯盘   用 MACD 顶底背离做日内 T

还有一条框架约束：**级别越大噪音越小，小级别买点需放更大级别确认**。所以本模块
不只报各周期读数，还会给一个跨周期的**一致性判定**——30 分钟转多但 60/120 还在
空头时，那只是小级别反弹，不是趋势转折。

数据来自 `index_bars_min`（30 分钟，60/120 由查询层按交易时段合成）。

用法:
    python -m market.intraday [YYYYMMDD]
"""
from __future__ import annotations

import sys
from typing import Optional

import pandas as pd

from datas.query_stock import query_index_min_bars
from draws.kline_theme import ThemeRegistry  # noqa: F401  (保持与其它 market 模块一致的导入风格)
from indicators.bbi import add_bbi_to_dataframe
from indicators.kdj import add_kdj_to_dataframe
from indicators.macd import add_macd_to_dataframe
from market.risks import bearish_divergence, bullish_divergence
from tools.log import get_analyze_logger

logger = get_analyze_logger()

DEFAULT_SYMBOL = "sh000001"
PERIODS = (30, 60, 120)
BARS = 400              # 取多少根算指标
KEY_RANGE = 60          # 关键位取近多少根的高低点

CALIBER = ("数据为指数分钟线（30 分钟入库，60/120 按交易时段合成）。"
           "关键位取近 %d 根的最高/最低；背离口径与日线风险扫描一致。"
           "分钟级信号需大级别确认——小周期单独转向不构成趋势判断" % KEY_RANGE)


def _one_period(symbol: str, period: int, to_dt: Optional[str]) -> Optional[dict]:
    df = query_index_min_bars(symbol, period=period, to_dt=to_dt, limit=BARS)
    if df.empty or len(df) < 40:
        return None

    d = df.copy().reset_index(drop=True)
    add_macd_to_dataframe(d, inplace=True)
    add_kdj_to_dataframe(d, inplace=True)
    add_bbi_to_dataframe(d, inplace=True)

    last = d.iloc[-1]
    close = float(last["close"])
    bbi = last.get("bbi")
    dif, dea, bar = last["macd_dif"], last["macd_dea"], last["macd_bar"]
    j = last["kdj_j"]

    # MACD 柱的方向：与上一根比
    bar_prev = d["macd_bar"].iloc[-2] if len(d) > 1 else None
    bar_dir = None
    if pd.notna(bar) and pd.notna(bar_prev):
        bar_dir = "扩张" if abs(bar) > abs(bar_prev) else "收缩"

    key = d.tail(KEY_RANGE)
    hi, lo = float(key["high"].max()), float(key["low"].min())

    # 两个方向都要看：顶背离是卖点，底背离是买点（系统里「小级别关键位底部钝化
    # 确认入场与加仓点」用的就是后者）。只报一个方向等于少了一半信息。
    div = bearish_divergence(d["close"], d["macd_dif"], d["macd_bar"])
    div_bull = bullish_divergence(d["close"], d["macd_dif"], d["macd_bar"])

    return {
        "周期": f"{period}分钟",
        "时刻": pd.to_datetime(last["dt"]).strftime("%m-%d %H:%M"),
        "收盘": round(close, 2),
        "涨跌": round(float(last["close"]) / float(d["close"].iloc[-2]) * 100 - 100, 2)
                if len(d) > 1 else None,
        "位置": ("BBI 上方" if pd.notna(bbi) and close > bbi else
                 "BBI 下方" if pd.notna(bbi) else None),
        "距BBI": round((close / float(bbi) - 1) * 100, 2) if pd.notna(bbi) else None,
        "MACD": {
            "DIF": round(float(dif), 2) if pd.notna(dif) else None,
            "DEA": round(float(dea), 2) if pd.notna(dea) else None,
            "水上": bool(pd.notna(dif) and dif > 0),
            "金叉": bool(pd.notna(dif) and pd.notna(dea) and dif > dea),
            "柱": bar_dir,
        },
        "KDJ_J": round(float(j), 1) if pd.notna(j) else None,
        "J状态": (None if pd.isna(j) else
                  "超买" if j >= 100 else "偏高" if j >= 85 else
                  "超卖" if j <= 0 else "偏低" if j <= 15 else "中性"),
        "关键位": {"高": round(hi, 2), "低": round(lo, 2),
                   "距高": round((close / hi - 1) * 100, 2),
                   "距低": round((close / lo - 1) * 100, 2)},
        "顶背离": div,
        "底背离": div_bull,
    }


def intraday_state(symbol: str = DEFAULT_SYMBOL,
                   to_dt: Optional[str] = None,
                   periods=PERIODS) -> dict:
    """各周期的分钟级状态 + 跨周期一致性。"""
    rows = []
    for p in periods:
        r = _one_period(symbol, p, to_dt)
        if r:
            rows.append(r)
    if not rows:
        return {"error": f"{symbol} 无分钟数据（先跑 datas.fetch_index_min_bars）"}

    # 跨周期一致性。判据是「金叉/死叉」的**有序推进**——按周期从小到大看，
    # 是不是逐级确认。这直接对应交易系统那条「级别越大噪音越小，小级别买点需
    # 放更大级别确认」：30 分钟金叉但 60/120 还死叉，只是小级别反弹。
    cross = [(r["周期"], r["MACD"]["金叉"], r["MACD"]["水上"]) for r in rows]
    ups = [c for c, cross_, _ in cross if cross_]
    downs = [c for c, cross_, _ in cross if not cross_]

    if not downs:
        consistent = "多周期一致转多" + ("，且已在水上" if all(w for _, _, w in cross)
                                          else "（但均在水下，属超跌反弹）")
    elif not ups:
        consistent = "多周期一致偏空"
    else:
        # 小周期先转，大周期未确认——这是最常见的分歧形态
        order = [c for c, _, _ in cross]
        if order.index(ups[0]) == 0 and set(ups) == set(order[:len(ups)]):
            consistent = (f"**小周期先转**：{'、'.join(ups)} 已金叉，"
                          f"{'、'.join(downs)} 仍未确认——"
                          f"按系统规则，小级别买点需大级别确认，**单独转向不构成趋势判断**")
        else:
            consistent = f"分歧：{'、'.join(ups)} 金叉，{'、'.join(downs)} 死叉"

    return {
        "symbol": symbol,
        "数据截至": rows[0]["时刻"],
        "周期": rows,
        "一致性": consistent,
        "口径": CALIBER,
    }


def render_intraday(a: dict) -> str:
    if a.get("error"):
        return f"❌ {a['error']}"
    lines = [f"# {a['symbol']} 分钟级走势　{a['数据截至']}", ""]
    # 一致性文案里可能已自带加粗标记，别再包一层（会渲染成 ****xxx**）
    txt = a["一致性"]
    lines.append(txt if "**" in txt else f"**{txt}**")
    lines.append("")
    for r in a["周期"]:
        m = r["MACD"]
        lines.append(f"### {r['周期']}　收 {r['收盘']:,.2f}"
                     + (f"（{r['涨跌']:+.2f}%）" if r["涨跌"] is not None else ""))
        bits = []
        if r["位置"]:
            bits.append(f"{r['位置']}（{r['距BBI']:+.2f}%）")
        bits.append(f"MACD {'水上' if m['水上'] else '水下'}"
                    f"{'金叉' if m['金叉'] else '死叉'}"
                    + (f"柱{m['柱']}" if m["柱"] else ""))
        if r["KDJ_J"] is not None:
            bits.append(f"J {r['KDJ_J']}" + (f"（{r['J状态']}）" if r["J状态"] else ""))
        lines.append("　".join(bits))
        k = r["关键位"]
        lines.append(f"关键位（近 {KEY_RANGE} 根）：{k['低']:,.2f} ~ {k['高']:,.2f}"
                     f"　现价距高 {k['距高']:+.2f}%、距低 {k['距低']:+.2f}%")
        if r["顶背离"]:
            dv = r["顶背离"]
            lines.append(f"⚠ 顶背离（卖点）：{dv['前高']} → {dv['后高']}"
                         f"　依据 {dv['依据']}　{dv['距今']} 根前")
        if r["底背离"]:
            dv = r["底背离"]
            lines.append(f"◆ 底背离（买点）：{dv['前低']} → {dv['后低']}"
                         f"　依据 {dv['依据']}　{dv['距今']} 根前")
        lines.append("")
    lines.append(f"> {a['口径']}")
    return "\n".join(lines)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    to = f"{arg[:4]}-{arg[4:6]}-{arg[6:8]} 23:59" if arg else None
    print(render_intraday(intraday_state(to_dt=to)))
