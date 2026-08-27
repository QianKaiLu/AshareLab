"""B1 策略：放量启动后缩量回踩。

理论来源：《B1 十张图》（life_kernel/trading_system/reference_articles/B1十张图.pdf）。
文档把 B1 买点分成四类「完美」图形，四类的核心逻辑一致——
「放量启动 → 顶部无量 → 缩量至地量 → 小阴小阳企稳」——
差异只在洗盘方式、指标精准度、以及股价所处位置：

    完美一  标准缩量回调，指标精准（J 勾到 13 以下、极致缩量）
    完美二  变量型洗盘，时间换空间，指标模糊（文档原文「无需追求指标绝对精准」）
    完美三  异动后箱体横盘 + 红肥绿瘦 + 高控盘
    完美四  高位缩量上涨 + 顶部无量，激进试错（前期已有大涨幅是特征而非缺陷）

所以本模块不是一条 AND 链，而是三个 variant 各自定 strictness、彼此 OR：
命中结果里的 `variant` 字段标明是哪一类，便于后续人工/AI 复筛。
（完美三无需独立分支，它在 STRICT 下即可通过。）

共同硬条件取自文档第 11-12 页的显式清单：
    当日涨幅 ∈ [-2%, +1.8%]、当日振幅 ≤ 7%、白线 > 黄线、量能缩至相对低位。

判定流程：

    A. 共同末日形态 —— 涨跌幅、振幅、白/黄关系
    B. variant 门槛 —— J 值上限与是否容许 J 仍在下行
    C. 位置限制     —— 近 60 日未翻倍（完美四豁免）
    D. 点火识别     —— 近 30 日内倒序搜索放量拉升段，逐个候选试下游
    E. 顶部无量     —— 价格高点不能同时是成交量高点（否则是放量滞涨/出货）
    F. 缩量回踩     —— 近两日缩量、无放量大阴线、红肥绿瘦
    G. 回踩位置     —— 现价处于点火区间下半部分
"""
from dataclasses import dataclass
from typing import Iterator, Optional

import pandas as pd

from hunter.hunt_machine import HuntInput, HuntInputLike, HuntMachine, HuntResult
from indicators.kdj import add_kdj_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe
from tools.log import get_analyze_logger

logger = get_analyze_logger()

# ---------------------------------------------------------------- 共同硬条件（文档明列）
# 「当日涨幅处于 -2% 到 1.8% 范围内」——小阴小阳企稳，涨太多说明已启动，跌太多说明还在杀跌
MIN_DOWN_PCT = -0.02
MAX_UP_PCT = 0.018
# 「当日振幅在 7% 以内」。文档自己的完美四案例（昂利康 20250711）振幅 7.02%，
# 略高于其声称的 7%，所以这里留 0.5pp 的舍入余量，否则文档案例会被自己的规则排除。
MAX_AMPLITUDE_PCT = 7.5
# 「白线（短期均线）大于黄线（长期均线）」。文档原文是严格大于，
# 不再沿用旧代码 white >= yellow * 0.99 的放宽。
# 收盘价则允许略微跌破黄线：文档明确「跌破黄线后快速收回」是强支撑信号。
CLOSE_YELLOW_TOLERANCE = 0.99

# ---------------------------------------------------------------- 位置限制
# 近 N 日最高/最低价之比达到此倍数即视为高位（完美四豁免此条）
HIGH_POSITION_LOOKBACK = 60
HIGH_POSITION_RATIO = 1.0

# ---------------------------------------------------------------- 点火识别
# 在最近 N 个交易日内倒序搜索点火段
SEARCH_WINDOW = 30
# 点火段最长天数
IGNITION_MAX_DAYS = 7
# 累计涨幅门槛随天数线性递增：base + per_day * (days - 1)。
# 旧版是 7 档 21 个手写数字，其中 6 天与 5 天门槛相同、放量倍数只取 1.8/2.0 两值,
# 自由度远超实际需要；这条直线在 1~7 天上与旧档位基本重合，参数从 21 个降到 3 个。
IGNITION_BASE_PCT = 0.04
IGNITION_PCT_PER_DAY = 0.026
# 点火期均量相对点火前盘整均量的倍数下限
IGNITION_VOL_MULTIPLE = 1.8
# 点火前用于计算盘整均量的天数
CONSOLIDATION_DAYS = 5

