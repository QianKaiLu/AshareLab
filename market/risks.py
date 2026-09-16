"""风险信号扫描：市场层面的「躲大跌清单」。

对应交易系统里那张五项清单（`reference_articles/modoo/大富翁交易系统全景总结.md` 第六节）：

    1. 活跃市值流出 >2.3%      上涨波段大概率终结   → 已在 market/amv.py，本模块不重复
    2. 加速段破位              加速段终结           → platform_breakdown()
    3. 大级别顶背离            买盘不足，将回落      → bearish_divergence()
    4. MACD「金叉空」          该上穿没上穿反向下    → macd_failed_cross()
    5. 奇怪的放量阴线          主力出货             → volume_spike_yin()

判断对象是**指数**（上证 / 沪深300 / 活跃市值），不是个股——个股层面
`hunter/distribution_signals.py` 已有 S1-S5 那一套。

**这里的阈值都是起点参照，不是硬规则。** 形态识别没有唯一解，参数换个值结论就可能
翻转，所以每条信号都返回触发依据（数值），由人复核，而不是只给一个 true/false。

用法:
    python -m market.risks [YYYYMMDD]
"""
from __future__ import annotations

import sys
from typing import Optional

import pandas as pd

from datas.query_stock import query_index_bars
from indicators.macd import macd
from market.amv import load_amv
from tools.log import get_analyze_logger

logger = get_analyze_logger()

# ---- 顶背离
SWING_K = 5             # 摆动高点的判定窗口：比前后各 K 根都高
DIV_LOOKBACK = 120      # 在最近多少根里找摆动高点
DIV_RECENT = 40         # 后一个高点必须在这个范围内才算「当前有效」

# ---- 平台破位
PLATFORM_MIN = 10       # 平台至少多少根
PLATFORM_MAX = 30       # 平台最多多少根
PLATFORM_RANGE = 0.06   # 平台内 (最高-最低)/均线 小于此值算窄幅横盘
BREAK_YIN = -1.5        # 跌破当日跌幅小于此值（%）才算「大阴线」而不是阴跌

# ---- 放量阴线
YIN_PCT = -2.0          # 当日跌幅
YIN_VOL_RATIO = 1.5     # 相对 5 日均量的放量倍数

# ---- MACD 金叉空
FAILED_CROSS_LOOKBACK = 15   # 在最近多少根里找「接近上穿但没上穿」
FAILED_CROSS_GAP = 0.15      # 差值收敛到 DIF 的多少比例以内算「接近上穿」


def _ma(s: pd.Series, n: int) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").rolling(n).mean()


def _swing_highs(close: pd.Series, k: int = SWING_K) -> list[int]:
    """局部高点索引：该点比前后各 k 根都高（且唯一最高）。"""
    out = []
    for i in range(k, len(close) - k):
        w = close.iloc[i - k:i + k + 1]
        if close.iloc[i] == w.max() and int((w == close.iloc[i]).sum()) == 1:
            out.append(i)
    return out


def bearish_divergence(close: pd.Series, dif: pd.Series) -> Optional[dict]:
    """顶背离：最近两个摆动高点，价格后高但 DIF 后低。

    含义是「股价创新高而 MACD 不创新高」——买盘不足。只取最近两个高点，
    且后一个必须够近（DIV_RECENT 内），否则老背离早失效了。
    """
    sub, d = close.tail(DIV_LOOKBACK).reset_index(drop=True), dif.tail(DIV_LOOKBACK).reset_index(drop=True)
    highs = _swing_highs(sub)
    if len(highs) < 2:
        return None
    i, j = highs[-2], highs[-1]
    if len(sub) - 1 - j > DIV_RECENT:
        return None                                  # 后一个高点太久远
    if sub.iloc[j] <= sub.iloc[i] or d.iloc[j] >= d.iloc[i]:
        return None
    # 背离后若已跌破前一个高点之前的低点，形态已被证伪，不再算数
    return {
        "信号": "顶背离",
        "前高": f"{sub.iloc[i]:,.2f}（DIF {d.iloc[i]:,.2f}）",
        "后高": f"{sub.iloc[j]:,.2f}（DIF {d.iloc[j]:,.2f}）",
        "距今": len(sub) - 1 - j,
        "说明": "价格创新高而 MACD 未创新高，买盘不足——顶背离后的反拉是减仓点",
    }


def platform_breakdown(close: pd.Series, pct: pd.Series) -> Optional[dict]:
    """加速段破位：先有一段加速，再横盘成平台，最后被大阴线跌破平台下沿。

    简化实现：在最近 PLATFORM_MAX 根里找一段满足「窄幅」的窗口当平台，
    看最新一根是否以大阴线跌破它。**不回溯验证前面是否真有加速段**——
    参数一多，误报就会盖过真信号。
    """
    n = len(close)
    if n < PLATFORM_MAX + 2:
        return None
    for w in range(PLATFORM_MAX, PLATFORM_MIN - 1, -1):
        plat = close.iloc[-(w + 1):-1]               # 不含最新一根
        if len(plat) < PLATFORM_MIN:
            continue
        mid = plat.mean()
        if mid <= 0 or (plat.max() - plat.min()) / mid > PLATFORM_RANGE:
            continue                                 # 不够窄，不是平台
        low = plat.min()
        last, chg = close.iloc[-1], pct.iloc[-1]
        if pd.isna(chg) or last >= low:
            continue                                 # 没破位
        if chg > BREAK_YIN and last > low * 0.98:
            continue                                 # 破得不干脆：阴跌不算破位
        return {
            "信号": "平台破位",
            "平台": f"{w} 根，区间 {plat.min():,.2f} ~ {plat.max():,.2f}"
                    f"（幅度 {(plat.max() - plat.min()) / mid * 100:.1f}%）",
            "破位": f"收 {last:,.2f}，跌破下沿 {low:,.2f}（{(last / low - 1) * 100:+.2f}%），"
                    f"当日 {chg:+.2f}%",
            "说明": "横盘平台被大阴线跌破，加速段终结",
        }
    return None


