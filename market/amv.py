"""活跃市值（指南针 0AMV）择时层：区间判定 + 仓位上限。

数据来自 `manual_data/0AMV.csv`（手工录入，既不走 DB 也不走 history 快照——
0AMV 是逐日累加的时间序列，塞进「每天一个横截面」的快照模型是削足适履）。

规则来源（交易系统本体，三份材料口径已对齐）：

    活跃市值.md          入场看 +4%（小波段）/ +5-8%（大波段）/ 连续 7-20%（大牛市）
                         离场看单日 ≤ -2.3%，波段大概率终结
    十分钟讲透：…        数字大小不重要，必须站上 60 日线 + MACD 白线上水，
                         否则孤零零的大阳线就是诱多
    对称交易.md          空头区间顶多 1~2 成仓；4% 以上新波段 + 上涨周期可满仓

60 日线指**活跃市值自身**的 60 日线，不是大盘的。实测佐证：2020-06-01 那天上证
已在自身 60 线上方，但《十分钟讲透》判该信号无效、要等横盘上去——只有用 0AMV
自身的 60 线才解释得通。

判据只给材料里写明的数字：空头 → 1~2 成、多头+4% 新波段 → 可满仓是原文；
变盘窗口/纠结只定性说「不重仓」（文章原话「仓位都不会很重」），不自己造阈值。

**关键约束：只能用 target 当日及之前的数据。** 0AMV 是逐日累加序列，拿未来数据
回看会让区间判定失真。这是本层特有的坑——market/ 其他层的快照本身就是时点数据，
不存在这个问题。

用法:
    python -m market.amv            # 最新状态
    python -m market.amv 20260821   # 指定日期（回看用）
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

from datas.create_database import DAILY_BAR_TABLE, DB_PATH
from indicators.macd import macd

REPO = Path(__file__).resolve().parent.parent
AMV_CSV = REPO / "manual_data" / "0AMV.csv"

MA_WINDOW = 60
SLOPE_DAYS = 5          # 60 线斜率取样窗口
BAND_PCT = 2.0          # 距 60 线 ±2% 内算变盘窗口
ENTRY_PCT = 4.0         # 主题级：跟随增量资金炒主题
MAIN_ENTRY_PCT = 8.0    # 主线级：可炒主线（源材料的 5-8% 区间上沿）
RISK_PCT = -2.3         # 波段终结风险：单日跌幅 ≤ 此值
BULL_RUN_PCT = 7.0      # 十年一牛：连续累计涨幅起点
BULL_RUN_DAYS = 3       # 连续多少日累计才算「连续」

# 分级的措辞取自源材料（4% 主题 / 8% 主题主线 / 连续 7-20% 十年一牛）
LEVEL_LABELS = (
    (MAIN_ENTRY_PCT, "主线级"),
    (ENTRY_PCT, "主题级"),
)

ZONE_BULL, ZONE_BEAR = "多头", "空头"
ZONE_TURN, ZONE_MIXED = "变盘窗口", "纠结"

POSITION_BY_ZONE = {
    ZONE_BEAR: ("1~2 成", "空头区间：再完美的票也顶多 1~2 成仓（对称交易.md）"),
    ZONE_BULL: ("正常仓位", "多头区间但当日无 ≥+4% 触发信号"),
    ZONE_TURN: ("谨慎，不重仓", "变盘窗口：方向待定（《十分钟讲透》）"),
    ZONE_MIXED: ("谨慎，不重仓", "指标不一致，方向不明"),
}
POSITION_ENTRY = ("可满仓", "多头区间 + 当日 ≥+4% 新波段（对称交易.md）")
POSITION_BULL_RUN = ("可满仓并可长期持有",
                     f"连续 {BULL_RUN_DAYS} 日以上累计 ≥{BULL_RUN_PCT:.0f}%——"
                     f"十年一牛级别，可随意布局")

CALIBER = ("60 日线与 MACD 均基于活跃市值自身序列（非大盘）；"
           "距线 2% 以内算变盘窗口；区间判定只用当日及之前的数据")


def load_amv() -> pd.DataFrame:
    """读 0AMV 序列，按日期升序。文件不存在或为空返回空 DataFrame（不抛）。"""
    if not AMV_CSV.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(AMV_CSV)
    except (OSError, pd.errors.ParserError, ValueError):
        return pd.DataFrame()
    if df.empty or "date" not in df.columns or "close" not in df.columns:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"])
    if "change_pct" in df.columns:
        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def _norm_date(target: str) -> str:
    """YYYYMMDD 或 YYYY-MM-DD 统一成 YYYY-MM-DD。"""
    t = str(target).strip()
    return f"{t[:4]}-{t[4:6]}-{t[6:8]}" if "-" not in t else t


def _trading_days_between(start: str, end: str) -> int:
    """start 之后、end 之前的交易日数。

    用个股表的 distinct date 当交易日历（`latest_trade_day()` 不认节假日，
    `market/fetch.py` 的 newhigh 层也是这么从库里反推日历的）。
    算不出来时返回 -1，调用方退化成日历日。
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                f"SELECT COUNT(DISTINCT date) FROM {DAILY_BAR_TABLE} "
                f"WHERE date > ? AND date <= ?", (start, end)).fetchone()
        return int(row[0]) if row and row[0] is not None else -1
    except sqlite3.Error:
        return -1


