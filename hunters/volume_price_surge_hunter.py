"""
量价齐升买点识别器

形态特征：
1. 价格连续上涨（至少3天）
2. 成交量同步放大（量增价涨）
3. 价格创近期新高或突破重要压力位
4. 成交量呈现递增态势
5. 均线多头排列或即将形成

分析体系：
- 量价关系理论：量是价的先行指标
- 道氏理论：成交量验证价格趋势
- OBV能量潮指标：资金流向

为什么是好的买点：
1. 量价齐升是最经典的强势信号，表示趋势健康
2. 成交量放大说明资金持续流入，有主力参与
3. 量增价涨确认突破有效性，避免假突破
4. 符合"价涨量增"的健康市场规律
5. 表示市场共识强，多头占优

适用场景：
- 突破关键压力位时
- 上升趋势的加速阶段
- 底部启动的初期
- 适合追涨和趋势跟踪

技术要点：
- 至少连续3天量增价涨
- 成交量要明显放大（至少1.5倍均量）
- 价格涨幅不能过大（避免追高）
- 最好配合均线多头排列
- OBV指标同步创新高更佳
"""

import pandas as pd
import numpy as np
from typing import Optional
from tools.log import get_analyze_logger
from indicators.macd import add_macd_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe

logger = get_analyze_logger()


def calculate_obv(df: pd.DataFrame) -> pd.Series:
    """
    计算OBV（On Balance Volume）能量潮指标

    Args:
        df: 包含close和volume的DataFrame

    Returns:
        OBV序列
    """
    obv = [0]
    for i in range(1, len(df)):
        if df.iloc[i]['close'] > df.iloc[i-1]['close']:
            obv.append(obv[-1] + df.iloc[i]['volume'])
        elif df.iloc[i]['close'] < df.iloc[i-1]['close']:
            obv.append(obv[-1] - df.iloc[i]['volume'])
        else:
            obv.append(obv[-1])

    return pd.Series(obv, index=df.index)


def calculate_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    计算VWAP（Volume Weighted Average Price）成交量加权平均价

    Args:
        df: 包含价格和成交量的DataFrame
        period: 计算周期

    Returns:
        VWAP序列
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    vwap = (typical_price * df['volume']).rolling(window=period).sum() / \
           df['volume'].rolling(window=period).sum()
    return vwap