def volume_spike_yin(close: pd.Series, pct: pd.Series, volume: pd.Series) -> Optional[dict]:
    """奇怪的放量阴线：跌幅够深 + 量能放大。"""
    if len(close) < 6:
        return None
    last_pct = pct.iloc[-1]
    if pd.isna(last_pct) or last_pct > YIN_PCT:
        return None
    base = volume.iloc[-6:-1].mean()
    if not base or pd.isna(base):
        return None
    ratio = float(volume.iloc[-1]) / float(base)
    if ratio < YIN_VOL_RATIO:
        return None
    return {
        "信号": "放量阴线",
        "读数": f"当日 {last_pct:+.2f}%，量为前 5 日均量的 {ratio:.2f} 倍",
        "说明": "放量阴线当天不抄底，等次日下穿动作确认",
    }


def macd_failed_cross(dif: pd.Series, dea: pd.Series) -> Optional[dict]:
    """MACD「金叉空」：DIF 曾经逼近 DEA（看起来要上穿），没穿过去反而向下扩大。"""
    if len(dif) < FAILED_CROSS_LOOKBACK + 2:
        return None
    gap = (dif - dea).tail(FAILED_CROSS_LOOKBACK + 1)
    if gap.iloc[-1] >= 0:
        return None                                  # 现在就在上方，不适用
    scale = float(dif.tail(FAILED_CROSS_LOOKBACK).abs().mean()) or 1.0
    near = gap / scale
    best_i = near.abs().idxmin()
    if near.loc[best_i] > FAILED_CROSS_GAP:          # 从没靠近过，谈不上「该上穿」
        return None
    if gap.loc[best_i] >= 0:
        return None                                  # 靠近时已在零轴上方，不是「金叉空」
    if abs(gap.iloc[-1]) <= abs(gap.loc[best_i]):
        return None                                  # 没往下扩大
    return {
        "信号": "MACD 金叉空",
        "读数": f"DIF−DEA 最接近 {gap.loc[best_i]:+.2f}（{FAILED_CROSS_LOOKBACK} 根内），"
                f"现 {gap.iloc[-1]:+.2f} 反而向下扩大",
        "说明": "该上穿没上穿反向下，转弱信号",
    }


def scan_series(name: str, df: pd.DataFrame) -> dict:
    """对一条日线序列跑全部信号。df 需含 date/open/high/low/close/volume。"""
    if df is None or df.empty or len(df) < PLATFORM_MAX + 5:
        return {"名称": name, "error": "数据不足"}

    close = pd.to_numeric(df["close"], errors="coerce")
    pct = close.pct_change() * 100
    m = macd(close)

    # 活跃市值没有成交量（它是市值量纲），缺 volume 列时跳过需要量能的信号
    hits = [h for h in (
        bearish_divergence(close, m["macd_dif"]),
        platform_breakdown(close, pct),
        (volume_spike_yin(close, pct, pd.to_numeric(df["volume"], errors="coerce"))
         if "volume" in df.columns else None),
        macd_failed_cross(m["macd_dif"], m["macd_dea"]),
    ) if h]
    return {
        "名称": name,
        "数据日期": pd.to_datetime(df["date"]).iloc[-1].strftime("%Y-%m-%d"),
        "收盘": round(float(close.iloc[-1]), 2),
        "触发": hits,
    }


def market_risks(target: str) -> dict:
    """对上证、沪深300、活跃市值分别扫描风险信号。"""
    day = target
    out = []
    for name, symbol in (("上证指数", "sh000001"), ("沪深300", "sh000300")):
        df = query_index_bars(symbol, to_date=day)
        if df.empty:
            continue
        out.append(scan_series(name, df.tail(260).reset_index(drop=True)))

    amv = load_amv()
    if not amv.empty:
        sub = amv[amv["date"] <= pd.Timestamp(
            f"{day[:4]}-{day[4:6]}-{day[6:8]}" if "-" not in day else day)].tail(260)
        if not sub.empty:
            out.append(scan_series("活跃市值", sub.reset_index(drop=True)))

    total = sum(len(s.get("触发") or []) for s in out)
    return {
        "数据日期": day,
        "扫描": out,
        "触发总数": total,
        "口径": ("判断对象是指数不是个股（个股层面 hunter/distribution_signals.py 已有 S1-S5）；"
                 "阈值都是起点参照不是硬规则，形态识别换个参数结论就可能翻转，"
                 "所以每条都返回数值依据供复核"),
    }


def render_risks(a: dict) -> str:
    if a.get("error"):
        return f"❌ {a['error']}"
    lines = [f"# 风险信号扫描　{a['数据日期']}　触发 {a['触发总数']} 条", ""]
    for s in a["扫描"]:
        if s.get("error"):
            lines.append(f"{s['名称']}: {s['error']}")
            continue
        hits = s.get("触发") or []
        lines.append(f"**{s['名称']}**（{s['数据日期']} 收 {s['收盘']:,.2f}）"
                     + (f"　触发 {len(hits)} 条" if hits else "　无触发"))
        for h in hits:
            lines.append(f"  · {h['信号']}：{h.get('读数') or h.get('破位') or ''}")
            if h.get("说明"):
                lines.append(f"    {h['说明']}")
        lines.append("")
    lines.append(f"> {a['口径']}")
    return "\n".join(lines)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.today().strftime("%Y%m%d")
    print(render_risks(market_risks(arg)))
