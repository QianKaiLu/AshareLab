"""成交日的客观测量快照（设计决策 D14）。

每笔交易落盘时算一次存死，而不是等回测时再重算历史——重算会撞上前复权因子变化
与数据修订，同一笔交易在不同时间算出不同的值，结论不可复现。

只测不判：这里给数字与状态标签，「买得对不对」由 skill 层的 AI 结合交易系统评价。

取数一律带 `to_date`，只用成交日及之前的数据，避免快照里混进未来信息。
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

import hunters.z_b1_hunter as b1
from datas.query_stock import query_bars_by_days
from indicators.bbi import add_bbi_to_dataframe
from indicators.kdj import add_kdj_to_dataframe
from indicators.kdj_weekly import add_kdj_weekly_to_dataframe
from indicators.macd import add_macd_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe

BARS = 500          # B1 的点火识别需要足够长的历史，与 b1_review 保持一致
CROSS_LOOKBACK = 5  # 金叉/死叉「新近发生」的判定窗口（交易日）


def _num(v: Any, digits: int = 2) -> Optional[float]:
    """转成能进 JSON 的 float。numpy 标量与 NaN 都在这里处理掉。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, digits)


def _jsonable(v: Any, digits: int = 3) -> Any:
    """把 hunt_b1 返回的 numpy 标量转成 JSON 原生类型。

    np.bool_ 不是 Python bool，直接走 _num() 会把 False 存成 0.0——事后读记录时
    「是否高位」变成数字，含义就丢了，所以布尔要先于数值判断。
    """
    if v is None or isinstance(v, (str, bool)):
        return v
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (int, np.integer)) and not isinstance(v, bool):
        return int(v)
    return _num(v, digits)


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """加齐快照需要的指标列。辅助列命名跟 z_b1_hunter 对齐，以便直接复用其阶段函数。"""
    d = df.copy()
    add_kdj_to_dataframe(d, inplace=True)
    add_kdj_weekly_to_dataframe(d, inplace=True)
    add_zxdkx_to_dataframe(d, inplace=True)
    add_bbi_to_dataframe(d, inplace=True)
    add_macd_to_dataframe(d, inplace=True)
    add_volume_ma_to_dataframe(d, periods=[5, b1.CONSOLIDATION_DAYS, 60], inplace=True)
    d["_pct_change_oc"] = d["close"] / d["open"] - 1
    d["_is_up"] = d["close"] > d["open"]
    d["_is_down"] = d["close"] < d["open"]
    return d


def _line_position(close: float, white: Optional[float], yellow: Optional[float]) -> Optional[str]:
    """现价相对双线的位置。波段交易只做黄线之上（波段交易系统.md）。"""
    if white is None or yellow is None:
        return None
    if close >= white and close >= yellow:
        return "双线之上"
    if close < min(white, yellow):
        return "双线之下"
    return "白黄之间"


def _macd_state(d: pd.DataFrame) -> dict:
    """MACD 的三个层次（macd.md）：趋势背景 / 趋势变化 / 变化强弱。"""
    if len(d) < 2 or "macd_dif" not in d:
        return {}
    last, prev = d.iloc[-1], d.iloc[-2]
    dif, dea, bar = last["macd_dif"], last["macd_dea"], last["macd_bar"]
    if not all(np.isfinite([dif, dea, bar])):
        return {}

    background = "水上" if dif > 0 else "水下"
    relation = "DIF在DEA上" if dif > dea else "DIF在DEA下"

    # 柱体收扩：看绝对值，红柱缩短与绿柱缩短都是「动能减弱」
    prev_bar = prev["macd_bar"]
    strength = None
    if np.isfinite(prev_bar):
        if abs(bar) > abs(prev_bar):
            strength = "柱扩张"
        elif abs(bar) < abs(prev_bar):
            strength = "柱收缩"
        else:
            strength = "柱持平"

    # 近期是否刚发生金叉/死叉
    cross = None
    window = d.tail(CROSS_LOOKBACK + 1)
    diff = (window["macd_dif"] - window["macd_dea"]).to_numpy(dtype=float)
    for i in range(len(diff) - 1, 0, -1):
        if not (np.isfinite(diff[i]) and np.isfinite(diff[i - 1])):
            continue
        if diff[i - 1] <= 0 < diff[i]:
            cross = f"{len(diff) - 1 - i} 日前金叉"
            break
        if diff[i - 1] >= 0 > diff[i]:
            cross = f"{len(diff) - 1 - i} 日前死叉"
            break

    state = {
        "macd_dif": _num(dif, 4),
        "macd_dea": _num(dea, 4),
        "macd_bar": _num(bar, 4),
        "macd_state": f"{background} / {relation}" + (f" / {strength}" if strength else ""),
    }
    if cross:
        state["macd_cross"] = cross
    return state


