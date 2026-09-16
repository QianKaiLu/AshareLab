"""市场阶段判定 → 当前该用哪套打法。

交易系统里有三套打法按市场阶段切换：

    大单边     → 做突破（右侧趋势跟随）
    箱体震荡   → 高抛低吸，不追突破
    大级别底部 → 左侧分批建仓

「空头区间、仓位 1~2 成」只说了**能做多重**，没说**该用哪套**。对短线的人来说，
「现在该空仓等」和「现在可以做箱体高抛低吸」是完全不同的操作——这个缺口由本模块补。

阶段由三个维度交叉判定：

    趋势方向   活跃市值区间 + 指数 60 日线斜率
    箱体特征   价格在窄幅区间内来回（60 线走平 + 区间宽度小）
    底部特征   周线 KDJ 深度超卖（J ≤ 0）——大级别底部的标志

用法:
    python -m market.stage [YYYYMMDD]
"""
from __future__ import annotations

import sys
from typing import Optional

import pandas as pd

from datas.query_stock import query_index_bars
from indicators.kdj import add_kdj_to_dataframe
from indicators.kdj_weekly import add_kdj_weekly_to_dataframe
from market.amv import amv_timing
from tools.log import get_analyze_logger

logger = get_analyze_logger()

SLOPE_FLAT = 0.5        # 60 线近 5 日斜率绝对值小于此值（%）算走平
RANGE_WINDOW = 60       # 箱体用最近多少根度量
RANGE_NARROW = 0.10     # 区间宽度 / 中值 小于此值算窄幅
# 周线 J 阈值。**标定依据（2026-09-16 实测上证 8726 根日线）**：
#   上证周线 J 的历史范围约 -24 ~ +126，10% 分位 2.3、25% 分位 17.6。
#   已知大底读数：2019-01 底 J=22.9、2022-10 底 J=17.6、2024-02 底 J=25.2、
#   2024-09 底 J=-0.3。
# 取 0 是**高精度低召回**的选择：只抓极端底（历史上仅 1991、2004、2011、
# 2019-05、2024-09 等几次）。会漏掉 J 在 15~25 区间的底（如 2019-01、2024-02），
# 这是有意的——放宽到 20 会让它在四分之一的时间里都报「大级别底部」，那就没意义了。
BOTTOM_J = 0.0
BOTTOM_J_NEAR = 20.0    # 未达极值但偏低，值得留意（不改变阶段判定，只提示）

STAGES = {
    "单边上涨": "做突破（右侧趋势跟随）。回踩关键位/均线不破可加仓。",
    "单边下跌": "不接飞刀。做突破是逆势，做超跌是赌底——以观察为主，等站上 60 日线。",
    "大级别底部": "左侧分批建仓。资金分份、越跌越买、与时间做朋友——前提是标的不会退市。",
}

# 箱体的打法要分资金方向——同样叫「箱体震荡」，钱在进和钱在走是两回事：
#   资金流入 → 标准高抛低吸（上沿减、下沿加）
#   资金流出 → 只做上沿减仓，**不做下沿加仓**（下沿大概率被击穿）
BOX_PLAYBOOK = {
    "in": "高抛低吸。箱体上沿减、下沿加，不追突破（震荡市里突破多为假信号）。",
    "out": ("高抛低吸，但**只做上沿减仓、不做下沿加仓**——资金持续流出，"
            "箱体下沿大概率被击穿。等破位后站回再谈。"),
}


def _index_frame(symbol: str, target: str, bars: int = 400) -> Optional[pd.DataFrame]:
    df = query_index_bars(symbol, to_date=target)
    if df.empty or len(df) < 80:
        return None
    return df.tail(bars).reset_index(drop=True)


def _narrow_range(df: pd.DataFrame) -> Optional[dict]:
    """最近 RANGE_WINDOW 根的区间宽度（相对中值）。"""
    sub = df.tail(RANGE_WINDOW)
    if len(sub) < 20:
        return None
    hi, lo = float(sub["high"].max()), float(sub["low"].min())
    mid = (hi + lo) / 2
    if mid <= 0:
        return None
    width = (hi - lo) / mid
    return {"高": round(hi, 2), "低": round(lo, 2), "宽度": round(width * 100, 2),
            "窄幅": width <= RANGE_NARROW}