# ---------------------------------------------------------------- 顶部无量
# 点火结束之后出现的最大成交量，相对点火期最大量的上限。
# 文档的链条是「放量启动 → 顶部无量 → 缩量至地量」：启动那波必须是量能峰值，
# 之后若再冒出同等量能，说明是放量滞涨/主力出货，而非蓄势。
# 注意衡量对象是点火期「之后」的 K 线——若含点火期本身，价格高点通常就是
# 点火放量那根，比值恒接近 1，条件会与放量启动形态自相矛盾。
#
# 阈值取 1.3 而非 1.0：文档对方正科技（乔丹）的描述是「启动后缩量杀跌两波」，
# 两波之间的反弹量能可以略超启动波峰值（该案例实测 1.12），仍属同一量级。
# 真正要挡的是数倍于启动波的放量出货。
TOP_VOL_RATIO_MAX = 1.3

# ---------------------------------------------------------------- 缩量回踩
# 最近两日成交量相对点火期最大量的上限。
# 旧版对相邻两天用 0.35 / 0.45 两个不同精确值，无形态学依据，合并为一个。
PULLBACK_VOL_RATIO_MAX = 0.45
# 「放量大阴线」判定：跌幅达到区间内最大波动的此比例，且量能超过基准量的此倍数
BIG_DOWN_CHANGE_RATIO = 0.4
BIG_DOWN_VOL_RATIO = 1.1
# 红肥绿瘦：阳线量 / 阴线量的下限，以及参与比较的最大量 K 线根数
VOL_RATIO_THRESHOLD = 1.2
TOP_VOL_BARS = 3
# 「缩量回调」判定：点火后所有阴线量均低于点火期最大量的此比例
VOL_SHRINK_THRESHOLD = 0.6

# ---------------------------------------------------------------- 回踩位置
# 现价在点火区间内的相对位置上限（0=区间底部，1=区间顶部）
MAX_POS_IN_RANGE = 0.5
# 完美四是「缩量上涨」，股价本就贴着区间上沿运行，不适用回调位置限制
HIGH_POS_MAX_POS_IN_RANGE = 1.0

# 止损位选择：收盘价与黄线的距离超过此比例时，改用白线做止损。
# 文档对昂利康的风控原话是「因股价与黄线距离远，需以跌破白线为止损点」。
FAR_FROM_YELLOW_PCT = 0.15


@dataclass(frozen=True)
class Variant:
    """一类「完美」图形的 strictness 设定。

    只保留文档明确指出有差异的三项；其余判定全 variant 共用。
    """
    name: str
    # J 值上限
    kdj_max: float
    # 是否豁免「近 60 日未翻倍」。完美四专打高位高控盘票，
    # 文档称「4500 点以上此类图形增多」，前期大涨幅是该形态的前提。
    allow_high_position: bool
    # 现价在点火区间内的位置上限。完美一/二/三是「缩量回调」，要求落在下半部分；
    # 完美四是「缩量上涨」，股价贴着高位走，若也要求 ≤0.5 就与其定义互斥——
    # 这也正是文档单独为它讲止损（离黄线远、改用白线）的原因。
    max_pos_in_range: float


# J 勾到 13 以下（文档「勾到大幅值（13 以下）」）
KDJ_STRICT = 13.0
# 完美二的模糊区间。文档明写野马电池「勾到大幅值为 13.72（未严格达 13 以下），
# 属于模糊认定买点」，所以上限取到 16 覆盖这类案例。
KDJ_FUZZY = 16.0
# 完美四不强调 J 值精准度，只要不在高位钝化即可
KDJ_HIGH_POS = 20.0

