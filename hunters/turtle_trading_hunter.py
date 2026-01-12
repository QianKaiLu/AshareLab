"""
海龟交易法则买点识别器

形态特征：
1. 价格突破N日最高价（唐奇安通道）
2. 系统1：突破20日最高价（短期系统）
3. 系统2：突破55日最高价（长期系统）
4. 使用ATR（真实波动幅度）来设置止损
5. 突破时成交量放大确认

分析体系：
- 海龟交易法则（Turtle Trading System）
- 趋势跟踪策略
- 唐奇安通道突破系统
- ATR波动性管理

为什么是好的买点：
1. 海龟交易法则是历史上最成功的交易系统之一
2. 简单、机械、客观，易于执行，避免情绪干扰
3. 捕捉大级别趋势，盈亏比优秀
4. 使用ATR止损，适应不同股票的波动特性
5. 经过实战验证的完整交易系统

适用场景：
- 趋势明确的市场环境
- 突破重要阻力位
- 适合中长期持有
- 强调资金管理和风险控制

技术要点：
- 系统1（激进）：突破20日高点买入，跌破10日低点卖出
- 系统2（保守）：突破55日高点买入，跌破20日低点卖出
- 止损位：入场价 - 2倍ATR
- 可以使用金字塔加仓法则
- 严格执行止损，绝不抗单

经典原则：
1. 仓位管理：每次风险不超过账户的2%
2. 止损设置：使用ATR动态止损
3. 加仓规则：盈利0.5ATR后可以加仓
4. 相关性控制：相关品种合计仓位不超过限制
5. 长期持有：让利润奔跑，及时止损
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
from tools.log import get_analyze_logger
from indicators.volume_ma import add_volume_ma_to_dataframe

logger = get_analyze_logger()


def calculate_atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    计算ATR（Average True Range）真实波动幅度

    Args:
        df: 包含OHLC数据的DataFrame
        period: 计算周期

    Returns:
        ATR序列
    """
    # 计算真实波幅TR
    df['h_l'] = df['high'] - df['low']
    df['h_pc'] = abs(df['high'] - df['close'].shift(1))
    df['l_pc'] = abs(df['low'] - df['close'].shift(1))

    df['tr'] = df[['h_l', 'h_pc', 'l_pc']].max(axis=1)

    # 计算ATR（TR的指数移动平均）
    atr = df['tr'].rolling(window=period).mean()

    return atr


def calculate_donchian_channel(df: pd.DataFrame, period: int) -> Tuple[pd.Series, pd.Series]:
    """
    计算唐奇安通道（Donchian Channel）

    Args:
        df: 包含OHLC数据的DataFrame
        period: 周期

    Returns:
        (upper_band, lower_band): 上轨和下轨
    """
    upper_band = df['high'].rolling(window=period).max()
    lower_band = df['low'].rolling(window=period).min()

    return upper_band, lower_band


