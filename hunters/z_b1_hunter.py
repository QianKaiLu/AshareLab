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
from datetime import datetime

logger = get_analyze_logger()

kdj_threshold = 5  # KDJ J-value threshold
kdj_up_threshold = 20  # If J is flattening, it must be below this value
yellow_line_threshold = 0.95  # Long-term cost line threshold (as ratio of yellow line)
search_window = 30  # Look for volume breakout within the last N trading days
consolidation_days = 5  # Number of days of consolidation before breakout
consolidation_box_pct = 0.5  # Max allowed price range during consolidation (as % of low)
explosion_vol_multiplier = 2  # Volume multiplier required for breakout
explosion_pct = 0.03  # Minimum price gain on breakout day
vol_ratio_threshold = 1.5  # Required up/down volume ratio after breakout ("red fat, green thin")
vol_shrink_threshold = 0.6  # Max allowed volume on down days after breakout (relative to base volume)

# B1 hunter

def hunt_b1(df: pd.DataFrame) -> Optional[dict]:
    ret = {}
    if df is None or df.empty:
        logger.warning("DataFrame is empty or None.")
        return None
    
    # 1. Check KDJ J-value condition
    add_kdj_to_dataframe(df, inplace=True)
    last_row = df.iloc[-1]
    
    jMatchThreshold = last_row["kdj_j"] <= kdj_threshold
    
    prev_row = df.iloc[-2]
    is_turning_up = last_row["kdj_j"] > prev_row["kdj_j"]
    is_flattening = abs(last_row["kdj_j"] - prev_row["kdj_j"]) < 3.0
    
    # Allow slightly higher J-value if it's turning upward or flattening
    if not jMatchThreshold and not (
        is_turning_up and 
        is_flattening and 
        last_row["kdj_j"] <= kdj_up_threshold):
        return None
    
    ret["kdj_j"] = last_row["kdj_j"]
    
    # 2. Check dual-line system (white & yellow lines)
    add_zxdkx_to_dataframe(df, inplace=True)
    last_row = df.iloc[-1]
    last_close = last_row["close"]
    if last_close < last_row['z_yellow'] * yellow_line_threshold:
        # Price too far below long-term line — reject
        return None
    if last_row["z_white"] < last_row['z_yellow'] * yellow_line_threshold:
        # Death cross (white below yellow) — reject
        return None
    
    ret["is_between_white_yellow"] = (last_close >= last_row['z_yellow']) and (last_close < last_row['z_white'])
    ret["is_above_white"] = last_close >= last_row['z_white']
    
    # 3. Exclude stocks that doubled in price within the last 60 days
    last_60_close = df["close"].iloc[-60:]
    last_60_max = last_60_close.max()
    last_60_min = last_60_close.min()
    if last_60_min <= 0:
        return None
    increase_pct = (last_60_max / last_60_min) - 1
    if increase_pct >= 1.0:
        return None
    
    # 4. Detect volume breakout (ignition point)
    # Configurations: (days, cumulative gain threshold, volume multiplier threshold)
    # Aim to catch early-stage momentum breakouts
    ignition_configs = [
        (6, 0.15,  2.0),
        (5, 0.15,  2.0),
        (4, 0.12,  1.8),
        (3, 0.08,  1.8),
        (2, 0.05,  1.8),
        (1, 0.04,  1.8)
    ]
    
    add_volume_ma_to_dataframe(df, periods=[consolidation_days], inplace=True)
    volume_ma_key = f'volume_ma_{consolidation_days}'
    
    slice_start = len(df) - search_window - 1
    slice_end = len(df) - 2
    recent_df = df.iloc[slice_start:slice_end].copy()
    
    fount_ignition = False
    fire_date = None
    fire_pct = 0.0
    fire_days = 0
    support_price = 0.0
    fire_idx_in_full_df = 0
    max_volume_dur_fire = 0
    
    scan_indices = range(len(recent_df) - 1, 3, -1)
    for i in scan_indices:
        curr_idx = recent_df.index[i]
        
        # Current day must be an up day
        curr_price = df.at[curr_idx, 'close']
        prev_price = df.at[curr_idx - 1, 'close']
        if curr_price < prev_price:
            continue
        
        # Test different breakout durations
        for days, pct_threshold, vol_mul_threshold in ignition_configs:
            
            # Day 1 of breakout must be an up day
            start_idx = curr_idx - days + 1
    
            start_price = df.at[start_idx - 1, 'close']  # Close before breakout
            if start_price <= 0:
                continue
            first_day_price = df.at[start_idx, 'close']  # Close on breakout start day
            if first_day_price < start_price:
                continue
            
            # 1. Cumulative price gain over breakout period
            acc_pct = (curr_price / start_price) - 1
            if acc_pct < pct_threshold:
                continue
            
            # 2. Average volume during breakout vs. pre-breakout MA
            volume_in_days = df.iloc[start_idx:curr_idx + 1]['volume'].mean()
            max_volume_dur_fire = df.iloc[start_idx:curr_idx + 1]['volume'].max()
            volume_ma_before = df.at[start_idx - 1, volume_ma_key]
            if volume_ma_before <= 0:
                continue
            vol_mul = volume_in_days / volume_ma_before
            if vol_mul < vol_mul_threshold:
                continue
            
            # Valid breakout found
            fount_ignition = True
            fire_date = df.at[start_idx, 'date']
            fire_days = days
            fire_pct = round(acc_pct * 100, 2)
            support_price = df.at[start_idx, 'low']
            fire_idx_in_full_df = start_idx
            break
        
        if fount_ignition:
            break
    
    if not fount_ignition:
        return None
    
    ret["fire_date"] = fire_date
    ret["fire_days"] = fire_days
    ret["fire_pct"] = fire_pct
    ret["support_price"] = support_price
    ret["max_volume_dur_fire"] = max_volume_dur_fire
    
    # 5. Key support: current price must not fall below breakout-day low
    if last_close < support_price:
        return None
    
    # 6. Verify pre-breakout consolidation
    pre_fire_start = fire_idx_in_full_df - consolidation_days
    if pre_fire_start < 0:
        pre_fire_start = 0
    
    pre_fire_data = df.iloc[pre_fire_start:fire_idx_in_full_df]  # Exclude breakout day itself
    box_high = pre_fire_data['close'].max()
    box_low = pre_fire_data['close'].min()
    box_range_pct = (box_high - box_low) / box_low if box_low > 0 else 1.0
    if box_range_pct > consolidation_box_pct:
        return None
    ret["box_range_pct"] = round(box_range_pct * 100, 2)
    
    # 7. Post-breakout volume behavior: "red fat, green thin"
    up_vol, down_vol = up_down_volume(df, fire_idx_in_full_df)
    if down_vol <= 0:
        return None
    vol_ratio = up_vol / down_vol
    is_vol_ratio_ok = vol_ratio > vol_ratio_threshold
    ret["up_down_vol_ratio"] = round(vol_ratio, 2)
    
    # 8. Ensure no heavy-volume down days after breakout
    is_post_fire_vol_shrinking = is_post_ignition_volume_shrinking(
        df, 
        fire_idx_in_full_df + fire_days - 1, 
        max_volume_dur_fire, 
        vol_shrink_threshold
    )
    
    # Require either shrinking down-volume OR strong up/down volume ratio
    if not (is_post_fire_vol_shrinking or is_vol_ratio_ok):
        return None
    
    return ret