VARIANTS = (
    Variant("完美一", kdj_max=KDJ_STRICT, allow_high_position=False,
            max_pos_in_range=MAX_POS_IN_RANGE),
    Variant("完美二", kdj_max=KDJ_FUZZY, allow_high_position=False,
            max_pos_in_range=MAX_POS_IN_RANGE),
    Variant("完美四", kdj_max=KDJ_HIGH_POS, allow_high_position=True,
            max_pos_in_range=HIGH_POS_MAX_POS_IN_RANGE),
)


@dataclass
class Ignition:
    """一段被识别出的放量拉升。"""
    start_idx: int          # 点火首日在 df 中的位置
    date: object            # 点火首日日期
    days: int               # 持续天数
    acc_pct: float          # 累计涨幅
    support_price: float    # 点火首日最低价，作为支撑参考
    max_volume: float       # 点火期内阳线最大成交量
    mean_volume: float      # 点火期内平均成交量
    max_change_pct: float   # 点火期内最大单日实体波动


def _find_big_down_bar(segment: pd.DataFrame, max_change_pct: float,
                       max_volume: float) -> bool:
    """区间内是否存在放量大阴线。

    三个条件同时成立才算：收阴、跌幅占区间最大波动的比例够高、成交量超过基准量。
    放量大阴线意味着主力出货，是形态被破坏的信号。
    """
    if max_change_pct <= 0 or max_volume <= 0:
        return False
    change_pct = segment['_pct_change_oc']
    change_ratio = change_pct.abs() / max_change_pct
    vol_ratio = segment['volume'] / max_volume
    return bool((
        (change_pct < 0)
        & (change_ratio > BIG_DOWN_CHANGE_RATIO)
        & (vol_ratio > BIG_DOWN_VOL_RATIO)
    ).any())


def _check_common_last_bar(df: pd.DataFrame) -> Optional[dict]:
    """阶段 A：文档明列的共同硬条件——涨跌幅、振幅、白/黄关系。"""
    last_row, prev_row = df.iloc[-1], df.iloc[-2]

    price_change_pct = (last_row["close"] / prev_row["close"]) - 1
    if not MIN_DOWN_PCT <= price_change_pct <= MAX_UP_PCT:
        return None

    amplitude = last_row.get("amplitude")
    if pd.notna(amplitude) and amplitude > MAX_AMPLITUDE_PCT:
        return None

    close, white, yellow = last_row["close"], last_row["z_white"], last_row["z_yellow"]
    if yellow <= 0:
        return None
    # 白线必须在黄线上方（文档条件 5）
    if white <= yellow:
        return None
    # 收盘价容许略微跌破黄线——文档视「跌破后快速收回」为强支撑
    if close < yellow * CLOSE_YELLOW_TOLERANCE:
        return None

    return {
        "price_change_pct": round(price_change_pct * 100, 2),
        "amplitude_pct": round(float(amplitude), 2) if pd.notna(amplitude) else None,
        "is_between_white_yellow": yellow <= close < white,
        "is_above_white": close >= white,
    }


def _check_variant_kdj(df: pd.DataFrame, variant: Variant) -> Optional[dict]:
    """阶段 B：J 值是否落在该 variant 容许的低位区间。

    只看 J 的绝对水平，不要求方向。文档对完美二（野马电池）的判定依据是
    「量能从跌停日的放量快速缩至企稳日的地量」——量能优先于指标，
    该案例 J 从 21.96 降到 13.73 仍在下行，若要求翘头就会漏掉。
    """
    j_val = df.iloc[-1]["kdj_j"]
    prev_j = df.iloc[-2]["kdj_j"]

    if j_val > variant.kdj_max:
        return None

    return {"kdj_j": round(float(j_val), 2), "kdj_j_prev": round(float(prev_j), 2)}