def hunt_turtle_trading(df: pd.DataFrame) -> Optional[dict]:
    """
    海龟交易法则买点识别函数

    Args:
        df: 包含OHLCV数据的DataFrame

    Returns:
        dict: 包含买点信息的字典，如果不符合条件则返回None
    """
    if df is None or df.empty or len(df) < 60:
        return None

    ret = {}

    # 1. 计算ATR（20日）
    df['atr20'] = calculate_atr(df, period=20)
    df['atr10'] = calculate_atr(df, period=10)

    # 2. 计算唐奇安通道
    # 系统1：20日通道（激进）
    df['dc20_high'], df['dc20_low'] = calculate_donchian_channel(df, period=20)
    df['dc10_low'] = calculate_donchian_channel(df, period=10)[1]  # 系统1的退出信号

    # 系统2：55日通道（保守）
    df['dc55_high'], df['dc55_low'] = calculate_donchian_channel(df, period=55)
    df['dc20_low_exit'] = calculate_donchian_channel(df, period=20)[1]  # 系统2的退出信号

    # 3. 添加成交量指标
    add_volume_ma_to_dataframe(df, periods=[20, 55], inplace=True)

    # 4. 检测突破信号
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    current_price = last_row['close']

    # 系统1突破：当前价格 > 20日最高价
    system1_breakout = current_price > prev_row['dc20_high']

    # 系统2突破：当前价格 > 55日最高价
    system2_breakout = current_price > prev_row['dc55_high']

    # 至少要有一个系统发出信号
    if not (system1_breakout or system2_breakout):
        return None

    ret['system1_breakout'] = system1_breakout
    ret['system2_breakout'] = system2_breakout
    ret['breakout_system'] = 'both' if (system1_breakout and system2_breakout) else \
                             'system1' if system1_breakout else 'system2'

    # 记录通道值
    ret['dc20_high'] = round(prev_row['dc20_high'], 2)
    ret['dc55_high'] = round(prev_row['dc55_high'], 2)
    ret['current_price'] = round(current_price, 2)

    # 5. 检查突破的有效性
    # 突破当天应该是阳线，且收盘价接近当天最高价
    is_bullish_candle = last_row['close'] > last_row['open']
    close_near_high = (last_row['high'] - last_row['close']) / (last_row['high'] - last_row['low']) < 0.3 \
                      if (last_row['high'] - last_row['low']) > 0 else False

    ret['is_bullish_candle'] = is_bullish_candle
    ret['close_near_high'] = close_near_high

    # 至少要是阳线
    if not is_bullish_candle:
        return None

    # 6. 成交量确认
    # 突破时成交量应该放大
    volume_ratio_20 = last_row['volume'] / last_row['volume_ma_20'] if last_row['volume_ma_20'] > 0 else 0

    ret['volume_ratio'] = round(volume_ratio_20, 2)
    ret['current_volume'] = int(last_row['volume'])
    ret['volume_ma_20'] = int(last_row['volume_ma_20'])

    # 成交量至少是均量的1.2倍
    if volume_ratio_20 < 1.2:
        return None

    # 7. 计算ATR和止损位
    atr20 = last_row['atr20']
    atr10 = last_row['atr10']

    # 海龟法则：止损设在入场价下方2倍ATR
    stop_loss_turtle = current_price - 2 * atr20

    # 另一种止损：使用唐奇安通道下轨
    stop_loss_dc = last_row['dc10_low'] if system1_breakout else last_row['dc20_low_exit']

    # 使用两者中较高的一个作为止损（更保守）
    stop_loss = max(stop_loss_turtle, stop_loss_dc)

    ret['atr20'] = round(atr20, 2)
    ret['atr_pct'] = round(atr20 / current_price * 100, 2) if current_price > 0 else 0
    ret['stop_loss_turtle'] = round(stop_loss_turtle, 2)
    ret['stop_loss_dc'] = round(stop_loss_dc, 2)
    ret['stop_loss'] = round(stop_loss, 2)

    # 8. 计算风险和仓位
    # 风险：当前价格到止损位的距离
    risk_per_share = current_price - stop_loss
    risk_pct = risk_per_share / current_price if current_price > 0 else 0

    ret['risk_per_share'] = round(risk_per_share, 2)
    ret['risk_pct'] = round(risk_pct * 100, 2)

    # 风险不能太大（超过8%则放弃）
    if risk_pct > 0.08:
        return None

    # 海龟法则：每次风险账户的2%
    # 这里只计算理论仓位，不涉及实际账户
    # 仓位 = (账户 * 2%) / 风险每股
    # 示例：假设账户10万，则 position_size = 100000 * 0.02 / risk_per_share
    ret['turtle_risk_unit'] = '2% of account / risk_per_share'

    # 9. 计算潜在目标位
    # 目标1：1倍ATR（短期目标）
    target1 = current_price + 1 * atr20
    # 目标2：3倍ATR（中期目标）
    target2 = current_price + 3 * atr20
    # 目标3：5倍ATR（长期目标）
    target3 = current_price + 5 * atr20

    ret['target1'] = round(target1, 2)
    ret['target2'] = round(target2, 2)
    ret['target3'] = round(target3, 2)

    # 风险收益比（使用中期目标）
    reward = target2 - current_price
    risk_reward_ratio = reward / risk_per_share if risk_per_share > 0 else 0

    ret['risk_reward_ratio'] = round(risk_reward_ratio, 2)

    # 风险收益比至少要大于3（海龟法则追求大盈亏比）
    if risk_reward_ratio < 3:
        return None

    # 10. 检查通道宽度（波动性）
    # 通道宽度 = (上轨 - 下轨) / 中线
    if system1_breakout:
        channel_width = (last_row['dc20_high'] - last_row['dc20_low']) / \
                       ((last_row['dc20_high'] + last_row['dc20_low']) / 2) \
                       if (last_row['dc20_high'] + last_row['dc20_low']) > 0 else 0
        ret['channel_width_pct'] = round(channel_width * 100, 2)

    # 11. 计算突破强度
    # 突破幅度：当前价格超出通道上轨的百分比
    if system1_breakout:
        breakout_strength = (current_price - prev_row['dc20_high']) / prev_row['dc20_high'] \
                           if prev_row['dc20_high'] > 0 else 0
    else:
        breakout_strength = (current_price - prev_row['dc55_high']) / prev_row['dc55_high'] \
                           if prev_row['dc55_high'] > 0 else 0

    ret['breakout_strength_pct'] = round(breakout_strength * 100, 2)

    # 突破强度不能太弱（至少0.5%），也不能太强（超过5%可能追高）
    if breakout_strength < 0.005 or breakout_strength > 0.05:
        return None

    # 12. 趋势确认：使用均线
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma55'] = df['close'].rolling(window=55).mean()

    ma20 = last_row['ma20']
    ma55 = last_row['ma55']

    # 价格应该在长期均线之上
    above_ma55 = current_price > ma55 * 0.95

    ret['ma20'] = round(ma20, 2)
    ret['ma55'] = round(ma55, 2)
    ret['above_ma55'] = above_ma55

    # 如果是系统2突破，必须在MA55之上
    if system2_breakout and not above_ma55:
        return None

    # 13. 检查前期是否有假突破
    # 查看最近是否有突破后回撤的情况
    recent_10 = df.iloc[-10:-1]
    false_breakout_count = 0

    for i in range(len(recent_10) - 1):
        # 如果某天突破了通道，但后续又跌回通道内
        if system1_breakout:
            if recent_10.iloc[i]['close'] > recent_10.iloc[i]['dc20_high'] and \
               recent_10.iloc[i+1]['close'] < recent_10.iloc[i]['dc20_high']:
                false_breakout_count += 1

    # 如果最近有多次假突破，则谨慎
    ret['false_breakout_count'] = false_breakout_count
    if false_breakout_count >= 2:
        return None

    # 14. 计算ADX（趋势强度指标）- 简化版
    # 使用价格变化率来近似
    price_changes = df['close'].pct_change().iloc[-20:]
    positive_changes = price_changes[price_changes > 0].sum()
    negative_changes = abs(price_changes[price_changes < 0].sum())

    if positive_changes + negative_changes > 0:
        directional_movement = abs(positive_changes - negative_changes) / (positive_changes + negative_changes)
        ret['trend_strength'] = round(directional_movement, 2)

        # 趋势强度应该较高（>0.3）
        if directional_movement < 0.3:
            return None

    # 15. 加仓位置计算（海龟法则的金字塔加仓）
    # 第一次加仓：价格上涨0.5个ATR
    add_position1 = current_price + 0.5 * atr20
    # 第二次加仓：价格上涨1个ATR
    add_position2 = current_price + 1.0 * atr20
    # 第三次加仓：价格上涨1.5个ATR
    add_position3 = current_price + 1.5 * atr20

    ret['add_position1'] = round(add_position1, 2)
    ret['add_position2'] = round(add_position2, 2)
    ret['add_position3'] = round(add_position3, 2)

    # 16. 市场环境评估
    # 计算最近N天的趋势方向
    trend_20 = (last_row['ma20'] - df.iloc[-20]['ma20']) / df.iloc[-20]['ma20'] \
               if df.iloc[-20]['ma20'] > 0 else 0

    ret['trend_20d_pct'] = round(trend_20 * 100, 2)

    # 海龟法则适合趋势市场，如果市场震荡（趋势弱）则不适合
    if abs(trend_20) < 0.05:  # 20天趋势小于5%，可能是震荡市
        return None

    # 17. 波动率检查
    # ATR占价格的比例，反映波动率
    volatility = atr20 / current_price if current_price > 0 else 0
    ret['volatility'] = round(volatility, 2)

    # 波动率太小（<1%）或太大（>8%）都不适合
    if volatility < 0.01 or volatility > 0.08:
        return None

    # 18. 综合评分
    score = 0

    # 双系统突破
    if system1_breakout and system2_breakout:
        score += 3

    # 收盘价接近最高价
    if close_near_high:
        score += 2

    # 成交量大幅放大
    if volume_ratio_20 > 1.5:
        score += 2

    # 趋势强劲
    if ret.get('trend_strength', 0) > 0.5:
        score += 2

    # 站在长期均线之上
    if above_ma55:
        score += 2

    # 风险收益比优秀
    if risk_reward_ratio > 4:
        score += 2

    ret['turtle_score'] = score

    # 总分至少要6分
    if score < 6:
        return None

    return ret


