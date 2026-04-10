import pandas as pd
from typing import Callable, List, Any, Optional
from tools.log import get_analyze_logger
from dataclasses import dataclass, field
from indicators.kdj import add_kdj_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe
from indicators.bbi import add_bbi_to_dataframe
from indicators.macd import add_macd_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe
from hunter.filters.is_bbi_deriv_uptrend import is_bbi_deriv_uptrend
from hunter.hunt_machine import HuntMachine, HuntResult, HuntInputLike, HuntInput
from hunters.hunt_output import draw_hunt_results
from hunter.hunt_pools import hs300_csi500_hunt_pool
from datetime import datetime

logger = get_analyze_logger()


def hunt_b2(df: pd.DataFrame) -> Optional[dict]:
    # 处理空数据
    if df is None or df.empty:
        logger.warning("DataFrame 为空或为 None。")
        return None
    
    add_kdj_to_dataframe(df, inplace=True)
    add_zxdkx_to_dataframe(df, inplace=True)
    
    ret = {}
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    # 检查 J 值条件
    j_val = last_row["kdj_j"]
    j_match = j_val <= kdj_threshold
    is_turning_up = j_val > prev_row["kdj_j"]
    is_flattening = abs(j_val - prev_row["kdj_j"]) < 10.0

    if not j_match and not (is_turning_up and is_flattening and j_val <= kdj_up_threshold):
        return None
    ret["kdj_j"] = j_val

    # 检查当日价格变动是否在合理范围内
    price_change_pct = (last_row["close"] / prev_row["close"]) - 1
    if price_change_pct < min_down_pct or price_change_pct > max_up_pct:
        return None
    ret["price_change_pct"] = round(price_change_pct * 100, 2)

    # 添加双线系统指标（白线/黄线）
    close = last_row["close"]
    yellow = last_row["z_yellow"]
    white = last_row["z_white"]

    # 收盘价不能远低于黄线，且白线不能低于黄线
    if close < yellow * yellow_line_threshold or white < yellow * yellow_line_threshold:
        return None

    ret["is_between_white_yellow"] = yellow <= close < white
    ret["is_above_white"] = close >= white

    # 排除过去 60 天内股价翻倍的股票
    last_60_close = df["close"].iloc[-60:]
    if last_60_close.min() <= 0:
        return None
    increase_pct = (last_60_close.max() / last_60_close.min()) - 1
    if increase_pct >= 1.0:
        return None

    # 配置放量启动模式：(持续天数, 累计涨幅阈值, 成交量倍数)
    ignition_configs = [
        (7, 0.20, 2.0),
        (6, 0.15, 2.0),
        (5, 0.15, 2.0),
        (4, 0.12, 1.8),
        (3, 0.08, 1.8),
        (2, 0.05, 1.8),
        (1, 0.04, 1.8)
    ]

    # 添加盘整期成交量均线
    add_volume_ma_to_dataframe(df, periods=[consolidation_days], inplace=True)
    vol_ma_key = f'volume_ma_{consolidation_days}'

    # 辅助列：涨跌、涨跌幅
    df['_pct_change_oc'] = df['close'] / df['open'] - 1
    df['_is_up'] = df['close'] > df['open']
    df['_is_down'] = df['close'] < df['open']

    # 从最近 search_window 天内倒序扫描（排除最后一天）
    start_idx = max(0, len(df) - search_window - 1)
    end_idx = len(df) - 2
    recent_df = df.iloc[start_idx:end_idx + 1]
    close_arr = df['close'].values

    found_ignition = False
    fire_date = fire_days = fire_pct = support_price = max_volume_dur_fire = mean_volume_dur_fire = max_price_change_pct = 0
    fire_idx_in_full_df = 0

    # 从近期向早期倒序扫描寻找点火信号
    for i in range(len(recent_df) - 1, 3, -1):
        curr_idx = recent_df.index[i]
        if close_arr[curr_idx] <= close_arr[curr_idx - 1]:
            continue

        for days, pct_th, vol_mul_th in ignition_configs:
            start_idx_fire = curr_idx - days + 1
            if start_idx_fire <= 0:
                continue

            start_price = close_arr[start_idx_fire - 1]
            if start_price <= 0:
                continue
            first_day_price = close_arr[start_idx_fire]
            if first_day_price < start_price:
                continue

            # 累计涨幅
            acc_pct = (close_arr[curr_idx] / start_price) - 1
            if acc_pct < pct_th:
                continue

            # 成交量分析
            segment = df.iloc[start_idx_fire:curr_idx + 1]
            mean_vol = segment['volume'].mean()
            max_vol = segment.loc[segment['_is_up'], 'volume'].max()
            if mean_vol <= 0:
                continue

            vol_ma_before = df.at[start_idx_fire - 1, vol_ma_key]
            vol_mul = mean_vol / vol_ma_before
            if vol_mul < vol_mul_th:
                continue

            # 计算最大单日价格波动
            open_ = segment['open']
            close_ = segment['close']
            price_change_abs = (close_ / open_ - 1).abs().where(open_ > 0, 0)
            max_price_change_pct = price_change_abs.max()

            # 排除放量大阴线
            day_change_pct = segment['_pct_change_oc']
            day_change_ratio = day_change_pct.abs() / max_price_change_pct
            vol_ratio = segment['volume'] / max_vol
            has_large_down = (
                (day_change_pct < 0) &
                (day_change_ratio > 0.4) &
                (vol_ratio > 1.1)
            ).any()
            if has_large_down:
                continue

            # 找到有效点火
            found_ignition = True
            fire_date = df.at[start_idx_fire, 'date']
            fire_days = days
            fire_pct = round(acc_pct * 100, 2)
            support_price = df.at[start_idx_fire, 'low']
            fire_idx_in_full_df = start_idx_fire
            max_volume_dur_fire = max_vol
            mean_volume_dur_fire = mean_vol
            break

        if found_ignition:
            break

    if not found_ignition:
        return None

    ret.update({
        "fire_date": fire_date,
        "fire_days": fire_days,
        "fire_pct": fire_pct,
        "support_price": support_price,
        "max_volume_dur_fire": round(max_volume_dur_fire, 2),
        "mean_volume_dur_fire": round(mean_volume_dur_fire, 2),
        "max_change_pct_dur_fire": round(max_price_change_pct * 100, 2)
    })

    # 突破后需缩量（最后两日）
    last_vol_ratio = round(last_row["volume"] / max_volume_dur_fire, 3)
    prev_vol_ratio = round(prev_row["volume"] / max_volume_dur_fire, 3)
    if last_vol_ratio > 0.35 or prev_vol_ratio > 0.45:
        return None
    ret["last_day_volume_ratio"] = last_vol_ratio
    ret["prev_day_volume_ratio"] = prev_vol_ratio

    # 突破后不能有放量大阴线
    post_segment = df.iloc[fire_idx_in_full_df:]
    day_change_pct = post_segment['_pct_change_oc']
    day_change_ratio = day_change_pct.abs() / max_price_change_pct
    vol_ratio = post_segment['volume'] / max_volume_dur_fire
    has_bad_down = (
        (day_change_pct < 0) &
        (day_change_ratio > 0.4) &
        (vol_ratio > 1.1)
    ).any()
    if has_bad_down:
        return None

    # 阳线/阴线成交量比（含假阴真阳修正）
    post_df = df.loc[df.index >= fire_idx_in_full_df, ['open', 'close', 'high', 'low', 'volume']].copy()
    if post_df.empty:
        return None

    breakout_high = post_df['high'].max()
    is_up = post_df['close'] > post_df['open']
    is_down = post_df['close'] < post_df['open']
    is_fake_down = is_down & (post_df['close'] > post_df['close'].shift(1))
    touch_high = post_df['high'] >= breakout_high

    adjusted_down = is_down & ((~is_fake_down) | touch_high)
    adjusted_up = is_up | (is_fake_down & ~touch_high)

    up_vol_top3 = post_df.loc[adjusted_up, 'volume'].nlargest(3).sum()
    down_vol_top3 = post_df.loc[adjusted_down, 'volume'].nlargest(3).sum()
    if down_vol_top3 <= 0:
        return None
    three_vol_ratio = up_vol_top3 / down_vol_top3
    if three_vol_ratio < vol_ratio_threshold:
        return None
    ret["three_vol_ratio"] = round(three_vol_ratio, 2)

    # 验证突破前存在盘整
    pre_start = max(0, fire_idx_in_full_df - consolidation_days)
    pre_fire = df.iloc[pre_start:fire_idx_in_full_df]
    box_low = pre_fire['close'].min()
    box_high = pre_fire['close'].max()
    if box_low > 0:
        box_range_pct = (box_high - box_low) / box_low
    else:
        box_range_pct = 1.0
    if box_range_pct > consolidation_box_pct:
        return None
    ret["box_range_pct"] = round(box_range_pct * 100, 2)

    # 突破后总阳线/阴线成交量比
    up_vol, down_vol = up_down_volume(df, fire_idx_in_full_df)
    if down_vol <= 0:
        return None
    vol_ratio = up_vol / down_vol
    is_vol_ok = vol_ratio > vol_ratio_threshold
    ret["up_down_vol_ratio"] = round(vol_ratio, 2)

    # 检查突破后是否缩量回调
    is_shrinking = is_post_ignition_volume_shrinking(
        df, fire_idx_in_full_df + fire_days - 1, max_volume_dur_fire, vol_shrink_threshold
    )

    # 至少满足缩量回调或红肥绿瘦之一
    if not (is_shrinking or is_vol_ok):
        return None

    # 当前位置应在突破区间下半部分
    post_max = post_df['high'].max()
    post_min = post_df['low'].min()
    if post_max <= post_min:
        return None
    pos_in_range = (last_row["close"] - post_min) / (post_max - post_min)
    if pos_in_range > 0.5:
        return None
    ret["pos_in_breakout_range"] = round(pos_in_range, 2)

    # 实体比率波动不宜过大
    post_df_all = df.loc[df.index >= fire_idx_in_full_df].copy()
    body_ratio = (post_df_all['close'] - post_df_all['open']).abs() / (
        post_df_all['high'] - post_df_all['low']
    ).replace(0, 1)
    body_ratio = body_ratio.dropna()
    if len(body_ratio) == 0:
        return None
    body_std = body_ratio.std()
    if body_std > 0.4:
        return None
    ret["body_ratio_std"] = round(body_std, 2)

    return ret