def _is_high_position(df: pd.DataFrame) -> bool:
    """近 60 日是否已翻倍（即处于高位）。"""
    recent_close = df["close"].iloc[-HIGH_POSITION_LOOKBACK:]
    if recent_close.min() <= 0:
        return True
    return (recent_close.max() / recent_close.min()) - 1 >= HIGH_POSITION_RATIO


def _find_ignitions(df: pd.DataFrame, close_arr, vol_ma_key: str) -> Iterator[Ignition]:
    """阶段 D：在最近 SEARCH_WINDOW 日内倒序搜索放量拉升段，逐个产出候选。

    产出顺序由近及远（同一结束日内部按天数从长到短），
    调用方取第一个能通过后续阶段的候选，即为离今天最近的有效点火。

    必须产出全部候选而非只返回第一个：较近的点火段可能满足本阶段却过不了
    后面的缩量/回踩判定，而更早那段能全过。只取第一个会让策略对参数非单调
    ——实测放宽点火放量倍数，25 只命中里换掉了 17 只（9 出 8 进）。
    """
    # 搜索区间不含最后一天：最后一天要留给「缩量回踩」判定
    start = max(0, len(df) - SEARCH_WINDOW - 1)
    end = len(df) - 2
    search_index = df.index[start:end + 1]

    # 倒序遍历候选结束日；下界 3 是为了给最长的点火段留出前置数据
    for i in range(len(search_index) - 1, 3, -1):
        end_idx = search_index[i]

        # 点火段必须以一根上涨日收尾
        if close_arr[end_idx] <= close_arr[end_idx - 1]:
            continue

        for days in range(IGNITION_MAX_DAYS, 0, -1):
            start_idx = end_idx - days + 1
            if start_idx <= 0:
                continue

            # 起涨基准是点火前一日收盘价
            base_price = close_arr[start_idx - 1]
            if base_price <= 0:
                continue

            # 点火首日不能低开低走跌破基准
            if close_arr[start_idx] < base_price:
                continue

            min_acc_pct = IGNITION_BASE_PCT + IGNITION_PCT_PER_DAY * (days - 1)
            acc_pct = (close_arr[end_idx] / base_price) - 1
            if acc_pct < min_acc_pct:
                continue

            segment = df.iloc[start_idx:end_idx + 1]
            mean_vol = segment['volume'].mean()
            if mean_vol <= 0:
                continue

            # 放量倍数以点火前的盘整期均量为基准
            vol_ma_before = df.at[start_idx - 1, vol_ma_key]
            if not vol_ma_before or mean_vol / vol_ma_before < IGNITION_VOL_MULTIPLE:
                continue

            # 单日最大实体波动，作为「大阴线」判定的标尺
            max_change_pct = (
                (segment['close'] / segment['open'] - 1)
                .abs()
                .where(segment['open'] > 0, 0)
                .max()
            )
            max_vol = segment.loc[segment['_is_up'], 'volume'].max()
            if pd.isna(max_vol) or max_vol <= 0:
                continue

            if _find_big_down_bar(segment, max_change_pct, max_vol):
                continue

            yield Ignition(
                start_idx=start_idx,
                date=df.at[start_idx, 'date'],
                days=days,
                acc_pct=acc_pct,
                support_price=df.at[start_idx, 'low'],
                max_volume=max_vol,
                mean_volume=mean_vol,
                max_change_pct=max_change_pct,
            )


def _check_top_no_volume(df: pd.DataFrame, fire: Ignition) -> Optional[dict]:
    """阶段 E：点火结束之后不再出现与启动波相当的量能。

    文档的链条是「放量启动 → 顶部无量 → 缩量至地量」：启动那一波应当是量能峰值，
    之后若再冒出同等成交量，说明是放量滞涨、主力借高位出货，而非缩量蓄势。

    只衡量点火期「之后」的 K 线。若把点火期本身算进来，价格高点通常就是点火
    放量那一根，比值恒接近 1，这条判定会与「放量启动」自相矛盾。
    """
    after = df.iloc[fire.start_idx + fire.days:]
    if after.empty:
        return {"top_vol_ratio": None}

    top_vol_ratio = after['volume'].max() / fire.max_volume
    if top_vol_ratio > TOP_VOL_RATIO_MAX:
        return None
    return {"top_vol_ratio": round(float(top_vol_ratio), 2)}