def hunt_volume_price_surge(df: pd.DataFrame) -> Optional[dict]:
    """
    量价齐升买点识别函数

    Args:
        df: 包含OHLCV数据的DataFrame

    Returns:
        dict: 包含买点信息的字典，如果不符合条件则返回None
    """
    if df is None or df.empty or len(df) < 40:
        return None

    ret = {}

    # 1. 添加均线指标
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma60'] = df['close'].rolling(window=60).mean()

    # 2. 添加成交量均线
    add_volume_ma_to_dataframe(df, periods=[5, 10, 20], inplace=True)

    # 3. 计算OBV指标
    df['obv'] = calculate_obv(df)

    # 4. 计算VWAP
    df['vwap20'] = calculate_vwap(df, period=20)

    # 5. 添加MACD
    add_macd_to_dataframe(df, inplace=True)

    # 6. 检测量价齐升
    # 查看最近3-5天的情况
    lookback = 5
    recent_data = df.iloc[-lookback:]

    # 统计量增价涨的天数
    surge_days = 0
    consecutive_surge_days = 0

    for i in range(1, len(recent_data)):
        curr_row = recent_data.iloc[i]
        prev_row = recent_data.iloc[i-1]

        # 价涨
        price_up = curr_row['close'] > prev_row['close']
        # 量增
        volume_up = curr_row['volume'] > prev_row['volume']

        if price_up and volume_up:
            surge_days += 1
            # 检查连续天数（从最后一天往前）
            if i == len(recent_data) - 1:
                consecutive_surge_days = 1
                for j in range(len(recent_data) - 2, 0, -1):
                    c = recent_data.iloc[j]
                    p = recent_data.iloc[j-1]
                    if c['close'] > p['close'] and c['volume'] > p['volume']:
                        consecutive_surge_days += 1
                    else:
                        break

    # 至少要有3天量增价涨，且最近至少连续2天
    if surge_days < 3 or consecutive_surge_days < 2:
        return None

    ret['surge_days_in_5'] = surge_days
    ret['consecutive_surge_days'] = consecutive_surge_days

    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    # 7. 成交量放大检查
    # 最近的成交量应该明显高于均量
    volume_ratio_vs_ma20 = last_row['volume'] / last_row['volume_ma_20'] if last_row['volume_ma_20'] > 0 else 0
    volume_ratio_vs_ma5 = last_row['volume'] / last_row['volume_ma_5'] if last_row['volume_ma_5'] > 0 else 0

    # 至少是20日均量的1.2倍
    if volume_ratio_vs_ma20 < 1.2:
        return None

    ret['volume_vs_ma20'] = round(volume_ratio_vs_ma20, 2)
    ret['volume_vs_ma5'] = round(volume_ratio_vs_ma5, 2)
    ret['current_volume'] = int(last_row['volume'])
    ret['volume_ma_20'] = int(last_row['volume_ma_20'])

    # 8. 成交量递增检查
    # 最近3天的成交量应该呈递增趋势
    recent_3_volumes = df['volume'].iloc[-3:].values
    volume_increasing = all(recent_3_volumes[i] <= recent_3_volumes[i+1]
                           for i in range(len(recent_3_volumes)-1))
    ret['volume_increasing'] = volume_increasing

    # 9. 价格涨幅检查
    # 计算最近5天的累计涨幅
    price_5_days_ago = df['close'].iloc[-5]
    current_price = last_row['close']
    gain_5d = (current_price / price_5_days_ago - 1) if price_5_days_ago > 0 else 0

    ret['gain_5d_pct'] = round(gain_5d * 100, 2)
    ret['current_price'] = round(current_price, 2)

    # 涨幅应该在合理范围（3%-15%），太小说明不够强，太大说明追高风险大
    if gain_5d < 0.03 or gain_5d > 0.15:
        return None

    # 10. 价格位置检查：创近期新高或接近
    recent_20_high = df['close'].iloc[-20:].max()
    near_recent_high = current_price >= recent_20_high * 0.98

    if not near_recent_high:
        return None

    ret['recent_20_high'] = round(recent_20_high, 2)
    ret['is_near_high'] = near_recent_high

    # 11. 均线多头排列检查
    ma5 = last_row['ma5']
    ma10 = last_row['ma10']
    ma20 = last_row['ma20']

    bullish_alignment = ma5 > ma10 and ma10 > ma20
    ret['bullish_alignment'] = bullish_alignment

    # 至少要求MA5 > MA10
    if ma5 <= ma10:
        return None

    # 当前价格应该在MA5之上
    if current_price < ma5:
        return None

    ret['ma5'] = round(ma5, 2)
    ret['ma10'] = round(ma10, 2)
    ret['ma20'] = round(ma20, 2)

    # 12. OBV创新高检查
    obv_current = last_row['obv']
    obv_20_high = df['obv'].iloc[-20:].max()
    obv_new_high = obv_current >= obv_20_high * 0.99

    ret['obv_new_high'] = obv_new_high
    ret['obv_current'] = int(obv_current)

    # 13. VWAP检查
    # 价格应该在VWAP之上，说明近期买入成本在增加
    vwap = last_row['vwap20']
    above_vwap = current_price > vwap

    ret['vwap20'] = round(vwap, 2)
    ret['above_vwap'] = above_vwap

    # 14. MACD确认
    macd_dif = last_row['macd_dif']
    macd_dea = last_row['macd_dea']
    macd_bar = last_row['macd_bar']

    # MACD应该在零轴之上或即将金叉
    macd_bullish = macd_dif > macd_dea and macd_bar > 0

    ret['macd_dif'] = round(macd_dif, 4)
    ret['macd_dea'] = round(macd_dea, 4)
    ret['macd_bullish'] = macd_bullish

    # 15. 计算换手率（如果有流通股本数据）
    # 这里简化处理，用成交量/历史平均成交量来近似
    avg_volume_60 = df['volume'].iloc[-60:].mean()
    relative_volume = last_row['volume'] / avg_volume_60 if avg_volume_60 > 0 else 0

    ret['relative_volume_60d'] = round(relative_volume, 2)

    # 16. 量价背离检查（排除）
    # 如果价格上涨但OBV下跌，则可能是假突破
    obv_5_days_ago = df['obv'].iloc[-5]
    obv_change = (obv_current - obv_5_days_ago) / abs(obv_5_days_ago) if obv_5_days_ago != 0 else 0

    ret['obv_change_5d_pct'] = round(obv_change * 100, 2)

    # OBV应该同步上涨
    if obv_change < 0:  # OBV下跌，量价背离
        return None

    # 17. 强度评分
    # 计算动量强度
    score = 0

    # 连续量增价涨天数
    if consecutive_surge_days >= 4:
        score += 3
    elif consecutive_surge_days >= 3:
        score += 2
    else:
        score += 1

    # 成交量放大幅度
    if volume_ratio_vs_ma20 >= 2.0:
        score += 3
    elif volume_ratio_vs_ma20 >= 1.5:
        score += 2
    else:
        score += 1

    # 均线多头排列
    if bullish_alignment:
        score += 2

    # OBV创新高
    if obv_new_high:
        score += 2

    # MACD多头
    if macd_bullish:
        score += 2

    # 价格在VWAP之上
    if above_vwap:
        score += 1

    ret['strength_score'] = score

    # 总分至少要8分
    if score < 8:
        return None

    # 18. 过滤过度拉升
    # 检查20天涨幅
    price_20_days_ago = df['close'].iloc[-20] if len(df) >= 20 else df['close'].iloc[0]
    gain_20d = (current_price / price_20_days_ago - 1) if price_20_days_ago > 0 else 0

    if gain_20d > 0.30:  # 20天涨幅超过30%，风险较大
        return None

    ret['gain_20d_pct'] = round(gain_20d * 100, 2)

    # 19. 计算资金流向强度
    # 简化版：用量价乘积的累计
    recent_5 = df.iloc[-5:]
    money_flow = (recent_5['close'] * recent_5['volume']).sum()
    prev_5 = df.iloc[-10:-5]
    prev_money_flow = (prev_5['close'] * prev_5['volume']).sum()

    money_flow_ratio = money_flow / prev_money_flow if prev_money_flow > 0 else 0
    ret['money_flow_increase'] = round(money_flow_ratio, 2)

    # 20. 趋势确认：使用ADX（简化版）
    # 计算价格的波动性和方向性
    df['tr'] = pd.DataFrame({
        'hl': df['high'] - df['low'],
        'hc': abs(df['high'] - df['close'].shift(1)),
        'lc': abs(df['low'] - df['close'].shift(1))
    }).max(axis=1)

    df['atr14'] = df['tr'].rolling(window=14).mean()

    # 趋势强度：最近涨幅 / ATR
    atr = last_row['atr14']
    if atr > 0:
        trend_strength = gain_5d * current_price / atr
        ret['trend_strength'] = round(trend_strength, 2)

    return ret


