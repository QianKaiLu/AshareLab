"""
锤子线反转买点识别器

形态特征：
1. K线实体很小（上影线+实体 < 整根K线的30%）
2. 下影线很长（至少是实体的2倍，最好3倍以上）
3. 上影线很短或没有
4. 出现在下跌趋势或重要支撑位
5. 最好伴随成交量放大

分析体系：
- K线形态学：单根K线反转形态
- 日本蜡烛图技术：锤子线(Hammer)和倒锤子线(Inverted Hammer)
- 支撑压力理论：出现在支撑位效果最好

为什么是好的买点：
1. 长下影线表示盘中跌至低位后被拉起，买盘强劲
2. 小实体说明收盘价接近最高价，多头控盘
3. 反映多空力量转换：空头打压后多头成功反击
4. 在重要支撑位出现时可靠性更高
5. 心理意义：恐慌性抛盘被消化，底部确认

适用场景：
- 下跌趋势的底部反转
- 上升趋势中的回调支撑
- 重要支撑位（前期低点、均线、整数关口）
- 适合短线反弹和波段操作

技术要点：
- 下影线越长越好（至少是实体的2倍）
- 实体越小越好（阳线阴线都可以，阳线更佳）
- 成交量放大确认买盘活跃
- 需要次日阳线确认反转有效
- 止损位在锤子线最低点下方
"""

import pandas as pd
import numpy as np
from typing import Optional
from tools.log import get_analyze_logger
from indicators.macd import add_macd_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe

logger = get_analyze_logger()


def is_hammer_candle(row: pd.Series, prev_row: pd.Series = None) -> dict:
    """
    判断是否是锤子线形态

    Args:
        row: 当天的K线数据
        prev_row: 前一天的K线数据（可选）

    Returns:
        dict: 包含锤子线特征的字典，如果不是锤子线则返回空字典
    """
    open_price = row['open']
    close_price = row['close']
    high_price = row['high']
    low_price = row['low']

    # 计算实体、上影线、下影线
    body = abs(close_price - open_price)
    upper_shadow = high_price - max(open_price, close_price)
    lower_shadow = min(open_price, close_price) - low_price
    total_range = high_price - low_price

    if total_range <= 0 or body <= 0:
        return {}

    # 锤子线特征判断
    # 1. 下影线至少是实体的2倍
    if lower_shadow < body * 2:
        return {}

    # 2. 上影线很短（不超过实体的0.5倍，最好没有）
    if upper_shadow > body * 0.5:
        return {}

    # 3. 实体在K线上部（实体+上影线占整个K线的比例小于40%）
    upper_part = body + upper_shadow
    if upper_part > total_range * 0.4:
        return {}

    # 4. 下影线占整根K线的比例（至少60%）
    lower_ratio = lower_shadow / total_range
    if lower_ratio < 0.6:
        return {}

    # 计算锤子线的质量得分
    # 下影线越长、实体越小、上影线越短 -> 得分越高
    body_ratio = body / total_range
    upper_ratio = upper_shadow / total_range

    # 锤子线强度：下影线比例 - 实体比例 - 上影线比例
    hammer_strength = lower_ratio - body_ratio - upper_ratio

    # 判断是阳线还是阴线
    is_bullish = close_price > open_price

    return {
        'is_hammer': True,
        'hammer_strength': hammer_strength,
        'lower_shadow_ratio': lower_ratio,
        'body_ratio': body_ratio,
        'upper_shadow_ratio': upper_ratio,
        'is_bullish': is_bullish,
        'lower_shadow': lower_shadow,
        'body': body,
        'total_range': total_range
    }