def _check_pullback_volume(df: pd.DataFrame, post: pd.DataFrame,
                           fire: Ignition) -> Optional[dict]:
    """阶段 F：最近两日缩量、无放量大阴线、红肥绿瘦。"""
    last_row, prev_row = df.iloc[-1], df.iloc[-2]

    # 回踩必须是缩量的，否则是资金在出逃
    last_vol_ratio = round(last_row["volume"] / fire.max_volume, 3)
    prev_vol_ratio = round(prev_row["volume"] / fire.max_volume, 3)
    if max(last_vol_ratio, prev_vol_ratio) > PULLBACK_VOL_RATIO_MAX:
        return None

    if _find_big_down_bar(post, fire.max_change_pct, fire.max_volume):
        return None

    # 阳线量 vs 阴线量，取各自量最大的 TOP_VOL_BARS 根比较。
    # 「假阴真阳」（收盘低于开盘但高于昨收）计入阳线，除非当日摸到区间新高——
    # 摸高后收阴是冲高回落，仍应视为卖压。
    breakout_high = post['high'].max()
    is_up = post['close'] > post['open']
    is_down = post['close'] < post['open']
    is_fake_down = is_down & (post['close'] > post['close'].shift(1))
    touch_high = post['high'] >= breakout_high

    adjusted_down = is_down & ((~is_fake_down) | touch_high)
    adjusted_up = is_up | (is_fake_down & ~touch_high)

    up_vol_top = post.loc[adjusted_up, 'volume'].nlargest(TOP_VOL_BARS).sum()
    down_vol_top = post.loc[adjusted_down, 'volume'].nlargest(TOP_VOL_BARS).sum()
    if down_vol_top <= 0:
        return None

    vol_ratio = up_vol_top / down_vol_top

    # 文档对完美三的「红肥绿瘦」写的是「阳线实体大于阴线实体」，指实体而非成交量。
    # 两种读法实战都有人用，这里任一满足即可，避免因口径之争漏掉形态。
    body = (post['close'] - post['open']).abs()
    up_body = body[adjusted_up].nlargest(TOP_VOL_BARS).sum()
    down_body = body[adjusted_down].nlargest(TOP_VOL_BARS).sum()
    body_ratio = up_body / down_body if down_body > 0 else float('inf')

    if vol_ratio < VOL_RATIO_THRESHOLD and body_ratio < VOL_RATIO_THRESHOLD:
        return None

    return {
        "last_day_volume_ratio": last_vol_ratio,
        "prev_day_volume_ratio": prev_vol_ratio,
        "three_vol_ratio": round(vol_ratio, 2),
        "three_body_ratio": round(body_ratio, 2) if body_ratio != float('inf') else None,
    }


def _check_pullback_position(df: pd.DataFrame, post: pd.DataFrame,
                             fire: Ignition, variant: Variant) -> Optional[dict]:
    """阶段 G：现价处于该 variant 容许的区间位置。

    量能上要求「缩量回调」或「红肥绿瘦」至少满足其一：前者看阴线是否都在缩量，
    后者看整体阳线量能是否压过阴线。
    """
    up_vol, down_vol = up_down_volume(post)
    if down_vol <= 0:
        return None
    up_down_ratio = up_vol / down_vol

    is_shrinking = is_post_ignition_volume_shrinking(
        df, fire.start_idx + fire.days - 1, fire.max_volume, VOL_SHRINK_THRESHOLD)

    if not (is_shrinking or up_down_ratio > VOL_RATIO_THRESHOLD):
        return None

    # 回踩位置：0 为区间最低、1 为区间最高。完美一/二/三要求落在下半部分；
    # 完美四是缩量上涨，位置上限放到 1.0。
    post_max, post_min = post['high'].max(), post['low'].min()
    if post_max <= post_min:
        return None
    pos_in_range = (df.iloc[-1]["close"] - post_min) / (post_max - post_min)
    if pos_in_range > variant.max_pos_in_range:
        return None

    return {
        "up_down_vol_ratio": round(up_down_ratio, 2),
        "pos_in_breakout_range": round(pos_in_range, 2),
    }


