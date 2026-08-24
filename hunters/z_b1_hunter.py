"""B1 策略：放量启动后缩量回踩。

寻找这样的形态：股价先在窄幅箱体内盘整，随后一根或几根放量阳线「点火」拉升，
之后缩量回调到点火区间的下半部分，同时 KDJ 的 J 值进入低位并开始走平或翘头。
本质是在一次已经确认的放量突破之后，等一个缩量的回踩买点。

判定分七个阶段，任一阶段不通过即淘汰（返回 None）：

    1. 末日形态   —— J 值低位、当日涨跌幅温和
    2. 成本线     —— 收盘价与白线均不显著低于黄线
    3. 涨幅上限   —— 近 60 日未翻倍
    4. 点火识别   —— 在近 30 日内倒序搜索放量拉升段
    5. 点火后量能 —— 最近两日缩量、无放量大阴线、红肥绿瘦
    6. 点火前盘整 —— 点火前 5 日为窄幅箱体
    7. 回踩位置   —— 现价处于点火区间下半部分、K 线实体稳定
"""
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from hunter.hunt_machine import HuntInput, HuntInputLike, HuntMachine, HuntResult
from indicators.kdj import add_kdj_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe
from tools.log import get_analyze_logger

logger = get_analyze_logger()

# ---------------------------------------------------------------- 阶段 1：末日形态
# J 值低于此值直接放行（超卖）
KDJ_THRESHOLD = 13
# J 值未够低但已走平/翘头时，仍须低于此值
KDJ_UP_THRESHOLD = 20
# 判定「走平」的 J 值日变动上限
KDJ_FLAT_DELTA = 10.0
# 检查日允许的涨跌幅区间：涨太多说明已启动，跌太多说明还在杀跌
MAX_UP_PCT = 0.018
MIN_DOWN_PCT = -0.02

# ---------------------------------------------------------------- 阶段 2：成本线
# 收盘价与白线相对黄线（长期成本线）的容忍下限
YELLOW_LINE_THRESHOLD = 0.99

# ---------------------------------------------------------------- 阶段 3：涨幅上限
# 近 N 日最高/最低价之比达到此倍数即排除（已炒过一轮）
MAX_INCREASE_LOOKBACK = 60
MAX_INCREASE_RATIO = 1.0

# ---------------------------------------------------------------- 阶段 4：点火识别
# 在最近 N 个交易日内倒序搜索点火段
SEARCH_WINDOW = 30
# 点火段候选配置：(持续天数, 累计涨幅下限, 相对盘整均量的放量倍数下限)
# 天数越短要求的涨幅越小，但放量倍数要求一致偏高
IGNITION_CONFIGS = [
    (7, 0.20, 2.0),
    (6, 0.15, 2.0),
    (5, 0.15, 2.0),
    (4, 0.12, 1.8),
    (3, 0.08, 1.8),
    (2, 0.05, 1.8),
    (1, 0.04, 1.8),
]

# ---------------------------------------------------------------- 阶段 5：点火后量能
# 最近两日成交量相对点火期最大量的上限（要求缩量）
LAST_DAY_VOL_RATIO_MAX = 0.35
PREV_DAY_VOL_RATIO_MAX = 0.45
# 「放量大阴线」判定：跌幅达到区间内最大波动的此比例，且量能超过最大量的此倍数
BIG_DOWN_CHANGE_RATIO = 0.4
BIG_DOWN_VOL_RATIO = 1.1
# 阳线量 / 阴线量的下限（红肥绿瘦）
VOL_RATIO_THRESHOLD = 1.2
# 取成交量最大的前 N 根阳线与阴线做比较
TOP_VOL_BARS = 3
# 「缩量回调」判定：点火后所有阴线量均低于点火期最大量的此比例
VOL_SHRINK_THRESHOLD = 0.6

# ---------------------------------------------------------------- 阶段 6：点火前盘整
# 点火前用于判定箱体的天数，及箱体振幅上限
CONSOLIDATION_DAYS = 5
CONSOLIDATION_BOX_PCT = 0.3

# ---------------------------------------------------------------- 阶段 7：回踩位置
# 现价在点火区间内的相对位置上限（0=区间底部，1=区间顶部）
MAX_POS_IN_RANGE = 0.5
# K 线实体占比的标准差上限（形态过于杂乱则排除）
MAX_BODY_RATIO_STD = 0.4


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
    change_pct = segment['_pct_change_oc']
    change_ratio = change_pct.abs() / max_change_pct
    vol_ratio = segment['volume'] / max_volume
    return bool((
        (change_pct < 0)
        & (change_ratio > BIG_DOWN_CHANGE_RATIO)
        & (vol_ratio > BIG_DOWN_VOL_RATIO)
    ).any())