def hunt_hammer_reversal(df: pd.DataFrame) -> Optional[dict]:
    """
    锤子线反转买点识别函数

    Args:
        df: 包含OHLCV数据的DataFrame

    Returns:
        dict: 包含买点信息的字典，如果不符合条件则返回None
    """
    if df is None or df.empty or len(df) < 30:
        return None

    ret = {}

    # 1. 添加均线和成交量指标
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()

    add_volume_ma_to_dataframe(df, periods=[5, 10], inplace=True)
    add_macd_to_dataframe(df, inplace=True)

    # 2. 检查最近1-3天内是否出现锤子线
    hammer_found = False
    hammer_idx = None
    hammer_info = {}

    for i in range(-1, -4, -1):  # 检查最近3天
        if abs(i) > len(df):
            break

        curr_row = df.iloc[i]
        prev_row = df.iloc[i-1] if i > -len(df) else None

        hammer_result = is_hammer_candle(curr_row, prev_row)

        if hammer_result.get('is_hammer', False):
            hammer_found = True
            hammer_idx = i
            hammer_info = hammer_result
            break

    if not hammer_found:
        return None

    hammer_row = df.iloc[hammer_idx]
    last_row = df.iloc[-1]

    ret['hammer_date'] = hammer_row['date']
    ret['hammer_price'] = round(hammer_row['close'], 2)
    ret['hammer_low'] = round(hammer_row['low'], 2)
    ret['hammer_strength'] = round(hammer_info['hammer_strength'], 3)
    ret['is_bullish_hammer'] = hammer_info['is_bullish']
    ret['lower_shadow_pct'] = round(hammer_info['lower_shadow_ratio'] * 100, 1)

    # 3. 确认锤子线出现在下跌过程中或支撑位
    # 检查锤子线之前是否有下跌
    if hammer_idx < -10:  # 如果锤子线不是最近几天，则需要更严格的检查
        return None

    # 计算锤子线前10天的价格变化
    pre_hammer_start = len(df) + hammer_idx - 10
    if pre_hammer_start < 0:
        pre_hammer_start = 0

    pre_hammer_data = df.iloc[pre_hammer_start:len(df) + hammer_idx]
    if len(pre_hammer_data) > 0:
        pre_high = pre_hammer_data['close'].max()
        pre_low = pre_hammer_data['close'].min()
        hammer_price = hammer_row['close']

        # 锤子线应该出现在相对低位
        # 当前价格接近前期低点
        price_position = (hammer_price - pre_low) / (pre_high - pre_low) if pre_high > pre_low else 0.5

        if price_position > 0.5:  # 如果价格位置在前期区间的上半部分，则不够低
            return None

        ret['price_position_in_range'] = round(price_position, 2)

        # 锤子线前是否有明显下跌
        decline_before = (pre_high - hammer_price) / pre_high if pre_high > 0 else 0
        ret['decline_before_hammer_pct'] = round(decline_before * 100, 2)

        # 下跌幅度应该至少有5%
        if decline_before < 0.05:
            return None

    # 4. 检查锤子线后是否有确认（后续K线应该向上）
    if hammer_idx < -1:  # 如果锤子线不是昨天
        # 检查锤子线之后的K线是否确认反转
        post_hammer_data = df.iloc[len(df) + hammer_idx + 1:]
        if len(post_hammer_data) > 0:
            # 后续应该有阳线
            up_days = sum(post_hammer_data['close'] > post_hammer_data['open'])
            total_days = len(post_hammer_data)
            up_ratio = up_days / total_days if total_days > 0 else 0

            ret['confirm_up_days'] = up_days
            ret['confirm_up_ratio'] = round(up_ratio, 2)

            # 至少50%的确认K线是阳线
            if up_ratio < 0.5:
                return None

    # 5. 当前价格应该高于锤子线的低点（确认支撑有效）
    current_price = last_row['close']
    hammer_low = hammer_row['low']

    if current_price < hammer_low * 1.01:  # 当前价格应该高于锤子线低点1%以上
        return None

    ret['current_price'] = round(current_price, 2)
    ret['above_hammer_low_pct'] = round((current_price / hammer_low - 1) * 100, 2)

    # 6. 当前价格不能涨幅过大（避免追高）
    gain_since_hammer = (current_price / hammer_row['close'] - 1) if hammer_row['close'] > 0 else 0
    if gain_since_hammer > 0.10:  # 涨幅超过10%
        return None

    ret['gain_since_hammer_pct'] = round(gain_since_hammer * 100, 2)

    # 7. 成交量确认
    # 锤子线当天成交量应该放大
    hammer_volume = hammer_row['volume']
    hammer_vol_ma = df.iloc[len(df) + hammer_idx - 10:len(df) + hammer_idx]['volume'].mean()

    if hammer_vol_ma > 0:
        hammer_vol_ratio = hammer_volume / hammer_vol_ma
        ret['hammer_volume_ratio'] = round(hammer_vol_ratio, 2)

        # 成交量至少是前期均量的0.8倍（允许缩量，但不能太小）
        # 不强制要求放量，因为锤子线可能在缩量中出现

    # 8. 检查是否在重要支撑位
    # MA20, MA60可能是支撑
    near_ma20 = abs(hammer_row['low'] - hammer_row['ma20']) / hammer_row['ma20'] if hammer_row['ma20'] > 0 else 1
    ret['near_ma20'] = near_ma20 < 0.03  # 距离MA20在3%以内

    # 或者接近前期低点
    recent_lows = df.iloc[pre_hammer_start:len(df) + hammer_idx]['low']
    if len(recent_lows) > 5:
        lowest = recent_lows.min()
        near_prev_low = abs(hammer_row['low'] - lowest) / lowest if lowest > 0 else 1
        ret['near_prev_low'] = near_prev_low < 0.02  # 距离前期低点在2%以内

    # 9. MACD辅助确认
    # MACD在低位或即将金叉
    last_macd_dif = last_row['macd_dif']
    last_macd_dea = last_row['macd_dea']

    ret['macd_dif'] = round(last_macd_dif, 4)
    ret['macd_dea'] = round(last_macd_dea, 4)

    # MACD在低位（负值但绝对值不大）或即将金叉
    macd_low = last_macd_dif < 0 and abs(last_macd_dif) < 0.5
    macd_approaching = last_macd_dif < last_macd_dea and (last_macd_dea - last_macd_dif) < 0.1

    ret['macd_favorable'] = macd_low or macd_approaching

    # 10. 风险收益评估
    # 止损位：锤子线最低点下方2%
    stop_loss = hammer_low * 0.98
    risk = current_price - stop_loss

    # 目标位：根据锤子线的长度，向上投影
    hammer_height = hammer_row['high'] - hammer_row['low']
    target_price = current_price + hammer_height * 1.5  # 1.5倍的锤子线高度

    reward = target_price - current_price
    risk_reward_ratio = reward / risk if risk > 0 else 0

    ret['stop_loss'] = round(stop_loss, 2)
    ret['target_price'] = round(target_price, 2)
    ret['risk_reward_ratio'] = round(risk_reward_ratio, 2)

    # 风险收益比至少要大于2
    if risk_reward_ratio < 2:
        return None

    # 11. 综合评分
    score = 0

    # 锤子线强度
    if hammer_info['hammer_strength'] > 0.5:
        score += 2
    elif hammer_info['hammer_strength'] > 0.4:
        score += 1

    # 是否是阳锤（阳线的锤子线更强）
    if hammer_info['is_bullish']:
        score += 1

    # 是否在支撑位
    if ret.get('near_ma20', False) or ret.get('near_prev_low', False):
        score += 2

    # MACD是否有利
    if ret.get('macd_favorable', False):
        score += 1

    # 风险收益比
    if risk_reward_ratio > 3:
        score += 2
    elif risk_reward_ratio > 2.5:
        score += 1

    ret['total_score'] = score

    # 总分至少要4分
    if score < 4:
        return None

    return ret