def _stop_loss_hint(df: pd.DataFrame) -> dict:
    """按文档的风控逻辑给出止损参考位。

    文档对昂利康：「因股价与黄线距离远，需以跌破白线为止损点」——
    即贴着黄线时用黄线，远离黄线时改用更近的白线，避免止损空间过大。
    """
    last_row = df.iloc[-1]
    close, white, yellow = last_row["close"], last_row["z_white"], last_row["z_yellow"]
    far_from_yellow = yellow > 0 and (close / yellow - 1) > FAR_FROM_YELLOW_PCT
    return {
        "stop_loss_line": "white" if far_from_yellow else "yellow",
        "stop_loss_price": round(float(white if far_from_yellow else yellow), 2),
    }


def _check_ignition_aftermath(df: pd.DataFrame, fire: Ignition,
                              variant: Variant) -> Optional[dict]:
    """对单个候选点火段跑阶段 E~G，全通过则返回该段的完整指标。"""
    post = df.iloc[fire.start_idx:]
    if post.empty:
        return None

    ret = {
        "fire_date": fire.date,
        "fire_days": fire.days,
        "fire_pct": round(fire.acc_pct * 100, 2),
        "support_price": fire.support_price,
        "max_volume_dur_fire": round(fire.max_volume, 2),
        "mean_volume_dur_fire": round(fire.mean_volume, 2),
        "max_change_pct_dur_fire": round(fire.max_change_pct * 100, 2),
    }

    stages = (
        _check_top_no_volume(df, fire),
        _check_pullback_volume(df, post, fire),
        _check_pullback_position(df, post, fire, variant),
    )
    for stage_result in stages:
        if stage_result is None:
            return None
        ret.update(stage_result)

    return ret


def hunt_b1(df: pd.DataFrame) -> Optional[dict]:
    """B1 策略主入口：命中返回指标 dict（含 variant 标签），否则返回 None。"""
    if df is None or df.empty:
        logger.warning("DataFrame 为空或为 None。")
        return None

    add_kdj_to_dataframe(df, inplace=True)
    add_zxdkx_to_dataframe(df, inplace=True)

    common = _check_common_last_bar(df)
    if common is None:
        return None

    # 点火识别及之后的阶段都依赖这几个辅助列
    add_volume_ma_to_dataframe(df, periods=[CONSOLIDATION_DAYS], inplace=True)
    df['_pct_change_oc'] = df['close'] / df['open'] - 1
    df['_is_up'] = df['close'] > df['open']
    df['_is_down'] = df['close'] < df['open']

    is_high = _is_high_position(df)
    close_arr = df['close'].values
    vol_ma_key = f'volume_ma_{CONSOLIDATION_DAYS}'

    for variant in VARIANTS:
        if is_high and not variant.allow_high_position:
            continue

        kdj_info = _check_variant_kdj(df, variant)
        if kdj_info is None:
            continue

        # 逐个试候选点火段（由近及远），取第一个能走完全部阶段的
        for fire in _find_ignitions(df, close_arr, vol_ma_key):
            aftermath = _check_ignition_aftermath(df, fire, variant)
            if aftermath is not None:
                return {
                    "variant": variant.name,
                    "is_high_position": is_high,
                    **common,
                    **kdj_info,
                    **aftermath,
                    **_stop_loss_hint(df),
                }

    return None


def up_down_volume(segment: pd.DataFrame) -> tuple[float, float]:
    """区间内上涨日与下跌日的总成交量（按实体涨跌，非按昨收）。"""
    if segment.empty:
        return 0.0, 0.0
    change = segment['close'] - segment['open']
    return (
        float(segment.loc[change > 0, 'volume'].sum()),
        float(segment.loc[change < 0, 'volume'].sum()),
    )


