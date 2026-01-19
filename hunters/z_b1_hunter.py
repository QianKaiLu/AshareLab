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

# KDJ 指标中 J 值的阈值
kdj_threshold = 13  
# 检查日允许的最大价格涨幅（百分比）
max_up_pct = 0.018  
# 检查日允许的最大价格跌幅（百分比）
min_down_pct = -0.02  
# 如果 J 值趋于平缓，则其必须低于此值
kdj_up_threshold = 20  
# 长期成本线（黄线）的阈值（以收盘价与黄线的比值表示）
yellow_line_threshold = 0.99  
# 在最近 N 个交易日内寻找放量突破点
search_window = 30  
# 突破前的盘整天数
consolidation_days = 5  
# 盘整期间价格波动范围上限（相对于最低价的百分比）
consolidation_box_pct = 0.3  
# 突破时所需成交量倍数（相对于盘整期均量）
explosion_vol_multiplier = 2  
# 突破后阳线成交量与阴线成交量的比值要求（"红肥绿瘦"）
vol_ratio_threshold = 1.2  
# 突破后下跌日成交量上限（相对于突破期间最大成交量的比例）
vol_shrink_threshold = 0.6  

# B1 策略猎手

def hunt_b1(df: pd.DataFrame) -> Optional[dict]:
    ret = {}
    if df is None or df.empty:
        logger.warning("DataFrame 为空或为 None。")
        return None
    
    # 1. 检查 KDJ 的 J 值条件
    add_kdj_to_dataframe(df, inplace=True)
    last_row = df.iloc[-1]
    
    # J 值是否小于等于阈值
    jMatchThreshold = last_row["kdj_j"] <= kdj_threshold
    
    prev_row = df.iloc[-2]
    is_turning_up = last_row["kdj_j"] > prev_row["kdj_j"]
    is_flattening = abs(last_row["kdj_j"] - prev_row["kdj_j"]) < 10.0
    
    # 如果 J 值不满足阈值，但处于向上拐头或走平状态，且未超过放宽阈值，则可接受
    if not jMatchThreshold and not (
        is_turning_up and 
        is_flattening and 
        last_row["kdj_j"] <= kdj_up_threshold):
        return None
    
    ret["kdj_j"] = last_row["kdj_j"]
    
    # 1.1 检查当日价格变动是否在合理范围内
    price_change_pct = (last_row["close"] / prev_row["close"]) - 1
    if price_change_pct < min_down_pct or price_change_pct > max_up_pct:
        return None
    ret["price_change_pct"] = round(price_change_pct * 100, 2)
    
    # # 1.2 检查 BBI 导数是否处于上升趋势（当前被注释掉）
    # add_bbi_to_dataframe(df, inplace=True)
    # if not is_bbi_deriv_uptrend(bbi=df["bbi"], min_window=20, max_window=90, q_threshold=0.2):
    #     return None
     
    # 2. 检查双线系统（白线与黄线）
    add_zxdkx_to_dataframe(df, inplace=True)
    last_row = df.iloc[-1]
    last_close = last_row["close"]
    # 收盘价不能远低于长期成本线（黄线）
    if last_close < last_row['z_yellow'] * yellow_line_threshold:
        return None
    # 白线不能低于黄线（避免“死叉”）
    if last_row["z_white"] < last_row['z_yellow'] * yellow_line_threshold:
        return None
    
    # 记录价格与均线的相对位置
    ret["is_between_white_yellow"] = (last_close >= last_row['z_yellow']) and (last_close < last_row['z_white'])
    ret["is_above_white"] = last_close >= last_row['z_white']
    
    # 3. 排除过去 60 天内股价翻倍的股票
    last_60_close = df["close"].iloc[-60:]
    last_60_max = last_60_close.max()
    last_60_min = last_60_close.min()
    if last_60_min <= 0:
        return None
    increase_pct = (last_60_max / last_60_min) - 1
    if increase_pct >= 1.0:  # 即涨幅 ≥ 100%
        return None
    
    # 4. 检测放量启动点（“点火”信号）
    # 配置：(持续天数, 累计涨幅阈值, 成交量倍数阈值)
    ignition_configs = [
        (7, 0.20,  2.0),
        (6, 0.15,  2.0),
        (5, 0.15,  2.0),
        (4, 0.12,  1.8),
        (3, 0.08,  1.8),
        (2, 0.05,  1.8),
        (1, 0.04,  1.8)
    ]
    
    # 添加盘整期成交量均线
    add_volume_ma_to_dataframe(df, periods=[consolidation_days], inplace=True)
    volume_ma_key = f'volume_ma_{consolidation_days}'
    
    # 从最近 search_window 天内向前扫描（排除最后一天）
    slice_start = len(df) - search_window - 1
    slice_end = len(df) - 2
    recent_df = df.iloc[slice_start:slice_end].copy()
    
    found_ignition = False
    fire_date = None
    fire_days = 0
    fire_pct = 0.0
    support_price = 0.0
    fire_idx_in_full_df = 0
    max_volume_dur_fire = 0
    mean_volume_dur_fire = 0.0
    
    # 从近期向早期倒序扫描
    scan_indices = range(len(recent_df) - 1, 3, -1)
    for i in scan_indices:
        curr_idx = recent_df.index[i]
        
        # 当前日必须是上涨日
        curr_price = df.at[curr_idx, 'close']
        prev_price = df.at[curr_idx - 1, 'close']
        if curr_price < prev_price:
            continue
        
        # 尝试不同长度的突破模式
        for days, pct_threshold, vol_mul_threshold in ignition_configs:
            
            # 突破起始日必须是上涨日
            start_idx = curr_idx - days + 1
            if start_idx <= 0:
                continue

            start_price = df.at[start_idx - 1, 'close']  # 突破前一日收盘价
            if start_price <= 0:
                continue
            first_day_price = df.at[start_idx, 'close']  # 突破首日收盘价
            if first_day_price < start_price:
                continue
            
            # 1. 突破期间累计涨幅
            acc_pct = (curr_price / start_price) - 1
            if acc_pct < pct_threshold:
                continue
            
            # 2. 突破期间平均成交量 vs 突破前均量
            mean_volume_dur_fire = df.iloc[start_idx:curr_idx + 1]['volume'].mean()
            # 找出突破期间所有阳线中的最大成交量
            mask = (df.index >= df.index[start_idx]) & (df.index <= df.index[curr_idx]) & (df['close'] > df['open'])
            max_volume_dur_fire = df.loc[mask, 'volume'].max() if mask.any() else 0
            # 计算突破期间最大单日涨跌幅
            max_price_change_pct = df.iloc[start_idx:curr_idx + 1].apply(
                lambda row: abs((row['close'] / row['open']) - 1) if row['open'] > 0 else 0, axis=1).max()
            volume_ma_before = df.at[start_idx - 1, volume_ma_key]
            if mean_volume_dur_fire <= 0:
                continue
            vol_mul = mean_volume_dur_fire / volume_ma_before
            if vol_mul < vol_mul_threshold:
                continue
            
            # 3. 不能有放量大阴线（防止选到顶部出货）
            has_large_down_volume_candle = False
            for check_idx in range(start_idx, curr_idx + 1):
                check_close = df.at[check_idx, 'close']
                check_open = df.at[check_idx, 'open']
                check_volume = df.at[check_idx, 'volume']
                if check_open <= 0:
                    has_large_down_volume_candle = True
                    break
                day_change_pct = (check_close / check_open) - 1
                # 当日涨跌幅占突破期间最大涨跌幅的比例
                day_change_ratio = abs(day_change_pct) / max_price_change_pct
                # 当日成交量占突破期间最大成交量的比例
                vol_ratio = check_volume / max_volume_dur_fire if max_volume_dur_fire > 0 else 0
                # 若为下跌日，且跌幅显著、成交量放大，则视为出货信号
                if day_change_pct < 0 and day_change_ratio > 0.4 and vol_ratio > 1.1:
                    has_large_down_volume_candle = True
                    break
            if has_large_down_volume_candle:
                continue
            
            # 找到有效启动点
            found_ignition = True
            fire_date = df.at[start_idx, 'date']
            fire_days = days
            fire_pct = round(acc_pct * 100, 2)
            support_price = df.at[start_idx, 'low']  # 启动日最低价作为支撑
            fire_idx_in_full_df = start_idx
            break  # 跳出内层循环
        
        if found_ignition:
            break  # 跳出外层循环
    
    if not found_ignition:
        return None
    
    # 记录启动点信息
    ret["fire_date"] = fire_date
    ret["fire_days"] = fire_days
    ret["fire_pct"] = fire_pct
    ret["support_price"] = support_price
    ret["max_volume_dur_fire"] = round(max_volume_dur_fire, 2)
    ret["mean_volume_dur_fire"] = round(mean_volume_dur_fire, 2)
    ret["max_change_pct_dur_fire"] = round(max_price_change_pct * 100, 2)
    
    # 4.1 突破后需缩量（最后两日成交量不能太大）
    last_day_volume_ratio = round(last_row["volume"] / max_volume_dur_fire, 3)
    prev_day_volume_ratio = round(prev_row["volume"] / max_volume_dur_fire, 3)
    if last_day_volume_ratio > 0.4:
        return None
    if prev_day_volume_ratio > 0.55:
        return None
    ret["last_day_volume_ratio"] = last_day_volume_ratio
    ret["prev_day_volume_ratio"] = prev_day_volume_ratio
    
    # 5. 价格不应跌破启动日最低价（与黄白线判断重复，暂不启用）
    # if last_close < support_price:
    #     return None
    
    # 4.2 再次检查启动后是否有放量大阴线
    for check_idx in range(fire_idx_in_full_df, len(df)):
        check_close = df.at[check_idx, 'close']
        check_open = df.at[check_idx, 'open']
        check_volume = df.at[check_idx, 'volume']
        if check_open <= 0:
            continue
        day_change_pct = (check_close / check_open) - 1
        day_change_ratio = abs(day_change_pct) / max_price_change_pct
        vol_ratio = check_volume / max_volume_dur_fire if max_volume_dur_fire > 0 else 0
        if day_change_pct < 0 and day_change_ratio > 0.4 and vol_ratio > 1.1:
            return None
        
    # 4.3 阳线成交量 vs 阴线成交量：取启动后前三大的阳线与阴线成交量对比
    max_three_up_vol = df.loc[
        (df.index >= fire_idx_in_full_df) & (df['close'] > df['open']),
        'volume'].nlargest(3).sum()
    max_three_down_vol = df.loc[
        (df.index >= fire_idx_in_full_df) & (df['close'] < df['open']),
        'volume'].nlargest(3).sum()
    if max_three_down_vol <= 0:
        return None
    three_vol_ratio = max_three_up_vol / max_three_down_vol
    if three_vol_ratio < vol_ratio_threshold:
        return None
    ret["three_vol_ratio"] = round(three_vol_ratio, 2)
    
    # 6. 验证突破前存在盘整
    pre_fire_start = fire_idx_in_full_df - consolidation_days
    if pre_fire_start < 0:
        pre_fire_start = 0
    
    pre_fire_data = df.iloc[pre_fire_start:fire_idx_in_full_df]  # 不包含突破日
    box_high = pre_fire_data['close'].max()
    box_low = pre_fire_data['close'].min()
    box_range_pct = (box_high - box_low) / box_low if box_low > 0 else 1.0
    if box_range_pct > consolidation_box_pct:
        return None
    ret["box_range_pct"] = round(box_range_pct * 100, 2)
    
    # 7. 突破后阳线与阴线成交量之比
    up_vol, down_vol = up_down_volume(df, fire_idx_in_full_df)
    if down_vol <= 0:
        return None
    vol_ratio = up_vol / down_vol
    is_vol_ratio_ok = vol_ratio > vol_ratio_threshold
    ret["up_down_vol_ratio"] = round(vol_ratio, 2)
    
    # 8. 突破后下跌日成交量是否明显萎缩
    is_post_fire_vol_shrinking = is_post_ignition_volume_shrinking(
        df, 
        fire_idx_in_full_df + fire_days - 1, 
        max_volume_dur_fire, 
        vol_shrink_threshold
    )
    
    # 满足任一条件即可：要么缩量下跌，要么阳线成交量显著大于阴线
    if not (is_post_fire_vol_shrinking or is_vol_ratio_ok):
        return None
    
    return ret