def _judge_zone(dist: float, above: bool, water: bool) -> str:
    """区间判定，优先级从高到低。已在文章点名的历史案例上验证。"""
    if abs(dist) < BAND_PCT:
        return ZONE_TURN
    if above and water:
        return ZONE_BULL
    if not above and not water:
        return ZONE_BEAR
    return ZONE_MIXED


def amv_timing(target: str, days: int = 10) -> dict:
    """活跃市值择时判定。返回中文键 dict，缺数据时返回 {"error": ...}。"""
    df = load_amv()
    if df.empty:
        return {"error": f"0AMV 数据不可用（{AMV_CSV} 不存在或为空）"}

    # 关键：先按 target 切片，绝不使用之后的数据
    day = _norm_date(target)
    df = df[df["date"] <= pd.Timestamp(day)]
    if len(df) < MA_WINDOW:
        return {"error": f"0AMV 在 {day} 之前只有 {len(df)} 条，不足 {MA_WINDOW} 根算 60 日线"}

    close = df["close"]
    ma60 = close.rolling(MA_WINDOW).mean()
    m = macd(close)
    dif, dea = m["macd_dif"], m["macd_dea"]

    c, m = float(close.iloc[-1]), float(ma60.iloc[-1])
    dist = (c / m - 1) * 100
    slope = (ma60.iloc[-1] / ma60.iloc[-1 - SLOPE_DAYS] - 1) * 100
    above, water = c > m, float(dif.iloc[-1]) > 0
    zone = _judge_zone(dist, above, water)

    pct = df["change_pct"].iloc[-1]
    pct = float(pct) if pd.notna(pct) else (
        (c / float(close.iloc[-2]) - 1) * 100 if len(close) > 1 else 0.0)

    # 连续累计涨幅：源材料的「十年一牛」看的是连续 7-20%，不是单日
    run_sum, run_days = 0.0, 0
    cp = df["change_pct"]
    for i in range(len(cp) - 1, -1, -1):
        v = cp.iloc[i]
        if pd.isna(v) or v <= 0:
            break
        run_sum += float(v)
        run_days += 1

    # 加速向下跳空：低开（开在前一日最低之下）**且**大跌。
    # 源材料把它与「单日流出 >2.3%」并列为两种截然不同的信号——同样是大幅下跌，
    # 普通阴跌是波段终结，跳空加速下杀反而接近底部（恐慌一步到位）。
    #
    # **实测（2026-09-17，上证 8726 根日线）**：这条只在**价格指数**、且只在
    # **短期**成立，强度也弱于源材料的措辞——
    #     大跌日中的跳空组   次日反弹胜率 61.6%（211 样本）
    #     全部大跌日         次日反弹胜率 55.9%（556 样本）
    #   3 日以上优势消失，20 日胜率与普通大跌日持平（48% vs 49%）。
    # 而在**活跃市值自身**上，跳空后是继续跌：跳空 >3% 时 20 日中位 -21%。
    # 所以报告里按源材料措辞呈现（那是使用者的系统），但别当成已证实的底部信号。
    prev_low = float(df["low"].iloc[-2]) if len(df) > 1 else None
    gap_down = (prev_low is not None and float(df["open"].iloc[-1]) < prev_low
                and pct <= RISK_PCT)

    # 当日信号
    today_signal = None
    if pct >= ENTRY_PCT:
        level = next((lbl for th, lbl in LEVEL_LABELS if pct >= th), "主题级")
        today_signal = (f"入场触发（{level} +{pct:.2f}%）"
                        + ("，站上 60 线，进攻" if above
                           else "，但未站上 60 线，疑似诱多，需站上确认"))
    elif gap_down:
        today_signal = (f"加速向下跳空（低开且 {pct:.2f}%）——"
                        f"往往是见底信号，不是恐慌信号")
    elif pct <= RISK_PCT:
        today_signal = f"波段终结风险（{pct:.2f}%）"

    # 近期信号
    recent = []
    tail = df.tail(days)
    for _, r in tail.iterrows():
        v = r.get("change_pct")
        v = float(v) if pd.notna(v) else None
        if v is None:
            continue
        if v >= ENTRY_PCT:
            recent.append({"date": r["date"].strftime("%m-%d"), "涨跌": v, "类型": "入场触发"})
        elif v <= RISK_PCT:
            recent.append({"date": r["date"].strftime("%m-%d"), "涨跌": v, "类型": "波段终结风险"})

    # 连续累计达标 → 十年一牛级别（可随意布局并长期持有）
    bull_run = (run_days >= BULL_RUN_DAYS and run_sum >= BULL_RUN_PCT)

    if bull_run:
        position, basis = POSITION_BULL_RUN
    elif zone == ZONE_BULL and pct >= ENTRY_PCT:
        position, basis = POSITION_ENTRY
    else:
        position, basis = POSITION_BY_ZONE[zone]

    data_date = df["date"].iloc[-1].strftime("%Y-%m-%d")
    # 交易日口径：按自然日算的话，长假期间会显示成落后十几天，误导判断
    lag = _trading_days_between(data_date, day)
    if lag < 0:
        lag = (pd.Timestamp(day) - df["date"].iloc[-1]).days

    return {
        "数据日期": data_date,
        "数据滞后天数": lag,
        "收盘": round(c, 2),
        "当日涨跌": round(pct, 2),
        "区间": zone,
        "距60线": round(dist, 2),
        "60线斜率": round(slope, 2),
        "白线": "上水" if water else "水下",
        "MACD": "金叉" if float(dif.iloc[-1]) > float(dea.iloc[-1]) else "死叉",
        "仓位上限": position,
        "仓位依据": basis,
        "今日信号": today_signal,
        "近期信号": recent,
        "连续上涨": {"天数": run_days, "累计": round(run_sum, 2), "达标": bull_run},
        "跳空": gap_down,
        "走势": [{"date": r["date"].strftime("%m-%d"),
                  "涨跌": round(float(r["change_pct"]), 2)}
                 for _, r in tail.iterrows() if pd.notna(r.get("change_pct"))],
        "口径": CALIBER,
    }


def render_amv(a: dict) -> str:
    """人读格式，供 __main__ 与排查使用。报告里的渲染在 analyze.render() 内。"""
    if a.get("error"):
        return f"❌ {a['error']}"
    lines = [
        f"活跃市值 {a['收盘']:,.0f}（{a['数据日期']}）　{a['区间']}　"
        f"距60线 {a['距60线']:+.2f}%　60线斜率 {a['60线斜率']:+.2f}%　"
        f"MACD {a['白线']}{a['MACD']}",
        f"仓位上限：{a['仓位上限']}　—　{a['仓位依据']}",
    ]
    if a["今日信号"]:
        lines.append(f"⚠ 当日信号：{a['今日信号']}")
    if a["近期信号"]:
        sig = "　".join(f"{s['date']} {s['涨跌']:+.2f}%（{s['类型']}）" for s in a["近期信号"])
        lines.append(f"近期信号：{sig}")
    if a["数据滞后天数"] > 0:
        lines.append(f"⚠ 0AMV 数据落后 {a['数据滞后天数']} 天（手工录入，落后是常态）")
    return "\n".join(lines)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.today().strftime("%Y%m%d")
    print(render_amv(amv_timing(arg)))
