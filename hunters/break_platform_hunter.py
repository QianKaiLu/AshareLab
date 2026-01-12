"""
突破平台买点识别器

形态特征：
1. 股价经历一段时间（10-30天）的横盘整理
2. 横盘区间波动幅度小（通常不超过10%）
3. 成交量在整理期间逐步萎缩
4. 突破当天放量明显（成交量至少是整理期均量的2倍）
5. 突破时收盘价站上平台上沿

分析体系：
- 形态分析：矩形整理突破
- 量价关系：缩量整理、放量突破
- 箱体理论：支撑压力转换

为什么是好的买点：
1. 横盘整理充分换手，洗盘彻底
2. 缩量整理说明抛压减轻，筹码稳定
3. 放量突破表示新资金介入，突破有效性高
4. 平台整理时间越长，突破后空间越大（时间换空间）
5. 突破后原压力位变支撑位，回踩可加仓

适用场景：
- 上升趋势中的中继整理
- 下跌后的底部平台突破
- 适合波段操作和中线持有

技术要点：
- 平台整理至少10天，但不超过60天（过长可能失败）
- 整理期间振幅越小越好（<8%最佳）
- 突破时放量越大越好（>2.5倍更佳）
- 突破后回踩不破平台上沿为确认信号
- 止损位设在平台下沿
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
from tools.log import get_analyze_logger
from indicators.volume_ma import add_volume_ma_to_dataframe

logger = get_analyze_logger()


def find_platform(df: pd.DataFrame, min_days: int = 10, max_days: int = 40,
                 max_amplitude: float = 0.10) -> Optional[Tuple[int, int, float, float]]:
    """
    识别横盘平台

    Args:
        df: 价格数据
        min_days: 平台最少天数
        max_days: 平台最多天数
        max_amplitude: 最大振幅（比例）

    Returns:
        (start_idx, end_idx, platform_low, platform_high) 或 None
    """
    # 从最近往前找平台
    for lookback in range(min_days, max_days + 1):
        if lookback > len(df) - 5:  # 至少需要5天来确认突破
            continue

        # 平台区间：[-lookback-5:-5]，最近5天用于判断突破
        platform_start_idx = len(df) - lookback - 5
        platform_end_idx = len(df) - 5

        if platform_start_idx < 0:
            continue

        platform_data = df.iloc[platform_start_idx:platform_end_idx]

        # 计算平台的高低点
        platform_high = platform_data['high'].max()
        platform_low = platform_data['low'].min()

        # 计算振幅
        if platform_low <= 0:
            continue
        amplitude = (platform_high - platform_low) / platform_low

        # 振幅符合要求
        if amplitude <= max_amplitude:
            # 检查是否真的横盘（使用标准差）
            price_std = platform_data['close'].std()
            price_mean = platform_data['close'].mean()
            if price_mean <= 0:
                continue

            # 变异系数（标准差/均值）应该较小
            cv = price_std / price_mean
            if cv < 0.05:  # 变异系数小于5%
                return platform_start_idx, platform_end_idx, platform_low, platform_high

    return None


def hunt_break_platform(df: pd.DataFrame) -> Optional[dict]:
    """
    突破平台买点识别函数

    Args:
        df: 包含OHLCV数据的DataFrame

    Returns:
        dict: 包含买点信息的字典，如果不符合条件则返回None
    """
    if df is None or df.empty or len(df) < 50:
        return None

    ret = {}

    # 1. 添加成交量均线
    add_volume_ma_to_dataframe(df, periods=[5, 10, 20], inplace=True)

    # 2. 寻找横盘平台
    platform_info = find_platform(df, min_days=10, max_days=40, max_amplitude=0.10)

    if platform_info is None:
        return None

    platform_start_idx, platform_end_idx, platform_low, platform_high = platform_info
    platform_days = platform_end_idx - platform_start_idx

    ret['platform_days'] = platform_days
    ret['platform_low'] = round(platform_low, 2)
    ret['platform_high'] = round(platform_high, 2)
    ret['platform_amplitude_pct'] = round((platform_high - platform_low) / platform_low * 100, 2)

    # 3. 计算平台中心线和上沿
    platform_mid = (platform_high + platform_low) / 2
    platform_upper = platform_high

    # 4. 检查整理期间的成交量特征
    platform_data = df.iloc[platform_start_idx:platform_end_idx]
    platform_vol_mean = platform_data['volume'].mean()
    platform_vol_trend = platform_data['volume'].iloc[-5:].mean() / platform_data['volume'].iloc[:5].mean()

    # 整理后期成交量应该萎缩（后期成交量 < 前期成交量）
    # ret['volume_shrink_ratio'] = round(platform_vol_trend, 2)

    # 5. 检测突破
    # 最近5天内是否有突破
    recent_data = df.iloc[-5:]
    breakout_found = False
    breakout_idx = None

    for i in range(len(recent_data)):
        row = recent_data.iloc[i]
        # 突破条件：收盘价站上平台上沿
        if row['close'] > platform_upper:
            breakout_idx = platform_end_idx + i
            breakout_found = True
            break

    if not breakout_found:
        return None

    breakout_row = df.iloc[breakout_idx]
    ret['breakout_date'] = breakout_row['date']
    ret['breakout_price'] = round(breakout_row['close'], 2)

    # 6. 检查突破时的成交量
    # 突破当天成交量应该明显放大
    breakout_volume = breakout_row['volume']
    volume_ratio = breakout_volume / platform_vol_mean if platform_vol_mean > 0 else 0

    # 至少是平台均量的1.8倍
    if volume_ratio < 1.8:
        return None

    ret['breakout_volume'] = int(breakout_volume)
    ret['platform_avg_volume'] = int(platform_vol_mean)
    ret['volume_surge_ratio'] = round(volume_ratio, 2)

    # 7. 检查突破的有效性
    last_row = df.iloc[-1]
    current_price = last_row['close']

    # 当前价格应该站稳在平台上沿之上（允许小幅回踩）
    if current_price < platform_upper * 0.97:
        return None

    ret['current_price'] = round(current_price, 2)
    ret['above_platform_pct'] = round((current_price / platform_upper - 1) * 100, 2)

    # 8. 突破后的涨幅不能过大（避免追高）
    gain_since_breakout = (current_price / breakout_row['close'] - 1) if breakout_row['close'] > 0 else 0
    if gain_since_breakout > 0.15:  # 涨幅超过15%
        return None

    ret['gain_since_breakout_pct'] = round(gain_since_breakout * 100, 2)

    # 9. 计算突破后的持续性（连续阳线数量）
    post_breakout_data = df.iloc[breakout_idx:]
    consecutive_up_days = 0
    for i in range(len(post_breakout_data)):
        if i == 0:
            consecutive_up_days = 1
            continue
        if post_breakout_data.iloc[i]['close'] > post_breakout_data.iloc[i-1]['close']:
            consecutive_up_days += 1
        else:
            break

    ret['consecutive_up_days'] = consecutive_up_days

    # 10. 检查均线支撑
    # 计算短期均线
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()

    last_ma5 = last_row['ma5']
    last_ma10 = last_row['ma10']

    # 当前价格最好在MA5和MA10之上
    above_ma5 = current_price >= last_ma5 * 0.98
    above_ma10 = current_price >= last_ma10 * 0.95

    ret['ma5'] = round(last_ma5, 2)
    ret['ma10'] = round(last_ma10, 2)
    ret['above_ma5'] = above_ma5
    ret['above_ma10'] = above_ma10

    # 至少要站在MA5之上
    if not above_ma5:
        return None

    # 11. 计算技术指标位置
    # 使用布林带判断突破强度
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['std20'] = df['close'].rolling(window=20).std()
    df['upper_band'] = df['ma20'] + 2 * df['std20']
    df['lower_band'] = df['ma20'] - 2 * df['std20']

    last_upper_band = last_row['upper_band']
    last_lower_band = last_row['lower_band']
    last_ma20 = last_row['ma20']

    # 当前价格相对布林带的位置
    if last_upper_band > last_lower_band:
        bb_position = (current_price - last_lower_band) / (last_upper_band - last_lower_band)
        ret['bollinger_position'] = round(bb_position, 2)

        # 如果已经突破上轨太多，可能过热
        if bb_position > 1.2:
            return None

    # 12. 风险收益评估
    # 止损位：平台下沿
    stop_loss = platform_low
    risk = current_price - stop_loss
    # 目标位：根据平台高度，向上投影（1:1或1:1.5）
    platform_height = platform_high - platform_low
    target_price = current_price + platform_height * 1.2
    reward = target_price - current_price

    risk_reward_ratio = reward / risk if risk > 0 else 0
    ret['stop_loss'] = round(stop_loss, 2)
    ret['target_price'] = round(target_price, 2)
    ret['risk_reward_ratio'] = round(risk_reward_ratio, 2)

    # 风险收益比至少要大于2
    if risk_reward_ratio < 2:
        return None

    # 13. 趋势背景检查
    # 检查突破前的趋势（平台之前是上涨还是下跌）
    if platform_start_idx >= 20:
        before_platform_data = df.iloc[platform_start_idx-20:platform_start_idx]
        before_avg_price = before_platform_data['close'].mean()
        platform_avg_price = platform_data['close'].mean()

        trend_before = 'uptrend' if platform_avg_price > before_avg_price * 1.05 else \
                      'downtrend' if platform_avg_price < before_avg_price * 0.95 else 'sideways'

        ret['trend_before_platform'] = trend_before

    return ret


def main():
    """测试函数"""
    from hunter.hunt_machine import HuntMachine, HuntResult
    from hunters.hunt_output import draw_hunt_results
    from datetime import datetime

    hunter = HuntMachine(max_workers=12)

    # 运行扫描
    results: list[HuntResult] = hunter.hunt(hunt_break_platform, min_bars=120)

    if not results:
        print("没有找到符合突破平台条件的股票。")
        return

    # 输出结果
    codes: list[str] = [result.code for result in results]

    print(f"\n🎉 找到 {len(results)} 只符合突破平台买点的股票:")
    for result in results:
        print(f"{result.code} {result.name}")
        print(f"  详情: {result.result_info}")

    print(f"\n股票代码列表: {','.join(codes)}")

    # 绘制图表（限制数量避免过多）
    if len(results) <= 10:
        date_in_title = datetime.now().strftime('%Y-%m-%d')
        draw_hunt_results(results, title="突破平台买点", desc=date_in_title, theme_name="dark_minimal")
    else:
        # 分批绘制
        batch_size = 6
        for i in range(0, min(len(results), 18), batch_size):
            batch_results = results[i:i + batch_size]
            date_in_title = datetime.now().strftime('%Y-%m-%d')
            draw_hunt_results(
                batch_results,
                title=f"突破平台买点 - 第{i//batch_size + 1}批",
                desc=date_in_title,
                theme_name="dark_minimal"
            )


if __name__ == "__main__":
    main()