def up_down_volume(df: pd.DataFrame, target_pos) -> tuple[float, float]:
    """计算从指定位置开始（含）的上涨日与下跌日总成交量。
    
    Args:
        df (pd.DataFrame): 包含 'close' 和 'volume' 列的数据框。
        target_pos: 起始索引位置（需与 df.index 对齐）。

    Returns:
        tuple: (上涨日总成交量, 下跌日总成交量)
    """
    temp_df = df[['close', 'volume']].copy()
    temp_df['change'] = temp_df['close'].diff()
    
    df_after = temp_df.loc[temp_df.index >= target_pos]
    
    if len(df_after) < 1:
        return 0.0, 0.0
    
    up_vol = df_after[df_after['change'] > 0]['volume'].sum()
    down_vol = df_after[df_after['change'] < 0]['volume'].sum()
    
    return float(up_vol), float(down_vol)

def is_post_ignition_volume_shrinking(
    df: pd.DataFrame, 
    fire_idx: int, 
    base_vol: float,  # 参考成交量（如突破期间最大成交量）
    shrink_threshold: float = 0.7  # 下跌日成交量上限（相对于 base_vol 的比例）
) -> bool:
    """检查突破后所有下跌日是否成交量明显萎缩。"""
    post_df = df.loc[df.index >= fire_idx].copy()
    if post_df.empty:
        return True  # 无后续数据，默认通过
    
    # 标记下跌日（收盘价低于前一日）
    post_df['is_down'] = post_df['close'] < post_df['close'].shift(1)
    
    down_days = post_df[post_df['is_down']]
    if down_days.empty:
        return True  # 无下跌日，默认通过
    
    # 所有下跌日成交量必须低于阈值
    shrunk = (down_days['volume'] < base_vol * shrink_threshold)
    return shrunk.all()

