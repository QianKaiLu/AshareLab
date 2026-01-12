"""
黄金交叉买点识别器

形态特征：
1. 短期均线（MA5）向上穿越长期均线（MA20），形成"黄金交叉"
2. MACD 指标同步出现金叉（DIF上穿DEA）
3. 成交量相比前期明显放大（至少1.5倍）
4. 股价在均线之上运行

分析体系：
- 均线系统：葛兰维尔八大法则
- MACD动量指标：趋势确认
- 量价关系：成交量确认

为什么是好的买点：
1. 多条技术指标共振，提高成功率
2. 短期均线上穿长期均线标志着趋势反转或加速
3. MACD金叉确认动能转强
4. 成交量放大说明资金开始介入，有持续性
5. 均线系统是最经典、最可靠的趋势跟踪工具

适用场景：
- 趋势反转初期
- 上升趋势加速阶段
- 适合中短期持有
"""

import pandas as pd
import numpy as np
from typing import Optional
from tools.log import get_analyze_logger
from indicators.macd import add_macd_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe

logger = get_analyze_logger()


def hunt_golden_cross(df: pd.DataFrame) -> Optional[dict]:
    """
    黄金交叉买点识别函数

    Args:
        df: 包含OHLCV数据的DataFrame

    Returns:
        dict: 包含买点信息的字典，如果不符合条件则返回None
    """
    if df is None or df.empty or len(df) < 60:
        return None

    ret = {}

    # 1. 计算均线：MA5, MA10, MA20, MA60
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma60'] = df['close'].rolling(window=60).mean()

    # 2. 添加MACD指标
    add_macd_to_dataframe(df, inplace=True)

    # 3. 计算成交量均线
    add_volume_ma_to_dataframe(df, periods=[5, 20], inplace=True)

    # 获取最近几天的数据
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    prev2_row = df.iloc[-3]

    # 4. 检测MA5上穿MA20（黄金交叉）
    # 前一天MA5 < MA20，当天MA5 >= MA20
    is_golden_cross = (
        prev_row['ma5'] < prev_row['ma20'] and
        last_row['ma5'] >= last_row['ma20']
    )

    # 或者最近3天内发生了金叉（允许一定的时间窗口）
    is_recent_cross = False
    for i in range(-1, -4, -1):
        if i < -len(df):
            break
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        if prev['ma5'] < prev['ma20'] and curr['ma5'] >= curr['ma20']:
            is_recent_cross = True
            break

    if not (is_golden_cross or is_recent_cross):
        return None

    ret['ma5'] = round(last_row['ma5'], 2)
    ret['ma20'] = round(last_row['ma20'], 2)
    ret['ma_cross_signal'] = 'golden_cross'

    # 5. 检测MACD金叉（DIF上穿DEA）
    # 要么刚刚金叉，要么已经金叉且DIF和DEA都在上升
    macd_golden = (
        prev_row['MACD_DIF'] < prev_row['MACD_DEA'] and
        last_row['MACD_DIF'] >= last_row['MACD_DEA']
    )

    # 或者已经金叉但保持向上（DIF > DEA 且 MACD柱状图为正且增长）
    macd_bullish = (
        last_row['MACD_DIF'] > last_row['MACD_DEA'] and
        last_row['MACD_BAR'] > 0 and
        last_row['MACD_BAR'] > prev_row['MACD_BAR']
    )

    if not (macd_golden or macd_bullish):
        return None

    ret['macd_dif'] = round(last_row['MACD_DIF'], 4)
    ret['macd_dea'] = round(last_row['MACD_DEA'], 4)
    ret['macd_bar'] = round(last_row['MACD_BAR'], 4)

    # 6. 成交量放大检查
    # 最近成交量应该大于20日均量的1.2倍
    volume_surge = last_row['volume'] > last_row['volume_ma_20'] * 1.2

    # 或者最近5日平均成交量大于前20日平均成交量的1.3倍
    recent_vol_avg = df['volume'].iloc[-5:].mean()
    vol_ratio = recent_vol_avg / last_row['volume_ma_20'] if last_row['volume_ma_20'] > 0 else 0

    if not (volume_surge or vol_ratio > 1.3):
        return None

    ret['volume_ratio'] = round(vol_ratio, 2)
    ret['current_volume'] = int(last_row['volume'])
    ret['volume_ma_20'] = int(last_row['volume_ma_20'])

    # 7. 股价位置检查：当前价格应该在MA5之上或附近
    price_above_ma5 = last_row['close'] >= last_row['ma5'] * 0.98
    if not price_above_ma5:
        return None

    ret['close'] = round(last_row['close'], 2)
    ret['price_above_ma5_pct'] = round((last_row['close'] / last_row['ma5'] - 1) * 100, 2)

    # 8. 均线多头排列检查（可选，加分项）
    # MA5 > MA10 > MA20 表示强势多头排列
    is_bullish_alignment = (
        last_row['ma5'] > last_row['ma10'] and
        last_row['ma10'] > last_row['ma20']
    )
    ret['bullish_alignment'] = is_bullish_alignment

    # 9. 趋势强度：计算MA5相对于MA20的斜率
    ma5_slope = (last_row['ma5'] - prev2_row['ma5']) / prev2_row['ma5'] if prev2_row['ma5'] > 0 else 0
    ret['ma5_slope_pct'] = round(ma5_slope * 100, 2)

    # 10. 过滤掉过度拉升的股票（最近20天涨幅超过30%的排除）
    price_20_days_ago = df['close'].iloc[-20] if len(df) >= 20 else df['close'].iloc[0]
    gain_20d = (last_row['close'] / price_20_days_ago - 1) if price_20_days_ago > 0 else 0
    if gain_20d > 0.30:  # 涨幅超过30%
        return None

    ret['gain_20d_pct'] = round(gain_20d * 100, 2)

    return ret


def main():
    """测试函数"""
    from hunter.hunt_machine import HuntMachine, HuntResult
    from hunters.hunt_output import draw_hunt_results
    from datetime import datetime

    hunter = HuntMachine(max_workers=12)

    # 运行扫描
    results: list[HuntResult] = hunter.hunt(hunt_golden_cross, min_bars=120)

    if not results:
        print("没有找到符合黄金交叉条件的股票。")
        return

    # 输出结果
    codes: list[str] = [result.code for result in results]

    print(f"\n🎉 找到 {len(results)} 只符合黄金交叉买点的股票:")
    for result in results:
        print(f"{result.code} {result.name}")
        print(f"  详情: {result.result_info}")

    print(f"\n股票代码列表: {','.join(codes)}")

    # 绘制图表（限制数量避免过多）
    if len(results) <= 10:
        date_in_title = datetime.now().strftime('%Y-%m-%d')
        draw_hunt_results(results, title="黄金交叉买点", desc=date_in_title, theme_name="dark_minimal")
    else:
        # 分批绘制
        batch_size = 6
        for i in range(0, min(len(results), 18), batch_size):
            batch_results = results[i:i + batch_size]
            date_in_title = datetime.now().strftime('%Y-%m-%d')
            draw_hunt_results(
                batch_results,
                title=f"黄金交叉买点 - 第{i//batch_size + 1}批",
                desc=date_in_title,
                theme_name="dark_minimal"
            )


if __name__ == "__main__":
    main()