def up_down_volume(df: pd.DataFrame, target_pos) -> tuple[float, float]:
    """计算从指定位置开始的上涨日与下跌日总成交量"""
    temp = df.loc[df.index >= target_pos, ['open', 'close', 'volume']].copy()
    if temp.empty:
        return 0.0, 0.0
    temp['change'] = temp['close'] - temp['open']
    up_vol = temp[temp['change'] > 0]['volume'].sum()
    down_vol = temp[temp['change'] < 0]['volume'].sum()
    return float(up_vol), float(down_vol)

def is_post_ignition_volume_shrinking(
    df: pd.DataFrame, 
    fire_idx: int, 
    base_vol: float, 
    shrink_threshold: float = 0.7
) -> bool:
    """检查突破后所有下跌日是否成交量明显萎缩"""
    post_df = df.iloc[fire_idx:].copy()
    if post_df.empty:
        return True
    post_df['_is_down'] = post_df['close'] < post_df['open']
    down_days = post_df[post_df['_is_down']]
    if down_days.empty:
        return True
    return (down_days['volume'] < base_vol * shrink_threshold).all()

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
    pool = ten_perfect_pool
    
    # 执行选股
    results: list[HuntResult] = hunter.hunt(hunt_b1, min_bars=500, hunt_pool=None)
    
    if not results:
        print("No stocks found that meet the criteria.")
        return

    codes = [r.code for r in results]
    print(f"\n🎉 Found {len(results)} stocks")
    # for r in results:
    #     print(r.format_info)
    #     print(r.result_info)
    
    print("Detailed results:")
    for r in results:
        print(r)
    
    # 每 10 股打印一行
    for i in range(0, len(codes), 10):
        print(",".join(codes[i:i+10]))

if __name__ == "__main__":
    main()