# 以下为强制测试用例（已知应被识别的股票形态）
target_pool: list[HuntInputLike] = [
    HuntInput(code="000725", to_date='20251223', days=500), # 京东方A
    HuntInput(code="600138", to_date='20260106', days=500), # 中青旅
    HuntInput(code="600750", to_date="20251230", days=500), # 江中药业
    HuntInput(code="688799", to_date="20250509", days=500), # 娜娜图
    HuntInput(code="600601", to_date="20250623", days=500), # 方正图
    HuntInput(code="002627", to_date="20260106", days=500), # 三峡旅游
    HuntInput(code="688321", to_date="20250620", days=500), # 微星生物
    HuntInput(code="600366", to_date="20250626", days=500), # 宁波韵升
]

# “完美图形”示例池
ten_perfect_pool: list[HuntInputLike] = [
    HuntInput(code="688799", to_date="20250509", days=500), # 娜娜图
    HuntInput(code="600366", to_date="20250806", days=500), # 宁波韵升
    HuntInput(code="688321", to_date="20250620", days=500), # 微星生物
    HuntInput(code="600601", to_date="20250723", days=500), # 方正图
    HuntInput(code="300689", to_date="20250718", days=500), # 澄天伟业
    HuntInput(code="002074", to_date="20250801", days=500), # 国轩高科
    HuntInput(code="605378", to_date="20250801", days=500), # 野马电池
    HuntInput(code="600184", to_date="20250710", days=500), # 光电股份
]