def main():
    """测试函数"""
    from hunter.hunt_machine import HuntMachine, HuntResult
    from hunters.hunt_output import draw_hunt_results
    from datetime import datetime

    hunter = HuntMachine(max_workers=12)

    # 运行扫描
    results: list[HuntResult] = hunter.hunt(hunt_hammer_reversal, min_bars=60)

    if not results:
        print("没有找到符合锤子线反转条件的股票。")
        return

    # 输出结果
    codes: list[str] = [result.code for result in results]

    print(f"\n🎉 找到 {len(results)} 只符合锤子线反转买点的股票:")
    for result in results:
        print(f"{result.code} {result.name}")
        print(f"  详情: {result.result_info}")

    print(f"\n股票代码列表: {','.join(codes)}")

    # 绘制图表（限制数量避免过多）
    if len(results) <= 10:
        date_in_title = datetime.now().strftime('%Y-%m-%d')
        draw_hunt_results(results, title="锤子线反转买点", desc=date_in_title, theme_name="dark_minimal")
    else:
        # 分批绘制
        batch_size = 6
        for i in range(0, min(len(results), 18), batch_size):
            batch_results = results[i:i + batch_size]
            date_in_title = datetime.now().strftime('%Y-%m-%d')
            draw_hunt_results(
                batch_results,
                title=f"锤子线反转买点 - 第{i//batch_size + 1}批",
                desc=date_in_title,
                theme_name="dark_minimal"
            )


if __name__ == "__main__":
    main()