def market_stage(target: str) -> dict:
    """判定当前市场阶段并给出对应打法。"""
    amv = amv_timing(target)
    day = target

    idx = _index_frame("sh000001", day)
    if idx is None:
        return {"error": f"{day} 上证数据不足，无法判定阶段"}

    close = pd.to_numeric(idx["close"], errors="coerce")
    ma60 = close.rolling(60).mean()
    slope = (ma60.iloc[-1] / ma60.iloc[-6] - 1) * 100 if pd.notna(ma60.iloc[-6]) else None
    dist = (close.iloc[-1] / ma60.iloc[-1] - 1) * 100 if pd.notna(ma60.iloc[-1]) else None

    # 周线 KDJ：大级别底部的标志
    wk = idx.copy()
    add_kdj_weekly_to_dataframe(wk, inplace=True)
    j_raw = wk["kdj_j_weekly"].iloc[-1]
    j_week = float(j_raw) if pd.notna(j_raw) else None
    # 周线在周五收盘前是**不完整的**——周一只有 1 根 bar，此时的周 J 噪声很大。
    # 实测 2024-02-05（周一，当天正是 2635 大底）周 J 报 20.3，而那一周的完整
    # 数据算出来是 25.2。数值本身没错，但「本周才走了几天」必须让读者知道。
    last_dt = pd.to_datetime(idx["date"].iloc[-1])
    week_done = last_dt.weekday() >= 4          # 周五及以后算本周已走完

    rng = _narrow_range(idx)
    zone = amv.get("区间") if not amv.get("error") else None

    # 判定顺序：底部 > 单边 > 箱体。底部优先是因为它决定「能不能左侧建仓」，
    # 是三者里唯一可以在下跌中主动买的选择，误判代价最大。
    #
    # **阶段看指数形态，资金方向另作叠加**——两者不一致时不是「不明」，而是
    # 一个明确的状态：指数还在横盘、钱已经走了。实测 2026-09-15 就是这种：
    # 活跃市值空头（距 60 线 -21%），而上证 60 线斜率仅 -0.44% 仍在横盘。
    stage, why, playbook = "不明", [], STAGES["大级别底部"]
    lean = "flat"

    # 周 J 的值已在「读数」行里，这里只补充它的可信度信息，不重复数值
    j_note = None
    if j_week is not None and not week_done:
        weekdays = len(idx) - 1 - max(
            (i for i in range(len(idx))
             if pd.to_datetime(idx["date"].iloc[i]).weekday() >= 4), default=-1)
        j_note = (f"本周仅 {weekdays} 个交易日、周线未走完，周 J 噪声偏大"
                  f"（周五收盘后再看才可靠）")

    if j_week is not None and j_week <= BOTTOM_J:
        stage = "大级别底部"
        why.append(f"周线 J {j_week:.1f} ≤ {BOTTOM_J:.0f}（大级别超卖）")
        playbook = STAGES[stage]
    elif j_week is not None and j_week <= BOTTOM_J_NEAR:
        # 不改变阶段判定，只提示——阈值放宽会让四分之一的时间都报「底部」
        why.append(f"周线 J {j_week:.1f} 偏低（未达 ≤{BOTTOM_J:.0f} 的极值门槛，"
                   f"但历史上 2019-01、2022-10 等底部读数就在这一带）")
    elif slope is not None and abs(slope) > SLOPE_FLAT:
        stage = "单边上涨" if slope > 0 else "单边下跌"
        why.append(f"60 线斜率 {slope:+.2f}%，趋势方向明确")
        if zone:
            why.append(f"活跃市值{zone}")
        playbook = STAGES[stage]
    elif slope is not None:
        stage = "箱体震荡"
        why.append(f"60 线走平（斜率 {slope:+.2f}%）")
        if rng:
            why.append(f"近 {RANGE_WINDOW} 根区间 {rng['低']:,.0f} ~ {rng['高']:,.0f}"
                       f"（宽度 {rng['宽度']}%）"
                       + ("，窄幅" if rng["窄幅"] else "，偏宽"))
        # 箱体的方向由资金定：钱在进 → 标准高抛低吸；钱在走 → 下沿大概率破
        if zone == "空头":
            lean = "out"
            why.append("**但活跃市值空头、资金在流出——箱体偏向下破位**")
        elif zone == "多头":
            lean = "in"
            why.append("活跃市值多头，资金在流入")
        playbook = BOX_PLAYBOOK.get(lean, BOX_PLAYBOOK["out"])

    return {
        "数据日期": pd.to_datetime(idx["date"]).iloc[-1].strftime("%Y-%m-%d"),
        "阶段": stage,
        "倾向": lean,
        "打法": playbook,
        "依据": why,
        "读数": {
            "活跃市值区间": zone,
            "上证": round(float(close.iloc[-1]), 2),
            "距60线": round(dist, 2) if dist is not None else None,
            "60线斜率": round(slope, 2) if slope is not None else None,
            "周线J": round(j_week, 1) if j_week is not None else None,
            "区间宽度": rng["宽度"] if rng else None,
        },
        "周线提示": j_note,
        # 60 线斜率是**滞后**指标：等它确认转向，行情往往走完大半（实测 2024-09-24
        # 那天大涨 4.15% 启动行情，但 60 线斜率仍是 -0.58%，判成「单边下跌」）。
        # 转向的判断要靠活跃市值的当日触发，不是靠这个斜率。
        "滞后提示": ("阶段由 60 线斜率判定，天然滞后——它确认转向时行情往往已走大半。"
                     "**转向的领先信号看活跃市值**：单日 ≥+4% 且当日站上 60 日线。"),
        "口径": (f"阶段看**指数形态**（60 线斜率 ±{SLOPE_FLAT}% 内算走平），"
                 f"底部另由周线 J ≤ {BOTTOM_J:.0f} 判定——判定顺序 底部 > 单边 > 箱体，"
                 f"因为底部是唯一能在下跌中主动买的选择，误判代价最大。"
                 f"**资金方向作叠加而非并列**：箱体里资金流出与流入是两套打法，"
                 f"两者不一致不是「信号矛盾」，而是「指数还没跌、钱已经走了」这个明确状态"),
    }


def render_stage(a: dict) -> str:
    if a.get("error"):
        return f"❌ {a['error']}"
    lean_text = {"out": "（资金流出，偏向下破位）", "in": "（资金流入）"}.get(a.get("倾向"), "")
    lines = [f"# 市场阶段　{a['数据日期']}", "",
             f"**{a['阶段']}**{lean_text}", f"→ {a['打法']}", ""]
    for w in a["依据"]:
        lines.append(f"  · {w}")
    r = a["读数"]
    lines.append("")
    lines.append("　".join(f"{k} {v}" for k, v in r.items() if v is not None))
    if a.get("滞后提示"):
        lines.append(f"\n⚠ {a['滞后提示']}")
    lines.append(f"\n> {a['口径']}")
    return "\n".join(lines)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.today().strftime("%Y%m%d")
    print(render_stage(market_stage(arg)))
