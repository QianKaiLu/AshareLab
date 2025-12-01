import pandas as pd
import numpy as np
from typing import Optional, Dict, Any

def wyckoff_analyze(df: pd.DataFrame, 
                   range_days: int = 40,     # 吸筹区间长度
                   spring_window: int = 5,   # 弹簧发生窗口
                   test_window: int = 10,    # 测试窗口
                   min_volume_ratio: float = 0.6,  # 缩量比例阈值
                   breakout_threshold: float = 0.02) -> Optional[Dict[str, Any]]:
    """
    威科夫高胜率买点检测：主要识别 Spring 和 Secondary Test 两类信号。
    
    Args:
        df: 包含 'open', 'high', 'low', 'close', 'volume' 的 DataFrame，按日期升序
        range_days: 定义为吸筹区间的天数（通常 30-60 天）
        spring_window: 最近N天内是否有弹簧形态
        test_window: 最近N天内是否完成支撑测试
        min_volume_ratio: 当前成交量低于均量多少视为缩量（如 0.6 表示 <60%）
        breakout_threshold: 突破幅度阈值（如 2%）
        
    Returns:
        如果匹配任一高胜率买点，则返回详情；否则返回 None
    """
    if len(df) < range_days + 20:
        return None

    recent = df.iloc[-spring_window:]         # 最近观察期
    base_period = df.iloc[-range_days:]       # 吸筹基底周期
    volume_ma20 = df['volume'].rolling(20).mean().iloc[-1]

    latest = df.iloc[-1]
    prev_few = df.iloc[-5:]

    # ——————————————————————————————
    # Step 1: 确定交易区间（Trading Range）
    # ——————————————————————————————
    support = base_period['low'].min()
    resistance = base_period['high'].max()
    range_width = (resistance - support) / support

    if range_width < 0.05:  # 区间太窄无意义
        return None
    if range_width > 0.3:   # 波动太大，可能不是吸筹而是洗盘
        return None

    # ——————————————————————————————
    # Step 2: 检测 "Spring"（弹簧）—— 假破位后快速回收
    # 条件：
    #   a. 最低价跌破支撑（< support）
    #   b. 收盘价迅速回到支撑之上（收盘 > support）
    #   c. 发生在最近几天
    #   d. 破位时成交量较小（非恐慌性抛售）
    # ——————————————————————————————
    spring_detected = False
    spring_info = {}

    for i in range(len(recent)):
        row = recent.iloc[i]
        low_broke = row['low'] < support * 0.98  # 轻微破位即可
        close_held = row['close'] > support       # 收盘收回支撑区
        vol_low = row['volume'] < volume_ma20 * min_volume_ratio * 1.2  # 不显著放量

        if low_broke and close_held and vol_low:
            days_ago = len(df) - range_days + i
            spring_detected = True
            spring_info = {
                "type": "Spring",
                "date": row.name if isinstance(row.name, str) else str(row.name),
                "spring_price": round(row['low'], 2),
                "close_reclaim": round(row['close'], 2),
                "support": round(support, 2),
                "vol_ratio": round(row['volume'] / volume_ma20, 2)
            }
            break

    # ——————————————————————————————
    # Step 3: 检测 "Secondary Test"（二次测试）
    # 条件：
    #   a. 在吸筹后期有一次对支撑的重新测试
    #   b. 测试时成交量明显萎缩
    #   c. 价格未破支撑，或轻微破后拉回（shallow spring）
    #   d. 近期出现止跌K线（十字星、锤子线、阳包阴等）
    # ——————————————————————————————
    test_detected = False
    test_info = {}
    test_period = df.iloc[-test_window:]

    for i in range(len(test_period)):
        row = test_period.iloc[i]
        near_support = abs(row['low'] - support) / support < 0.03
        vol_shrink = row['volume'] < volume_ma20 * min_volume_ratio
        close_above_open = row['close'] >= row['open']
        small_body = (abs(row['close'] - row['open']) / (row['high'] - row['low'] + 1e-6)) < 0.3

        # 锤子线判断（下影线长，实体小，位置低）
        lower_shadow = row['low'] == row['close'] or row['low'] == row['open']
        long_lower = (row['open'] - row['low']) > 2 * (row['high'] - row['open']) if row['close'] >= row['open'] else \
                     (row['close'] - row['low']) > 2 * (row['high'] - row['close'])

        if near_support and vol_shrink:
            if close_above_open and (long_lower or not small_body):
                test_detected = True
                test_info = {
                    "type": "Secondary Test",
                    "date": row.name if isinstance(row.name, str) else str(row.name),
                    "test_price": round(row['low'], 2),
                    "support": round(support, 2),
                    "vol_ratio": round(row['volume'] / volume_ma20, 2),
                    "pattern": "Hammer" if long_lower else "Bullish Rejection"
                }
                break

    # ——————————————————————————————
    # Step 4: 可选增强：真实突破确认（增加置信度）
    # ——————————————————————————————
    breakout_confirmed = False
    if latest['close'] > resistance * (1 + breakout_threshold) and \
       latest['volume'] > volume_ma20 * 1.3:
        breakout_confirmed = True

    # ——————————————————————————————
    # Step 5: 综合判断（满足任意一个高胜率模式）
    # ——————————————————————————————
    if not (spring_detected or test_detected):
        return None

    # 可加入基本趋势过滤：例如 EMA20 > EMA50（中期多头）
    try:
        ema20 = df['close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        uptrend = ema20 > ema50
    except:
        uptrend = True  # 若不够数据，默认通过

    result = {
        "setup": "Wyckoff High-Probability Buy Setup",
        "current_price": round(latest['close'], 2),
        "support_zone": [round(support * 0.98, 2), round(support * 1.02, 2)],
        "resistance_zone": [round(resistance * 0.98, 2), round(resistance * 1.02, 2)],
        "base_duration": range_days,
        "uptrend": uptrend,
        "breakout_confirmed": breakout_confirmed
    }

    if spring_detected:
        result.update(spring_info)
    elif test_detected:
        result.update(test_info)

    return result