def main():
    """测试函数"""
    from hunter.hunt_machine import HuntMachine, HuntResult
    from hunters.hunt_output import draw_hunt_results
    from datetime import datetime

    hunter = HuntMachine(max_workers=12)

    # 运行扫描
    results: list[HuntResult] = hunter.hunt(hunt_volume_price_surge, min_bars=80)

    if not results:
        print("没有找到符合量价齐升条件的股票。")
        return

    # 输出结果
    codes: list[str] = [result.code for result in results]

    print(f"\n🎉 找到 {len(results)} 只符合量价齐升买点的股票:")
    for result in results:
        print(f"{result.code} {result.name}")
        print(f"  详情: {result.result_info}")

    print(f"\n股票代码列表: {','.join(codes)}")

    # 绘制图表（限制数量避免过多）
    if len(results) <= 10:
        date_in_title = datetime.now().strftime('%Y-%m-%d')
        draw_hunt_results(results, title="量价齐升买点", desc=date_in_title, theme_name="dark_minimal")
    else:
        # 分批绘制
        batch_size = 6
        for i in range(0, min(len(results), 18), batch_size):
            batch_results = results[i:i + batch_size]
            date_in_title = datetime.now().strftime('%Y-%m-%d')
            draw_hunt_results(
                batch_results,
                title=f"量价齐升买点 - 第{i//batch_size + 1}批",
                desc=date_in_title,
                theme_name="dark_minimal"
            )


if __name__ == "__main__":
    main()