def _check_last_bar(df: pd.DataFrame) -> Optional[dict]:
    """阶段 1：末日 J 值处于低位，且当日涨跌幅温和。"""
    last_row, prev_row = df.iloc[-1], df.iloc[-2]

    j_val = last_row["kdj_j"]
    prev_j = prev_row["kdj_j"]
    is_oversold = j_val <= KDJ_THRESHOLD
    is_turning_up = j_val > prev_j
    is_flattening = abs(j_val - prev_j) < KDJ_FLAT_DELTA

    # 要么已经足够低，要么在稍高的位置上开始走平/翘头
    if not is_oversold and not (is_turning_up and is_flattening
                                and j_val <= KDJ_UP_THRESHOLD):
        return None

    price_change_pct = (last_row["close"] / prev_row["close"]) - 1
    if not MIN_DOWN_PCT <= price_change_pct <= MAX_UP_PCT:
        return None

    return {
        "kdj_j": j_val,
        "price_change_pct": round(price_change_pct * 100, 2),
    }


def _check_cost_lines(df: pd.DataFrame) -> Optional[dict]:
    """阶段 2：收盘价与白线均不显著低于黄线（长期成本线）。"""
    last_row = df.iloc[-1]
    close, white, yellow = last_row["close"], last_row["z_white"], last_row["z_yellow"]

    floor = yellow * YELLOW_LINE_THRESHOLD
    if close < floor or white < floor:
        return None

    return {
        "is_between_white_yellow": yellow <= close < white,
        "is_above_white": close >= white,
    }


def _is_not_doubled(df: pd.DataFrame) -> bool:
    """阶段 3：近 60 日内未翻倍——已炒过一轮的票不再参与。"""
    recent_close = df["close"].iloc[-MAX_INCREASE_LOOKBACK:]
    if recent_close.min() <= 0:
        return False
    increase_pct = (recent_close.max() / recent_close.min()) - 1
    return increase_pct < MAX_INCREASE_RATIO


def _find_ignition(df: pd.DataFrame, close_arr, vol_ma_key: str) -> Optional[Ignition]:
    """阶段 4：在最近 SEARCH_WINDOW 日内倒序搜索放量拉升段。

    倒序是为了优先匹配离今天最近的一次点火。对每个候选结束日，按
    IGNITION_CONFIGS 从长到短试各种持续天数，命中即返回。
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

        for days, min_acc_pct, min_vol_multiple in IGNITION_CONFIGS:
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

            acc_pct = (close_arr[end_idx] / base_price) - 1
            if acc_pct < min_acc_pct:
                continue

            segment = df.iloc[start_idx:end_idx + 1]
            mean_vol = segment['volume'].mean()
            if mean_vol <= 0:
                continue

            # 放量倍数以点火前的盘整期均量为基准
            vol_ma_before = df.at[start_idx - 1, vol_ma_key]
            if mean_vol / vol_ma_before < min_vol_multiple:
                continue

            # 单日最大实体波动，作为「大阴线」判定的标尺
            max_change_pct = (
                (segment['close'] / segment['open'] - 1)
                .abs()
                .where(segment['open'] > 0, 0)
                .max()
            )
            max_vol = segment.loc[segment['_is_up'], 'volume'].max()

            if _find_big_down_bar(segment, max_change_pct, max_vol):
                continue

            return Ignition(
                start_idx=start_idx,
                date=df.at[start_idx, 'date'],
                days=days,
                acc_pct=acc_pct,
                support_price=df.at[start_idx, 'low'],
                max_volume=max_vol,
                mean_volume=mean_vol,
                max_change_pct=max_change_pct,
            )

    return None


def _check_post_ignition_volume(df: pd.DataFrame, post: pd.DataFrame,
                                fire: Ignition) -> Optional[dict]:
    """阶段 5：点火后量能——最近两日缩量、无放量大阴线、红肥绿瘦。"""
    last_row, prev_row = df.iloc[-1], df.iloc[-2]

    # 回踩必须是缩量的，否则是资金在出逃
    last_vol_ratio = round(last_row["volume"] / fire.max_volume, 3)
    prev_vol_ratio = round(prev_row["volume"] / fire.max_volume, 3)
    if last_vol_ratio > LAST_DAY_VOL_RATIO_MAX or prev_vol_ratio > PREV_DAY_VOL_RATIO_MAX:
        return None

    if _find_big_down_bar(post, fire.max_change_pct, fire.max_volume):
        return None

    # 阳线量 vs 阴线量，取各自量最大的 3 根比较。
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

    three_vol_ratio = up_vol_top / down_vol_top
    if three_vol_ratio < VOL_RATIO_THRESHOLD:
        return None

    return {
        "last_day_volume_ratio": last_vol_ratio,
        "prev_day_volume_ratio": prev_vol_ratio,
        "three_vol_ratio": round(three_vol_ratio, 2),
    }


def _check_consolidation(df: pd.DataFrame, fire: Ignition) -> Optional[dict]:
    """阶段 6：点火前 CONSOLIDATION_DAYS 日构成窄幅箱体。

    点火前的横盘代表筹码充分换手，是「有准备的启动」而非追高。
    """
    start = max(0, fire.start_idx - CONSOLIDATION_DAYS)
    pre_fire = df.iloc[start:fire.start_idx]

    box_low, box_high = pre_fire['close'].min(), pre_fire['close'].max()
    box_range_pct = (box_high - box_low) / box_low if box_low > 0 else 1.0
    if box_range_pct > CONSOLIDATION_BOX_PCT:
        return None

    return {"box_range_pct": round(box_range_pct * 100, 2)}


def _check_pullback(df: pd.DataFrame, post: pd.DataFrame,
                    fire: Ignition) -> Optional[dict]:
    """阶段 7：现价处于点火区间下半部分，且 K 线实体稳定。

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

    # 回踩位置：0 为区间最低、1 为区间最高，要求落在下半部分
    post_max, post_min = post['high'].max(), post['low'].min()
    if post_max <= post_min:
        return None
    pos_in_range = (df.iloc[-1]["close"] - post_min) / (post_max - post_min)
    if pos_in_range > MAX_POS_IN_RANGE:
        return None

    # 实体占比波动过大说明多空反复、形态杂乱
    body_ratio = (post['close'] - post['open']).abs() / (
        post['high'] - post['low']).replace(0, 1)
    body_ratio = body_ratio.dropna()
    if body_ratio.empty:
        return None
    body_std = body_ratio.std()
    if body_std > MAX_BODY_RATIO_STD:
        return None

    return {
        "up_down_vol_ratio": round(up_down_ratio, 2),
        "pos_in_breakout_range": round(pos_in_range, 2),
        "body_ratio_std": round(body_std, 2),
    }