# 应被排除的反例
bad_case: list[HuntInputLike] = [
    "002709",
]

def main():
    def print_result(result: HuntResult):
        logger.info(f"{result.format_info}")

    hunter = HuntMachine(max_workers=12, on_result_found=print_result)
    
    pool = hs300_csi500_hunt_pool()
    
    # Execute hunt
    results: list[HuntResult] = hunter.hunt(hunt_b1, min_bars=500, hunt_pool=pool)
    
    if not results:
        print("No stocks found that meet the criteria.")
        return

    # Process results
    codes: list[str] = [result.code for result in results]
    
    print(f"\n🎉 Found {len(results)} stocks in {len(pool)}:")
    for result in results:
        print(result.format_info)
        print(result.result_info)
    print(f"Stock code list: {','.join(codes)}")
    
    print(f"Detailed results:")
    for result in results:
        print(result)
    
    # 绘图
    # if len(results) < 10:
    #     date_in_title = datetime.now().strftime('%Y-%m-%d')
    #     draw_hunt_results(results, title="今日 B1 策略", desc=date_in_title, theme_name="dark_minimal")
    # else:
    #     batch_size = 10
    #     step = 0
    #     for i in range(0, len(results), batch_size):
    #         step += 1
    #         batch_results = results[i:i + batch_size]
    #         date_in_title = datetime.now().strftime('%Y-%m-%d')
    #         draw_hunt_results(batch_results, title=f"今日 B1 策略 - 第 {step} 批", desc=date_in_title, theme_name="dark_minimal")

if __name__ == "__main__":
    main()
