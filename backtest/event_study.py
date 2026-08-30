"""事件研究骨架：检验「信号出现后，价格是否朝预期方向走了」。

回测策略有效性分两类，本模块只做第一类：

1. **事件研究** —— 信号出现后 N 日内，后续收益 / 最深回撤是多少，是否
   显著偏离基准。适合回答「这个买入/卖出信号有没有用」，不含资金曲线。
2. 组合模拟 —— 完整撮合 + 仓位 + 费用，输出净值曲线。以后需要再加。

事件研究要回答「信号有没有用」，光报「信号后跌了 X%」是不够的，必须比基准：

- **无条件基准**：同一宇宙里随机交易日的前向分布。剥离「这段时间大盘整体在跌」。
- **市场匹配基准**：信号日当天，全市场（同宇宙）中位前向走势。剥离大盘 beta，
  剩下的才是信号自身的选股信息。

约定：
- forward 指标一律从**信号日收盘价**起算（卖出信号问的是「现在卖，能躲掉多少」）。
- 回撤用最低价捕捉盘中下探；收益用收盘价。
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

DEFAULT_HORIZONS = (5, 10, 20, 40, 60)

# 列名：前向收益 / 最深回撤 / 最大反弹，按窗口 k 展开成 ret_k / dd_k / up_k
RET = "ret_{k}"
DD = "dd_{k}"
UP = "up_{k}"
MKT_RET = "mkt_ret_{k}"
MKT_DD = "mkt_dd_{k}"
MKT_UP = "mkt_up_{k}"


def forward_metrics(close: np.ndarray, low: np.ndarray, i: int,
                    horizons: Iterable[int] = DEFAULT_HORIZONS) -> dict:
    """事件行号 i 起、后续各窗口的前向收益 / 最深回撤 / 最大反弹。

    fwd_ret[k] = close[i+k] / close[i] - 1          （窗口末收益）
    fwd_dd[k]  = min(low[i+1 : i+k+1]) / close[i] - 1   （最深回撤，用最低价）
    fwd_up[k]  = max(close[i+1 : i+k+1]) / close[i] - 1 （最大反弹，用收盘价）

    三者合起来刻画信号后的走势形状：跌多深（dd）、能不能弹回（up）、
    最终落在哪（ret）。一个「卖出信号」越有效，越应该 dd 深而 up 低——
    弹不回来才是真出货，跌完强反弹多半只是洗盘。

    数据不足（窗口超出样本末端）时置 NaN。
    """
    base = close[i]
    n = len(close)
    out: dict = {}
    for k in horizons:
        j = i + k
        if j >= n:
            out[RET.format(k=k)] = np.nan
            out[DD.format(k=k)] = np.nan
            out[UP.format(k=k)] = np.nan
            continue
        seg = close[i + 1: j + 1]
        out[RET.format(k=k)] = close[j] / base - 1
        out[DD.format(k=k)] = low[i + 1: j + 1].min() / base - 1
        out[UP.format(k=k)] = seg.max() / base - 1
    return out


def summarize(events: pd.DataFrame,
              horizons: Iterable[int] = DEFAULT_HORIZONS) -> pd.DataFrame:
    """把事件长表聚合成一张「各窗口收益/回撤分布」表。

    events 需含 ret_k / dd_k 列。返回一行一个窗口：
        n           有效事件数
        mean_ret    前向收益均值
        median_ret  前向收益中位数
        mean_dd     最深回撤均值（负值越大越深）
        median_dd   最深回撤中位数
        mean_up     最大反弹均值（正 = 跌完能弹回信号价之上）
        median_up   最大反弹中位数
        pct_dd_lt_-10  回撤跌破 -10% 的事件占比
        pct_dd_lt_-20  回撤跌破 -20% 的事件占比
    """
    rows = []
    for k in horizons:
        dd = events[DD.format(k=k)].dropna()
        ret = events[RET.format(k=k)].dropna()
        up = events[UP.format(k=k)].dropna()
        rows.append({
            "horizon": k,
            "n": int(len(dd)),
            "mean_ret": float(ret.mean()),
            "median_ret": float(ret.median()),
            "mean_dd": float(dd.mean()),
            "median_dd": float(dd.median()),
            "mean_up": float(up.mean()),
            "median_up": float(up.median()),
            "pct_dd_lt_-10": float((dd <= -0.10).mean()),
            "pct_dd_lt_-20": float((dd <= -0.20).mean()),
        })
    return pd.DataFrame(rows)


def market_baseline(panel: dict, dates: Iterable,
                    horizons: Iterable[int] = DEFAULT_HORIZONS) -> pd.DataFrame:
    """市场匹配基准：每个事件日，同宇宙全部股票的中位前向走势。

    Args:
        panel: {code: DataFrame(index=date, columns=['close','low'])}，date 为
               DatetimeIndex。某股停牌导致无当日行情时跳过该股。
        dates: 需要基准的事件日集合。

    Returns:
        DataFrame(index=date, columns=[mkt_ret_k, mkt_dd_k])。
        mkt_dd_k 是当天全市场中位最深回撤——用它减掉大盘 beta。
    """
    rows: dict = {}
    for d in dates:
        row: dict = {}
        for k in horizons:
            dds, rets, ups = [], [], []
            for p in panel.values():
                try:
                    pos = p.index.get_loc(d)
                except KeyError:
                    continue
                if pos + k >= len(p):
                    continue
                base = p["close"].iloc[pos]
                dds.append(p["low"].iloc[pos + 1: pos + k + 1].min() / base - 1)
                seg = p["close"].iloc[pos + 1: pos + k + 1]
                rets.append(p["close"].iloc[pos + k] / base - 1)
                ups.append(seg.max() / base - 1)
            row[MKT_RET.format(k=k)] = float(np.median(rets)) if rets else np.nan
            row[MKT_DD.format(k=k)] = float(np.median(dds)) if dds else np.nan
            row[MKT_UP.format(k=k)] = float(np.median(ups)) if ups else np.nan
        rows[d] = row
    return pd.DataFrame.from_dict(rows, orient="index")


def join_market(events: pd.DataFrame, mkt: pd.DataFrame,
                horizons: Iterable[int] = DEFAULT_HORIZONS) -> pd.DataFrame:
    """把市场基准并到事件表，并算事件相对市场的超额（alpha）。

    新增列：
        alpha_dd_k = dd_k - mkt_dd_k   （负 = 比市场跌得更多 = 信号有选股信息）
        alpha_ret_k = ret_k - mkt_ret_k
        alpha_up_k = up_k - mkt_up_k   （负 = 反弹不如市场 = 跌完起不来）
    """
    e = events.copy()
    e = e.join(mkt, on="date")
    for k in horizons:
        e[f"alpha_dd_{k}"] = e[DD.format(k=k)] - e[MKT_DD.format(k=k)]
        e[f"alpha_ret_{k}"] = e[RET.format(k=k)] - e[MKT_RET.format(k=k)]
        e[f"alpha_up_{k}"] = e[UP.format(k=k)] - e[MKT_UP.format(k=k)]
    return e
