"""周线 KDJ。

服务「长短周期共振」的判断：长线票先看周线 J 是否进入超卖区，再用日线 J 找具体
入场点（见 trading_system/kdj.md）。

与直接对周线重采样再算 KDJ 的区别 —— **不能把整周的 J 值贴回该周每一天**，那样
周一就用到了周五的数据，是未来函数。这里按「周内到当日」（week-to-date）计算：

    某日的周线 J = 用「已完成周的平滑基数」+「当周截至当日的 OHLC」推进一步

所以周中每天的周线 J 会随行情变动，到周五收盘时正好等于该周完整周线 K 算出的值
（`verify_alignment` 校验这一点）。这与行情软件里周 K 实时形成的行为一致。

周划分按自然周（周一~周日），A 股即周一~周五。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from indicators.kdj import kdj


def resample_weekly(
    df: pd.DataFrame,
    date_col: str = "date",
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: Optional[str] = "volume",
) -> pd.DataFrame:
    """日线聚合成周线。

    最后一周若未走完，同样输出（形成中的周 K），这是有意为之——周线判断要能看到
    当周的进展，不能等周五才有值。
    """
    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col])
    week = d[date_col].dt.to_period("W")

    spec = {
        "date": (date_col, "last"),      # 该周最后一个交易日
        "open": (open_col, "first"),
        "high": (high_col, "max"),
        "low": (low_col, "min"),
        "close": (close_col, "last"),
    }
    if volume_col and volume_col in d.columns:
        spec["volume"] = (volume_col, "sum")

    out = d.groupby(week, sort=True).agg(**spec)
    out.index.name = "week"
    out["bars"] = d.groupby(week, sort=True).size()  # 该周含几个交易日，用于判断是否走完
    return out.reset_index()


def kdj_weekly(
    df: pd.DataFrame,
    date_col: str = "date",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    period: int = 9,
    k_period: int = 3,
    d_period: int = 3,
) -> pd.DataFrame:
    """计算周线 KDJ，结果对齐回日线的每一行。

    Returns:
        pd.DataFrame，与 df 同长同序，列 `kdj_k_weekly` / `kdj_d_weekly` / `kdj_j_weekly`
    """
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["kdj_k_weekly", "kdj_d_weekly", "kdj_j_weekly"], index=df.index if df is not None else None
        )

    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col])
    weeks = d[date_col].dt.to_period("W")

    # 周线序列（含未走完的当周），用于取「上一完成周」的 K/D 平滑基数
    wk = (
        d.assign(_w=weeks)
        .groupby("_w", sort=True)
        .agg(high=(high_col, "max"), low=(low_col, "min"), close=(close_col, "last"))
    )

    w_index = {w: i for i, w in enumerate(wk.index)}
    w_high = wk["high"].to_numpy(dtype=float)
    w_low = wk["low"].to_numpy(dtype=float)

    # 平滑基数必须用**未舍入**的周线 K/D：J = 3K - 2D 会把 K/D 的舍入误差放大约 5 倍，
    # 若拿 kdj() 已 round(2) 的输出当递推起点，周五对齐校验会出现 ~0.02 的偏差
    w_high_roll = wk["high"].rolling(window=period, min_periods=1).max()
    w_low_roll = wk["low"].rolling(window=period, min_periods=1).min()
    w_denom = w_high_roll - w_low_roll
    w_rsv = np.where(w_denom == 0, 50.0, (wk["close"] - w_low_roll) / w_denom * 100)
    w_rsv = pd.Series(w_rsv, index=wk.index)
    prev_k = w_rsv.ewm(com=k_period - 1, adjust=False).mean().to_numpy(dtype=float)
    prev_d = (
        pd.Series(prev_k, index=wk.index)
        .ewm(com=d_period - 1, adjust=False)
        .mean()
        .to_numpy(dtype=float)
    )

    # ewm(com=n-1, adjust=False) 等价于 alpha = 1/n 的递推，与 indicators/kdj.py 一致
    alpha_k = 1.0 / k_period
    alpha_d = 1.0 / d_period

    highs = d[high_col].to_numpy(dtype=float)
    lows = d[low_col].to_numpy(dtype=float)
    closes = d[close_col].to_numpy(dtype=float)

    ks = np.empty(len(d))
    ds = np.empty(len(d))

    wtd_high = -np.inf
    wtd_low = np.inf
    cur_week = None

    for i in range(len(d)):
        w = weeks.iloc[i]
        if w != cur_week:          # 进入新的一周，周内累计重置
            cur_week = w
            wtd_high = highs[i]
            wtd_low = lows[i]
        else:
            wtd_high = max(wtd_high, highs[i])
            wtd_low = min(wtd_low, lows[i])

        wi = w_index[w]
        # 回看窗口：前 period-1 个已完成周 + 当周截至今日。min_periods=1 语义，
        # 与日线 kdj 的 rolling(min_periods=1) 对齐
        lo = max(0, wi - (period - 1))
        if wi > lo:
            high_max = max(w_high[lo:wi].max(), wtd_high)
            low_min = min(w_low[lo:wi].min(), wtd_low)
        else:
            high_max, low_min = wtd_high, wtd_low

        denom = high_max - low_min
        rsv = 50.0 if denom == 0 else (closes[i] - low_min) / denom * 100.0

        if wi == 0:
            # 首周无平滑基数，按 ewm(adjust=False) 的初值语义：K=RSV, D=K
            k = rsv
            dd = k
        else:
            k = (1 - alpha_k) * prev_k[wi - 1] + alpha_k * rsv
            dd = (1 - alpha_d) * prev_d[wi - 1] + alpha_d * k

        ks[i] = k
        ds[i] = dd

    return pd.DataFrame(
        {
            "kdj_k_weekly": np.round(ks, 2),
            "kdj_d_weekly": np.round(ds, 2),
            "kdj_j_weekly": np.round(3 * ks - 2 * ds, 2),
        },
        index=d.index,
    )


def add_kdj_weekly_to_dataframe(
    df: pd.DataFrame,
    date_col: str = "date",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    period: int = 9,
    k_period: int = 3,
    d_period: int = 3,
    inplace: bool = False,
) -> Optional[pd.DataFrame]:
    """给日线 DataFrame 加周线 KDJ 列。

    Example:
        >>> df = query_bars_by_days('300314', days=500)
        >>> add_kdj_weekly_to_dataframe(df, inplace=True)
        >>> df[['date', 'kdj_j_weekly']].tail()
    """
    res = kdj_weekly(df, date_col, high_col, low_col, close_col, period, k_period, d_period)
    target = df if inplace else df.copy()
    for col in res.columns:
        target[col] = res[col]
    return None if inplace else target


def verify_alignment(
    df: pd.DataFrame,
    date_col: str = "date",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    period: int = 9,
    k_period: int = 3,
    d_period: int = 3,
    tol: float = 0.011,
) -> dict:
    """自检：每个已走完周的最后一个交易日，其 week-to-date 值应等于该周完整周线 K 的值。

    这是本模块正确性的核心保证——如果这条不成立，说明周内推进的递推写错了。
    """
    daily = kdj_weekly(df, date_col, high_col, low_col, close_col, period, k_period, d_period)
    wk = resample_weekly(df, date_col=date_col, high_col=high_col, low_col=low_col, close_col=close_col)
    wk_kdj = kdj(wk["high"], wk["low"], wk["close"], period, k_period, d_period)

    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col])
    last_of_week = d.groupby(d[date_col].dt.to_period("W"))[date_col].transform("max") == d[date_col]

    checked = mismatch = 0
    worst = 0.0
    detail = []
    for wi, (_, row) in enumerate(wk.iterrows()):
        idx = d.index[last_of_week & (d[date_col] == row["date"])]
        if len(idx) != 1:
            continue
        got = float(daily.loc[idx[0], "kdj_j_weekly"])
        want = float(wk_kdj["kdj_j"].iloc[wi])
        checked += 1
        diff = abs(got - want)
        worst = max(worst, diff)
        if diff > tol:
            mismatch += 1
            if len(detail) < 5:
                detail.append({"date": str(row["date"])[:10], "got": got, "want": want})

    return {"检查周数": checked, "不一致": mismatch, "最大偏差": round(worst, 4), "样例": detail}