def _b1_fields(d: pd.DataFrame) -> dict:
    """B1 相关测量。命中就取 hunt_b1 的全套字段；没命中也给出止损参考与区间位置。

    没命中不等于没价值——记录下来才能事后统计「我有多少笔是踩在规则内的」。
    """
    out: dict[str, Any] = {}

    # hunt_b1 会就地加列，给个副本免得污染上层 DataFrame
    hit = b1.hunt_b1(d.copy())
    out["b1_hit"] = hit is not None
    if hit:
        for k, v in hit.items():
            out[k] = _jsonable(v)
        if isinstance(hit.get("fire_date"), (pd.Timestamp, np.datetime64)):
            out["fire_date"] = str(pd.Timestamp(hit["fire_date"]).date())
        # 点火期的绝对量值对事后判读没帮助（比值已经存了），去掉免得记录臃肿
        for noisy in ("max_volume_dur_fire", "mean_volume_dur_fire"):
            out.pop(noisy, None)
        return out

    # 未命中：补上不依赖命中的两项，便于事后对照
    out.update({k: v for k, v in b1._stop_loss_hint(d).items()})
    key = f"volume_ma_{b1.CONSOLIDATION_DAYS}"
    try:
        fires = list(b1._find_ignitions(d, d["close"].to_numpy(), key))
    except Exception:
        fires = []
    if fires:
        fire = fires[0]  # _find_ignitions 由近及远，取最近的一段
        post = d.iloc[fire.start_idx:]
        hi, lo = post["high"].max(), post["low"].min()
        out["fire_date"] = str(pd.Timestamp(fire.date).date())
        out["fire_days"] = int(fire.days)
        out["fire_pct"] = _num(fire.acc_pct)
        out["support_price"] = _num(fire.support_price)
        if hi > lo:
            out["pos_in_breakout_range"] = _num(
                (float(d.iloc[-1]["close"]) - lo) / (hi - lo), 2
            )
        if fire.max_volume:
            out["last_day_volume_ratio"] = _num(
                float(d.iloc[-1]["volume"]) / fire.max_volume, 3
            )
    return out


def collect(code: str, day: Optional[str] = None, bars: int = BARS) -> dict:
    """采集 code 在 day 收盘后的测量快照。

    day 为 None 时用库里最新交易日。若库里当日数据还没到（日更没跑、停牌、
    或成交当天盘中就录入），快照会带 `date_mismatch` 说明实际用的是哪一天——
    宁可标注清楚，也不要静默用邻近日期冒充。
    """
    df = query_bars_by_days(code=code, days=bars, to_date=day)
    if df is None or df.empty:
        return {"error": f"{code} 在 {day or '最新'} 之前无行情数据"}
    if len(df) < 30:
        return {"error": f"{code} 仅 {len(df)} 根 K 线，不足以测量（新股？）"}

    d = _prepare(df)
    last = d.iloc[-1]
    actual = str(pd.Timestamp(last["date"]).date())

    snap: dict[str, Any] = {"date": actual, "bars": int(len(d))}
    if day:
        want = str(pd.Timestamp(day).date()) if "-" in str(day) else (
            f"{str(day)[:4]}-{str(day)[4:6]}-{str(day)[6:8]}"
        )
        if want != actual:
            snap["date_mismatch"] = f"请求 {want}，实际用 {actual}"

    close = float(last["close"])
    white = _num(last.get("z_white"))
    yellow = _num(last.get("z_yellow"))
    snap.update(
        {
            "close": _num(close),
            "change_pct": _num(last.get("change_pct")),
            "amplitude_pct": _num(last.get("amplitude")),
            "z_white": white,
            "z_yellow": yellow,
            "bbi": _num(last.get("bbi")),
            "line_position": _line_position(close, white, yellow),
            "close_to_yellow_pct": _num((close / yellow - 1) * 100) if yellow else None,
            "close_to_bbi_pct": (
                _num((close / float(last["bbi"]) - 1) * 100)
                if np.isfinite(last.get("bbi", np.nan)) and last["bbi"]
                else None
            ),
            "kdj_j": _num(last.get("kdj_j")),
            "kdj_j_weekly": _num(last.get("kdj_j_weekly")),
        }
    )

    # 量能：相对 5 日均量看当日强弱，近 60 日分位看是否地量
    vma5 = last.get("volume_ma_5")
    if vma5 and np.isfinite(vma5) and vma5 > 0:
        snap["vol_ratio"] = _num(float(last["volume"]) / float(vma5))
    vol60 = d["volume"].tail(60)
    if len(vol60) >= 20:
        snap["vol_pct_in_60d"] = _num(
            float((vol60 < float(last["volume"])).sum()) / len(vol60), 2
        )

    snap.update(_macd_state(d))
    snap.update(_b1_fields(d))
    return snap


def describe(snap: dict) -> str:
    """把快照排成人读的几行，供 CLI 回显确认。"""
    if snap.get("error"):
        return f"  快照不可用：{snap['error']}"
    lines = []
    if snap.get("date_mismatch"):
        lines.append(f"  ⚠ {snap['date_mismatch']}")
    lines.append(
        f"  {snap['date']}  收 {snap.get('close')}  "
        f"J {snap.get('kdj_j')}  周J {snap.get('kdj_j_weekly')}"
    )
    lines.append(
        f"  白 {snap.get('z_white')} / 黄 {snap.get('z_yellow')} / BBI {snap.get('bbi')}"
        f"  {snap.get('line_position') or ''}"
    )
    if snap.get("macd_state"):
        extra = f"  {snap['macd_cross']}" if snap.get("macd_cross") else ""
        lines.append(f"  MACD {snap['macd_state']}{extra}")
    b1_line = "  B1 " + ("命中 " + str(snap.get("variant")) if snap.get("b1_hit") else "未命中")
    if snap.get("pos_in_breakout_range") is not None:
        b1_line += f"  区间位置 {snap['pos_in_breakout_range']}"
    if snap.get("stop_loss_line"):
        b1_line += f"  止损参考 {snap['stop_loss_line']}@{snap.get('stop_loss_price')}"
    lines.append(b1_line)
    return "\n".join(lines)
