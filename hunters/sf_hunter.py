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
from hunter.hunt_machine import HuntMachine, HuntResult

logger = get_analyze_logger()

# 买鞋：少妇战法

def hunt_sf(df: pd.DataFrame, kdj_threshold=5) -> Optional[dict]:
    ret = {}
    if df is None or df.empty:
        logger.warning("DataFrame is empty or None.")
        return None
    
    # 1. 检查 j 值
    add_kdj_to_dataframe(df, inplace=True)
    last_row = df.iloc[-1]
    if last_row["kdj_j"] > kdj_threshold:
        return None
    
    ret["kdj_j"] = last_row["kdj_j"]
    
    # 2. 检查双线系统
    add_zxdkx_to_dataframe(df, inplace=True)
    last_row = df.iloc[-1]
    last_close = last_row["close"]
    if last_close < last_row['z_yellow']:
        # 下破长期成本线，放弃
        return None
    if last_row["z_white"] < last_row['z_yellow']*0.985:
        # 双线死叉，放弃
        return None
    
    ret["is_between_white_yellow"] = (last_close >= last_row['z_yellow']) and (last_close < last_row['z_white'])
    ret["is_above_white"] = last_close >= last_row['z_white']
    
    # 3. 两个月内翻倍过的股票不考虑
    last_60_close = df["close"].iloc[-60:]
    last_60_max = last_60_close.max()
    last_60_min = last_60_close.min()
    if last_60_min <= 0:
        return None
    increase_pct = (last_60_max / last_60_min) - 1
    if increase_pct >= 1.0:
        return None
    
    search_window = 12 # 最近交易日内寻找放量突破
    consolidation_days = 10 # 放量前横盘天数
    consolidation_box_pct = 0.08 # 横盘箱体最大振幅比例
    explosion_vol_multiplier = 2 # 放量突破的成交量倍数
    explosion_pct = 0.04 # 放量突破的涨幅比例
    vol_ratio_threshold = 1.8 # 放量突破后红肥绿瘦的成交量比率
    
    # 4. 检查放量突破
    add_volume_ma_to_dataframe(df, periods=[consolidation_days], inplace=True)
    volume_ma_key = f'volume_ma_{consolidation_days}'
    volume_shift = df[volume_ma_key].shift(1)
    recent_data = df.iloc[-search_window:-2]
    ignition_mask = (
        (recent_data['close'] / recent_data['open'] > (1 + explosion_pct)) &
        (recent_data['volume'] / volume_shift > explosion_vol_multiplier)
    )
    if not ignition_mask.any():
        return None
    
    fire_pos = recent_data[ignition_mask].index[-1]
    fire_row = df.loc[fire_pos]
    fire_idx_loc = df.index.get_loc(fire_pos)
    
    ret["fire_date"] = fire_row['date']
    ret["fire_pct"] = round((fire_row['close'] / fire_row['open'] - 1) * 100, 2)
    
    # 5. 关键支撑：不跌破放量突破当天的最低价
    support_price = fire_row['low']
    if last_close < support_price:
        return None
    
    # 6. 检查爆发前横盘
    pre_fire_start = fire_idx_loc - consolidation_days
    if pre_fire_start < 0:
        pre_fire_start = 0
    
    pre_fire_data = df.iloc[pre_fire_start:fire_idx_loc] # 不能包含放量突破当天
    box_high = pre_fire_data['high'].max()
    box_low = pre_fire_data['low'].min()
    box_range_pct = (box_high - box_low) / box_low if box_low > 0 else 1.0
    # if box_range_pct > consolidation_box_pct:
    #     return None
    ret["box_range_pct"] = round(box_range_pct * 100, 2)
    
    # 7. 检查爆发后成交量（红肥绿瘦）
    up_vol, down_vol = up_down_volume(df, fire_pos)
    if down_vol <= 0:
        return None
    vol_ratio = up_vol / down_vol
    if vol_ratio < vol_ratio_threshold:
        return None
    ret["up_down_vol_ratio"] = round(vol_ratio, 2)
    
    return ret

def up_down_volume(df: pd.DataFrame, target_pos) -> tuple[float, float]:

    temp_df = df[['close', 'volume']].copy()
    temp_df['change'] = temp_df['close'].diff()
    
    df_after = temp_df.loc[temp_df.index >= target_pos]
    
    if len(df_after) < 1:
        return 0.0, 0.0
    
    up_vol = df_after[df_after['change'] > 0]['volume'].sum()
    down_vol = df_after[df_after['change'] < 0]['volume'].sum()
    
    return float(up_vol), float(down_vol)

def main():
    hunter = HuntMachine(max_workers=8)
    
    # Run the hunt
    results: list[HuntResult] = hunter.hunt(hunt_sf, min_bars=365)
    
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


if __name__ == "__main__":
    main()