def hunt_b1(df: pd.DataFrame) -> Optional[dict]:
    """B1 策略主入口：命中返回指标 dict，否则返回 None。"""
    if df is None or df.empty:
        logger.warning("DataFrame 为空或为 None。")
        return None

    add_kdj_to_dataframe(df, inplace=True)
    add_zxdkx_to_dataframe(df, inplace=True)

    ret: dict = {}

    for check in (_check_last_bar, _check_cost_lines):
        stage_result = check(df)
        if stage_result is None:
            return None
        ret.update(stage_result)

    if not _is_not_doubled(df):
        return None

    # 点火识别及之后的阶段都依赖这几个辅助列
    add_volume_ma_to_dataframe(df, periods=[CONSOLIDATION_DAYS], inplace=True)
    df['_pct_change_oc'] = df['close'] / df['open'] - 1
    df['_is_up'] = df['close'] > df['open']
    df['_is_down'] = df['close'] < df['open']

    fire = _find_ignition(df, df['close'].values, f'volume_ma_{CONSOLIDATION_DAYS}')
    if fire is None:
        return None

    ret.update({
        "fire_date": fire.date,
        "fire_days": fire.days,
        "fire_pct": round(fire.acc_pct * 100, 2),
        "support_price": fire.support_price,
        "max_volume_dur_fire": round(fire.max_volume, 2),
        "mean_volume_dur_fire": round(fire.mean_volume, 2),
        "max_change_pct_dur_fire": round(fire.max_change_pct * 100, 2),
    })

    # 点火当日至今的全部 K 线，后续三个阶段共用
    post = df.iloc[fire.start_idx:]
    if post.empty:
        return None

    for check in (_check_post_ignition_volume, _check_consolidation, _check_pullback):
        stage_result = (check(df, fire) if check is _check_consolidation
                        else check(df, post, fire))
        if stage_result is None:
            return None
        ret.update(stage_result)

    return ret


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


# 测试用例池
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

ten_perfect_pool: list[HuntInputLike] = [
    HuntInput(code="688799", to_date="20250509", days=500),
    HuntInput(code="600366", to_date="20250806", days=500),
    HuntInput(code="688321", to_date="20250620", days=500),
    HuntInput(code="600601", to_date="20250723", days=500),
    HuntInput(code="300689", to_date="20250718", days=500),
    HuntInput(code="002074", to_date="20250801", days=500),
    HuntInput(code="605378", to_date="20250801", days=500),
    HuntInput(code="600184", to_date="20250710", days=500),
]

bad_case: list[HuntInputLike] = ["002709"]


def main():
    def print_result(result: HuntResult):
        logger.info(f"{result.format_info}")

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