def up_down_volume(df: pd.DataFrame, target_pos) -> tuple[float, float]:
    """Calculate total volume on up-days and down-days from target position onward (inclusive).
    
    Args:
        df (pd.DataFrame): DataFrame with 'close' and 'volume' columns.
        target_pos: Index label marking the start position (must align with df index).
    
    Returns:
        tuple: (total up-volume, total down-volume)
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
    base_vol: float,  # Reference volume (e.g., max during breakout)
    shrink_threshold: float = 0.7  # Max allowed down-day volume as ratio of base_vol
) -> bool:
    """Check whether all down days after breakout show reduced volume."""
    post_df = df.loc[df.index >= fire_idx].copy()
    if post_df.empty:
        return True  # No data after breakout — assume valid
    
    # Mark down days (close < previous close)
    post_df['is_down'] = post_df['close'] < post_df['close'].shift(1)
    
    down_days = post_df[post_df['is_down']]
    if down_days.empty:
        return True  # No down days — condition satisfied by default
    
    # Ensure every down day has volume below threshold
    shrunk = (down_days['volume'] < base_vol * shrink_threshold)
    return shrunk.all()

# These are mandatory test cases (known patterns that should be detected)
target_pool: list[HuntInputLike] = [
    HuntInput(code="000725", to_date='20251223', days=500),
    HuntInput(code="600138", to_date='20260106', days=500),
    HuntInput(code="600750", to_date="20251230",days=500),
    HuntInput(code="688799", to_date="20250509",days=500), # 娜娜图
    HuntInput(code="600601", to_date="20250623",days=500), # 方正图
    HuntInput(code="002627", to_date="20260106",days=500), # 三峡旅游
    HuntInput(code="688321", to_date="20250619",days=500), # 微星生物
    HuntInput(code="600366", to_date="20250626",days=500), # 宁波韵升
]

def main():
    hunter = HuntMachine(max_workers=12)
    
    # Run the hunt
    results: list[HuntResult] = hunter.hunt(hunt_b1, min_bars=365)
    
    if not results:
        print("No stocks found matching the criteria.")
        return

    # Process results
    # results is a list of HuntResult objects
    codes: list[str] = [result.code for result in results]
    
    print(f"\n🎉 Found {len(results)} stocks:")
    for result in results:
        print(result)
        print(result.result_info)
    print(f"codes: {','.join(codes)}")
    
    print(f"list:")
    for result in results:
        print(result)
    
    if len(results) < 10:
        date_in_title = datetime.now().strftime('%Y-%m-%d')
        draw_hunt_results(results, title="Today b1", desc=date_in_title, theme_name="dark_minimal")
    else:
        # Plot in batches of 6 charts per image
        batch_size = 6
        step = 0
        for i in range(0, len(results), batch_size):
            step += 1
            batch_results = results[i:i + batch_size]
            date_in_title = datetime.now().strftime('%Y-%m-%d')
            draw_hunt_results(batch_results, title=f"Today b1 - Batch {step}", desc=date_in_title, theme_name="dark_minimal")
    


if __name__ == "__main__":
    main()
