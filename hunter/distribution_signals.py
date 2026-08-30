"""主力出货形态探测器（S1~S5 + S6 综合）。

理论来源：《主力出货的 5 种典型方式》（Z 哥 2025-09 直播完整文稿）。

文稿的三条纪律直接决定本模块的实现方式：

1. **只看量、价、位置**。「不要往上面叠 MACD、KDJ，也不要看背离——顶部只有
   一个，但背离每次上涨都有。」所以这里不用任何技术指标，唯一的均线是
   zxdkx 的白线/黄线——文稿自己用它们判断「主力还护不护盘」。
2. **假阴真阳一律当阴线**。实体（open→close）为负即阴线，不需要额外规则。
3. **宁可信其有，不可信其无**。探测宁可多报、交给下游（AI/人工）复核，
   不为压命中数收紧阈值。

五种形态与量化对应（阈值取自文稿案例实测标定，见
`.claude/skills/qk-stock-distribution/references/distribution_rules.md`）：

    S1  加速之后单日放天量大阴线      —— 归一化实体 ≤ -0.9、量创 60 日新高、前期加速
    S1变式 高位巨量大阴（量非 60 日极值）—— 实体 ≤ -0.6、量超顶部区所有阳量
    S2  加速后次高点突然巨量长阴      —— 最高点日缩量、随后 1~4 日内突然巨量长阴
    S3  新高后连续阶梯放量下跌        —— 顶部后 ≥3 根带量阴线（量 > 顶部区阳量中位 1.2 倍）
    S4  双头双放量巨阴               —— 两个高点接近、各配一根放量阴线、中间有回调
    S5  顶部绿肥红瘦 / 风车           —— 顶部区阴线量与实体同时压倒阳线
    S6  综合                         —— 同一窗口命中 ≥2 种（盘子越大越常见，不是独立探测器）

每个 detector 对「候选日 i」做判断，scan_signals 把窗口内每一天都当候选日跑一遍——
识别的是「最近一段时间内是否出现过出货特征」，而不是只看最后一天。
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from indicators.price_limit import (
    add_price_limit_to_dataframe,
    refine_limit_by_history,
)
from indicators.zxdkx import add_zxdkx_to_dataframe

# ---------------------------------------------------------------- 共同阈值（案例标定值）
# 归一化实体分级：中铁 20141222 = -1.10、光线 20250217 = -1.29 是标准 S1；
# 东财 20190226 假阴真阳只有 -0.24，靠「量大于之前所有阳量」补足——
# 所以 S1 走「实体 / 量」双轨：实体越浅，对量的要求越高。
S1_BODY_STD = -0.90        # 标准 S1 实体（倍跌停幅度）
S1_BODY_VARIANT = -0.60    # S1 变式实体下限
S1_VOL60_RATIO = 0.95      # 天量：当日量 / 前 60 日最大量
S1_TOP_UP_RATIO = 1.30     # 局部天量：当日量 / 前 10 日最大阳量（东财 2019 实测 >1）

# 加速：信号前 20 日内，任意 10 日收盘价涨幅达到该值。
# 中铁 82%、光线 >100%、民生 2013 约 32%、东财 2020 约 55%。
# 文稿中铁段：「没加速出什么货」——不满足加速的放量大阴降级，不报 S1。
ACCEL_MIN = 0.25
ACCEL_RET_DAYS = 10
ACCEL_SEARCH_DAYS = 20

# S2：最高点日必须缩量（民生 0.48、东财 0.72、宁德 0.53——
# 最高点日量 / 其前 10 日最大量），随后突然放巨量长阴。
S2_PEAK_WITHIN = 4          # 信号日距最高点日的交易日数上限
S2_PEAK_VOL_SHRINK = 0.80   # 最高点日量 / 其前 10 日最大量
S2_VOL_VS_PEAK = 1.15       # 信号日量 / 最高点日量（东财 1.24、民生 1.65、宁德 2.74）
S2_VOL_VS_PEAK_STRONG = 1.5
S2_BODY_MAX = -0.24         # 信号日实体下限（宁德 -0.249、东财 -0.41、民生 -0.55）

# S3：新高之后带量连续下跌。基准量用顶部区（最高点前 10 日，不含最高点当日）
# 阳线量的中位数——用最大值会被「天量天价」那根吃掉（民生 2025-07-10 天量阳线）。
S3_PEAK_WITHIN = 30       # 峰可以很早：民生 2025 峰 7/10、确认 8/15，相隔 26 个交易日
S3_VOL_VS_TOPUP = 1.15    # 下跌日量 / 顶部区阳量中位（万科 2018 实测 1.17~1.6）
S3_MIN_HEAVY_DOWNS = 3

# S4：双头。卫宁健康 2025 标定：头1 2025-08-08、头2 08-27，
# 各配放量阴线（实体 -0.39 / -0.36，量 1.45 / 1.87 倍均量）。
S4_WINDOW = 40
S4_HEAD_RATIO_MIN = 0.93
S4_HEAD_RATIO_MAX = 1.10
S4_VALLEY_DEPTH = 0.04      # 两头之间最低价相对头高的最小回撤
S4_MIN_GAP_DAYS = 5
S4_HEAD_BODY = -0.30
S4_HEAD_VOL_RATIO = 1.15    # 头部阴线量 / 其前 20 日均量（大盘放宽到 1.08，见下）
S4_HEAD_VOL_RATIO_BIG = 1.08  # 中信 2015 标定：4/20 头部阴 1.19、5/28 头二阴 1.46
S4_CONFIRM_WITHIN = 3       # 头2 阴线后多少日内报信号
# 大盘股（流通市值 ≥800 亿）量难放——「中信出货能给你顶部换出 30% 的一根阴线吗」，
# 头部阴线的量比门槛对大盘股放宽。
S4_BIG_CAP_YI = 800

# S5：顶部区绿肥红瘦。华谊 2013-10 标定：阴线量/阳线量 ≈ 7 倍。
# 取 1.3 是宽松下限，宁多报交 AI 复核。棕榈 2010 那种「实体未压倒」的早期雏形
# 不报，由 review 明细表交 AI 判断（见 references 的边界说明）。
S5_WINDOW = 5
S5_TOP_ZONE = 0.88          # 收盘价不低于 60 日最高价的比例才算「顶部区」
S5_VOL_RATIO = 1.30
S5_BODY_RATIO = 1.30
S5_MIN_DOWN_BARS = 2

# 信号时效分层（交易日）
AGE_HOT = 20
AGE_WATCH = 60

# 流通市值分档（亿元）：文稿「小盘单顶、中盘双头、大盘综合」
CAP_SMALL = 100
CAP_BIG = 500


@dataclass
class DistributionSignal:
    """一次出货形态命中。"""
    date: str                # 信号确认日（S3/S4/S5 是形态走完的那天）
    kind: str                # 'S1' / 'S1变式' / 'S2' / 'S3' / 'S4' / 'S5'
    grade: str               # '必走' / '至少走一半' / '稳一手'——文稿原话分级
    age: int                 # 距评估日的交易日数，0 = 评估日当天
    metrics: dict = field(default_factory=dict)


def prepare_distribution_df(
    df: pd.DataFrame,
    code: str = "",
    name: Optional[str] = None,
) -> pd.DataFrame:
    """加出货量价判定所需的全部衍生列。返回新 DataFrame，不改入参。

    新增列：z_white / z_yellow（zxdkx）、limit_pct / body_pct / body_norm /
    chg_norm（price_limit）、vol_ma20_prev、vol60max_prev、high60_prev、
    accel_prev（前 20 日内最大 10 日涨幅）、is_down（实体阴线，假阴真阳为阴线）。
    """
    d = df.sort_values("date").reset_index(drop=True).copy()

    add_zxdkx_to_dataframe(d, inplace=True)
    add_price_limit_to_dataframe(d, code=code, name=name, inplace=True)
    # 用涨跌幅分布修正 ST 区间（stock_base_info 只有当前名称，历史戴帽期靠推断）
    refined = refine_limit_by_history(d)
    changed = refined != d["limit_pct"]
    if changed.any():
        d.loc[changed, "limit_pct"] = refined[changed]
        d.loc[changed, "body_norm"] = (
            d.loc[changed, "body_pct"] / refined[changed]
        ).round(3)
        if "chg_norm" in d.columns:
            d.loc[changed, "chg_norm"] = (
                d.loc[changed, "change_pct"] / refined[changed]
            ).round(3)

    vol = d["volume"].astype(float)
    d["vol_ma20_prev"] = vol.rolling(20, min_periods=5).mean().shift(1)
    d["vol60max_prev"] = vol.rolling(60, min_periods=20).max().shift(1)
    d["high60_prev"] = d["high"].rolling(60, min_periods=20).max().shift(1)

    ret = d["close"] / d["close"].shift(ACCEL_RET_DAYS) - 1
    d["accel_prev"] = ret.shift(1).rolling(ACCEL_SEARCH_DAYS).max()

    d["is_down"] = d["body_pct"] < 0

    # 流通市值（亿元），由换手率反推。S4 对大盘股放宽量比门槛用。
    if "turnover_rate" in d.columns:
        turn = d["turnover_rate"].astype(float)
        d["cap_yi"] = (d["volume"] / turn.where(turn > 0) * 100
                       * d["close"] / 1e8)
    return d


# ---------------------------------------------------------------- 五个探测器
# 约定：入参 d 必须过了 prepare_distribution_df；i 是候选日在 d 中的行号。
# 命中返回 metrics dict（不含 kind/grade，由 scan_signals 统一打包），未命中 None。


def _detect_s1(d: pd.DataFrame, i: int) -> Optional[tuple[str, str, dict]]:
    """S1：加速之后，单日放天量大阴线。

    加速的口径：相对「前 20 日内最低收盘价」的累计涨幅，而非任意 10 日
    涨幅。一字板加速段（神车 2015-04，实体恒为 0）按 10 日窗口会漏，
    按区间最低价不会。
    """
    if i < 60:
        return None
    row = d.iloc[i]
    body = row["body_norm"]
    vol, v60 = row["volume"], row["vol60max_prev"]
    if body >= 0 or not np.isfinite(v60) or v60 <= 0:
        return None

    vol60_ratio = vol / v60
    top = d.iloc[max(0, i - 10):i]
    top_up_max = top.loc[top["body_pct"] > 0, "volume"].max()
    top_up_ratio = vol / top_up_max if top_up_max and top_up_max > 0 else np.inf

    is_sky = vol60_ratio >= S1_VOL60_RATIO
    is_local_sky = top_up_ratio >= S1_TOP_UP_RATIO
    if not (is_sky or is_local_sky):
        return None

    base = d["close"].iloc[max(0, i - ACCEL_SEARCH_DAYS):i].min()
    accel = row["close"] / base - 1 if base > 0 else 0.0
    has_accel = accel >= ACCEL_MIN
    new_high = row["high"] >= row["high60_prev"] * 0.98 if np.isfinite(row["high60_prev"]) else False

    metrics = {
        "body_norm": round(float(body), 2),
        "vol60_ratio": round(float(vol60_ratio), 2),
        "vol_vs_top_up": round(float(top_up_ratio), 2),
        "accel_from_low_pct": round(float(accel) * 100, 1),
    }

    # 标准 S1：实体、天量、加速三条件齐（文稿：三个条件要都满足）
    if body <= S1_BODY_STD and is_sky and (has_accel or new_high):
        return "S1", "必走", metrics
    # S1 变式：实体稍浅但量压过顶部所有阳量，且位置在高位
    # （东财 2019「创新高，量大于之前所有的阳量」、中铁 20150608「对这个高点来讲是放量」）
    if body <= S1_BODY_VARIANT and is_local_sky and (has_accel or new_high):
        return "S1变式", "必走", metrics
    # 量够、实体够，但没有加速——文稿说这种多半是试盘不是出货，降级
    if body <= S1_BODY_VARIANT:
        return "S1变式", "稳一手", {**metrics, "note": "无加速段，存疑（可能是试盘）"}
    return None


def _detect_s2(d: pd.DataFrame, i: int) -> Optional[tuple[str, str, dict]]:
    """S2：加速之后，次高点突然巨量长阴。

    与 S1 的差别在位置（次高点而非最高点）与量能基准（相对最高点日）。
    文稿明说不要求加速（宁德 20211207：「不太符合加速之后，但符合次高点
    突然巨量长阴」），所以加速只用于分级，不做门槛。
    """
    if i < 60:
        return None
    row = d.iloc[i]
    if row["body_norm"] >= S2_BODY_MAX:
        return None

    # 最高点日：前 1~4 个交易日内 high 最高、且本身是近期新高的那天
    lo = max(1, i - S2_PEAK_WITHIN)
    window = d.iloc[lo:i]
    if window.empty:
        return None
    p = window["high"].idxmax()
    peak = d.loc[p]
    if not np.isfinite(peak["high60_prev"]) or peak["high"] < peak["high60_prev"] * 0.97:
        return None
    # 最高点日必须缩量——文稿：「前一日（最高点）是缩量的，甚至没有放量」
    prior_max = d["volume"].iloc[max(0, p - 10):p].max()
    if not prior_max or peak["volume"] > prior_max * S2_PEAK_VOL_SHRINK:
        return None

    vol_vs_peak = row["volume"] / peak["volume"]
    if vol_vs_peak < S2_VOL_VS_PEAK:
        return None
    # 收盘价必须已经掉下来（次高点，不是又创新高）
    if row["close"] >= peak["high"]:
        return None

    accel_base = d["close"].iloc[max(0, i - ACCEL_SEARCH_DAYS):i].min()
    accel = row["close"] / accel_base - 1 if accel_base > 0 else 0.0
    metrics = {
        "body_norm": round(float(row["body_norm"]), 2),
        "vol_vs_peak_day": round(float(vol_vs_peak), 2),
        "peak_date": str(peak["date"])[:10],
        "peak_shrink": round(float(peak["volume"] / prior_max), 2),
        "accel_from_low_pct": round(float(accel) * 100, 1),
    }
    grade = "必走" if (vol_vs_peak >= S2_VOL_VS_PEAK_STRONG
                       or row["body_norm"] <= -0.4) else "至少走一半"
    return "S2", grade, metrics


def _detect_s3(d: pd.DataFrame, i: int) -> Optional[tuple[str, str, dict]]:
    """S3：新高之后，连续阶梯放量下跌。

    「阶梯」指量价：下跌日一根比一根带量、且每根都压过顶部区的阳线量。
    民生 2025-07~08 标定：顶部区阳量中位 263M，下跌日 346~440M（1.3~1.7 倍）。

    最高点的选取：直接取回溯窗内 high 最高的那根。窗口要长（30 个交易日）——
    民生 2025 的顶在 7/10，形态确认在 8/15，相隔 26 个交易日，窗口短了会把
    下跌中继的小反弹高点误当顶部。防线用「价格在推进下行」补：末日收盘必须
    低于峰后首日，否则只是高位横盘震荡、不是阶梯出货。
    """
    if i < 60:
        return None
    lo = max(1, i - S3_PEAK_WITHIN)
    window = d.iloc[lo:i + 1]
    p = window["high"].idxmax()
    if p >= i - 2:  # 峰太近，还没有「连续下跌」可言
        return None
    peak = d.loc[p]
    if not np.isfinite(peak["high60_prev"]) or peak["high"] < peak["high60_prev"] * 0.97:
        return None

    # 顶部区基准量：峰前 10 日阳线量的中位数。用中位数而不用最大值——
    # 最大值会被「天量天价」那根吃掉（民生 7/10 峰日自身就是 600M 阳线）。
    top_zone = d.iloc[max(0, p - 10):p]
    up_vols = top_zone.loc[top_zone["body_pct"] > 0, "volume"]
    if up_vols.empty:
        return None
    top_up_med = up_vols.median()
    if top_up_med <= 0:
        return None

    downs = d.iloc[p + 1:i + 1]
    downs = downs[downs["is_down"]]
    heavy = downs[downs["volume"] >= top_up_med * S3_VOL_VS_TOPUP]
    if len(heavy) < S3_MIN_HEAVY_DOWNS:
        return None

    # 价格必须确实下来了，且仍在下行（末日收盘低于峰后首日），
    # 否则只是高位横盘震荡，不是出货
    row = d.iloc[i]
    drop_from_peak = row["close"] / peak["high"] - 1
    if drop_from_peak > -0.03 or row["close"] >= d.at[p + 1, "close"]:
        return None

    # 带量破位情况：文稿「破白线就得卖」「放量又跌破黄线」
    break_white = bool(((downs["close"] < downs["z_white"])
                        & (downs["volume"] >= top_up_med * S3_VOL_VS_TOPUP)).any())
    break_yellow = bool(((downs["close"] < downs["z_yellow"])
                         & (downs["volume"] >= top_up_med * S3_VOL_VS_TOPUP)).any())

    metrics = {
        "heavy_down_days": int(len(heavy)),
        "peak_date": str(peak["date"])[:10],
        "drop_from_peak_pct": round(float(drop_from_peak) * 100, 1),
        "vol_vs_top_up_med": round(float(heavy["volume"].iloc[-1] / top_up_med), 2),
        "break_white": break_white,
        "break_yellow": break_yellow,
    }
    grade = "必走" if break_yellow else ("至少走一半" if break_white else "稳一手")
    return "S3", grade, metrics


def _detect_s4(d: pd.DataFrame, i: int) -> Optional[tuple[str, str, dict]]:
    """S4：双头双放量巨阴。中盘股一根出不完的典型走法。

    头用「放量阴线」锚定，而不是用价格局部极值锚定——卫宁健康 2025 标定：
    价格头在 8/1（11.52），出货阴在 8/8（-7.83%），两者差 5 个交易日。
    先找两根放量阴线，头高取阴线前后 ±3 日内的最高价。
    """
    if i < 60:
        return None
    lo = max(2, i - S4_WINDOW)
    seg = d.iloc[lo:i + 1]

    # 大盘股量难放，头部阴线量比门槛放宽
    cap = d["cap_yi"].iloc[i] if "cap_yi" in d.columns else np.nan
    vol_ratio_need = (S4_HEAD_VOL_RATIO_BIG
                      if np.isfinite(cap) and cap >= S4_BIG_CAP_YI
                      else S4_HEAD_VOL_RATIO)

    bars = seg[(seg["is_down"])
               & (seg["body_norm"] <= S4_HEAD_BODY)
               & (seg["volume"] >= seg["vol_ma20_prev"] * vol_ratio_need)]
    if len(bars) < 2:
        return None

    # 头2 是最近的放量阴线，且必须在确认窗口内（否则是旧信号）
    b2 = bars.index[-1]
    if i - b2 > S4_CONFIRM_WITHIN:
        return None

    def head_high(bar_idx: int) -> float:
        return d["high"].iloc[max(0, bar_idx - 3):bar_idx + 2].max()

    h2 = head_high(b2)
    # 头1：在头2 之前间隔足够、头高接近的放量阴线，取最近且最高的那个
    best = None
    for b1 in bars.index[:-1]:
        if b2 - b1 < S4_MIN_GAP_DAYS:
            continue
        h1 = head_high(b1)
        if S4_HEAD_RATIO_MIN <= h2 / h1 <= S4_HEAD_RATIO_MAX:
            if best is None or h1 > best[1]:
                best = (b1, h1)
    if best is None:
        return None
    b1, h1 = best

    valley = d["low"].iloc[b1:b2 + 1].min()
    if valley > min(h1, h2) * (1 - S4_VALLEY_DEPTH):
        return None

    def bar_info(b):
        r = d.loc[b]
        return {"date": str(r["date"])[:10],
                "body_norm": round(float(r["body_norm"]), 2),
                "vol_ratio": round(float(r["volume"] / r["vol_ma20_prev"]), 2)}

    return "S4", "必走", {
        "head1": bar_info(b1),
        "head2": bar_info(b2),
        "head2_vs_head1": round(float(h2 / h1), 3),
        "valley_depth_pct": round(float(valley / min(h1, h2) - 1) * 100, 1),
        "big_cap_relaxed": bool(vol_ratio_need == S4_HEAD_VOL_RATIO_BIG),
    }


def _detect_s5(d: pd.DataFrame, i: int) -> Optional[tuple[str, str, dict]]:
    """S5：顶部绿肥红瘦（阴线量与实体同时压倒阳线），含顶部风车变体。"""
    if i < 60:
        return None
    row = d.iloc[i]
    high60 = d["high"].iloc[:i + 1].max()
    if row["close"] < high60 * S5_TOP_ZONE:
        return None

    seg = d.iloc[i - S5_WINDOW + 1:i + 1]
    downs = seg[seg["is_down"]]
    ups = seg[~seg["is_down"]]
    if len(downs) < S5_MIN_DOWN_BARS or ups.empty:
        return None

    vol_ratio = downs["volume"].sum() / ups["volume"].sum()
    body_ratio = (downs["body_pct"].abs().sum()
                  / max(ups["body_pct"].sum(), 1e-9))
    if vol_ratio < S5_VOL_RATIO or body_ratio < S5_BODY_RATIO:
        return None

    metrics = {
        "down_up_vol_ratio": round(float(vol_ratio), 2),
        "down_up_body_ratio": round(float(body_ratio), 2),
        "down_bars": int(len(downs)),
        "window": S5_WINDOW,
    }
    # 窗口内含巨阴 → 不只是「慢慢出」
    if (downs["body_norm"] <= S1_BODY_VARIANT).any():
        return "S5", "必走", metrics
    return "S5", "至少走一半", metrics


_DETECTORS = (_detect_s1, _detect_s2, _detect_s3, _detect_s4, _detect_s5)


# ---------------------------------------------------------------- 扫描与汇总

def scan_signals(
    df: pd.DataFrame,
    code: str = "",
    name: Optional[str] = None,
    lookback: Optional[int] = AGE_WATCH,
) -> list[DistributionSignal]:
    """逐日扫描，返回窗口内全部出货信号（按日期升序）。

    Args:
        df: 原始日线（无需预先加指标），按 date 排序与否均可。
        lookback: 只扫最后 N 个交易日；None = 全部历史（复盘用）。
    """
    d = prepare_distribution_df(df, code=code, name=name)
    n = len(d)
    start = 60 if lookback is None else max(60, n - lookback)

    signals: list[DistributionSignal] = []
    for i in range(start, n):
        for detect in _DETECTORS:
            hit = detect(d, i)
            if hit is None:
                continue
            kind, grade, metrics = hit
            signals.append(DistributionSignal(
                date=str(d.at[i, "date"])[:10],
                kind=kind,
                grade=grade,
                age=n - 1 - i,
                metrics=metrics,
            ))
    return signals


def float_cap_yi(df: pd.DataFrame) -> Optional[float]:
    """流通市值（亿元），由换手率反推：volume / turnover_rate% × close。"""
    row = df.iloc[-1]
    turn = row.get("turnover_rate")
    if not turn or turn <= 0:
        return None
    return round(float(row["volume"] / (turn / 100) * row["close"] / 1e8), 1)


def cap_tier(cap_yi: Optional[float]) -> str:
    """文稿分档：小盘单顶、中盘双头、大盘综合（出货方式随盘子变复杂）。"""
    if cap_yi is None:
        return "未知"
    if cap_yi < CAP_SMALL:
        return "小盘"
    if cap_yi < CAP_BIG:
        return "中盘"
    return "大盘"


def summarize(
    signals: list[DistributionSignal],
    df: Optional[pd.DataFrame] = None,
) -> Optional[dict]:
    """把逐日信号汇总成一股一行的结论。

    分层逻辑：
      时效 —— 最新信号 age ≤20 交易日为「高危」，≤60 为「观察」，更早忽略；
      严重度 —— 取窗口内最重的一档（必走 > 至少走一半 > 稳一手）；
      S6 综合 —— 高危窗口内命中 ≥2 种形态时置 composite=True（文稿第六条：
      盘子越大出货方式越综合，复合头部本身就是危险信号）；
      换庄豁免 —— 信号日之后出现「更大量 + 收盘站上信号日高点」，说明有新资金
      把货接走了（中铁 2014 案例），旧信号降级为失效。
    """
    if not signals:
        return None

    fresh = [s for s in signals if s.age <= AGE_WATCH]
    if not fresh:
        return None

    grade_rank = {"必走": 3, "至少走一半": 2, "稳一手": 1}
    worst = max(fresh, key=lambda s: grade_rank[s.grade])
    newest_age = min(s.age for s in fresh)
    hot = [s for s in fresh if s.age <= AGE_HOT]
    kinds = sorted({s.kind for s in fresh})

    invalidated = False
    if df is not None and newest_age > 0:
        d = df.sort_values("date").reset_index(drop=True)
        sig = min(fresh, key=lambda s: s.age)
        sig_idx = d.index[d["date"].astype(str).str[:10] == sig.date]
        if len(sig_idx):
            after = d.iloc[sig_idx[0] + 1:]
            sig_high = d.at[sig_idx[0], "high"]
            sig_vol = d.at[sig_idx[0], "volume"]
            if not after.empty:
                stronger = after[(after["close"] > sig_high * 1.02)
                                 & (after["volume"] > sig_vol)]
                invalidated = not stronger.empty

    return {
        "verdict": worst.grade,
        "tier": "高危" if newest_age <= AGE_HOT else "观察",
        "newest_age": int(newest_age),
        "kinds": kinds,
        "composite": len({s.kind for s in hot}) >= 2,
        "invalidated": invalidated,
        "signal_count": len(fresh),
        "signals": fresh,
    }