def main():
    """测试函数"""
    from hunter.hunt_machine import HuntMachine, HuntResult
    from hunters.hunt_output import draw_hunt_results
    from datetime import datetime

    hunter = HuntMachine(max_workers=12)

    # 运行扫描
    results: list[HuntResult] = hunter.hunt(hunt_turtle_trading, min_bars=120)

    if not results:
        print("没有找到符合海龟交易法则条件的股票。")
        return

    # 输出结果
    codes: list[str] = [result.code for result in results]

    print(f"\n🎉 找到 {len(results)} 只符合海龟交易法则买点的股票:")
    for result in results:
        print(f"{result.code} {result.name}")
        print(f"  详情: {result.result_info}")
        print(f"  系统: {result.result_info.get('breakout_system', 'N/A')}")
        print(f"  止损: {result.result_info.get('stop_loss', 'N/A')}")
        print(f"  目标: {result.result_info.get('target2', 'N/A')}")

    print(f"\n股票代码列表: {','.join(codes)}")

    # 绘制图表（限制数量避免过多）
    if len(results) <= 10:
        date_in_title = datetime.now().strftime('%Y-%m-%d')
        draw_hunt_results(results, title="海龟交易法则买点", desc=date_in_title, theme_name="dark_minimal")
    else:
        # 分批绘制
        batch_size = 6
        for i in range(0, min(len(results), 18), batch_size):
            batch_results = results[i:i + batch_size]
            date_in_title = datetime.now().strftime('%Y-%m-%d')
            draw_hunt_results(
                batch_results,
                title=f"海龟交易法则买点 - 第{i//batch_size + 1}批",
                desc=date_in_title,
                theme_name="dark_minimal"
            )


if __name__ == "__main__":
    main()