def is_post_ignition_volume_shrinking(
    df: pd.DataFrame,
    fire_idx: int,
    base_vol: float,
    shrink_threshold: float = 0.7,
) -> bool:
    """点火后的阴线是否全部明显缩量。无阴线时视为满足。"""
    post_df = df.iloc[fire_idx:]
    if post_df.empty:
        return True
    down_days = post_df[post_df['close'] < post_df['open']]
    if down_days.empty:
        return True
    return bool((down_days['volume'] < base_vol * shrink_threshold).all())


# 测试用例池：《B1 十张图》的十个案例，日期为文档给出的买点日
doc_ten_pool: list[HuntInputLike] = [
    HuntInput(code="688799", to_date="20250512", days=500),  # 华纳药厂 完美一
    HuntInput(code="600366", to_date="20250806", days=500),  # 宁波韵升 完美一
    HuntInput(code="688321", to_date="20250620", days=500),  # 微芯生物 完美一
    HuntInput(code="600601", to_date="20250723", days=500),  # 方正科技 完美一
    HuntInput(code="300689", to_date="20250718", days=500),  # 澄天伟业 完美二
    HuntInput(code="002074", to_date="20250801", days=500),  # 国轩高科 完美二
    HuntInput(code="605378", to_date="20250731", days=500),  # 野马电池 完美二
    HuntInput(code="600184", to_date="20250710", days=500),  # 光电股份 完美二
    HuntInput(code="301076", to_date="20250801", days=500),  # 新瀚新材 完美三
    HuntInput(code="002940", to_date="20250711", days=500),  # 昂利康   完美四
]

target_pool: list[HuntInputLike] = [
    HuntInput(code="000725", to_date='20251223', days=500),  # 京东方A
    HuntInput(code="600138", to_date='20260106', days=500),  # 中青旅
    HuntInput(code="600750", to_date="20251230", days=500),  # 江中药业
    HuntInput(code="688799", to_date="20250509", days=500),  # 娜娜图
    HuntInput(code="600601", to_date="20250623", days=500),  # 方正图
    HuntInput(code="002627", to_date="20260106", days=500),  # 三峡旅游
    HuntInput(code="688321", to_date="20250620", days=500),  # 微星生物
    HuntInput(code="600366", to_date="20250626", days=500),  # 宁波韵升
]

bad_case: list[HuntInputLike] = ["002709"]


def main():
    # 命中时按「名称一行 + 紧凑指标一行」输出，指标 dict 直接可读、可 grep，
    # 便于对命中结果做人工/AI 复盘，不必再单独取数。
    METRIC_KEYS = (
        "variant", "kdj_j", "price_change_pct", "amplitude_pct",
        "fire_date", "fire_days", "fire_pct", "top_vol_ratio",
        "last_day_volume_ratio", "prev_day_volume_ratio",
        "three_vol_ratio", "three_body_ratio",
        "pos_in_breakout_range", "is_high_position",
        "stop_loss_line", "stop_loss_price", "support_price",
    )

    def print_result(result: HuntResult):
        logger.info(f"{result.format_info}")
        info = result.result_info
        if isinstance(info, dict):
            logger.info("    " + ", ".join(
                f"{k}={info.get(k)}" for k in METRIC_KEYS))

    hunter = HuntMachine(max_workers=20, on_result_found=print_result)
    results: list[HuntResult] = hunter.hunt(hunt_b1, min_bars=500, hunt_pool=None)

    if not results:
        print("No stocks found that meet the criteria.")
        return

    codes = [r.code for r in results]
    print(f"\n🎉 Found {len(results)} stocks")

    print("Detailed results:")
    for r in results:
        print(r)

    # 每 10 股打印一行
    for i in range(0, len(codes), 10):
        print(",".join(codes[i:i + 10]))


if __name__ == "__main__":
    main()
