"""
MACD底背离买点识别器

形态特征：
1. 价格创出新低（相比前一个低点更低）
2. 但MACD指标的低点却高于前一个低点（DIF或BAR柱状图）
3. 形成"价格下跌、指标上升"的背离形态
4. 背离后出现反转信号（MACD金叉或K线反转）

分析体系：
- 背离理论：技术指标与价格走势的不一致
- MACD动量指标：反映趋势的强度和方向
- 波浪理论：底背离常出现在下跌末期

为什么是好的买点：
1. 底背离是超跌反弹的经典信号，成功率较高
2. 表示下跌动能衰竭，空头力量减弱
3. 通常出现在下跌趋势的末期或重要支撑位
4. 结合反转K线形态，可靠性更高
5. 风险收益比好，止损位明确（最近低点）

适用场景：
- 下跌趋势末期
- 超跌反弹机会
- 重要支撑位附近
- 适合短期和波段操作

技术要点：
- 两个低点之间至少间隔5个交易日
- 价格新低要明显（至少1%）
- MACD的背离要清晰（低点差异至少5%）
- 最好结合RSI等其他超卖指标
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
from tools.log import get_analyze_logger
from indicators.macd import add_macd_to_dataframe
from indicators.rsi import add_rsi_to_dataframe

logger = get_analyze_logger()


def find_local_extremes(series: pd.Series, window: int = 5) -> Tuple[list, list]:
    """
    查找时间序列中的局部极值点（波峰和波谷）

    Args:
        series: 价格或指标序列
        window: 判断极值的窗口大小

    Returns:
        (peaks_idx, troughs_idx): 波峰和波谷的索引列表
    """
    peaks = []
    troughs = []

    for i in range(window, len(series) - window):
        # 检查是否是局部最高点
        is_peak = True
        for j in range(i - window, i + window + 1):
            if j != i and series.iloc[j] >= series.iloc[i]:
                is_peak = False
                break
        if is_peak:
            peaks.append(i)

        # 检查是否是局部最低点
        is_trough = True
        for j in range(i - window, i + window + 1):
            if j != i and series.iloc[j] <= series.iloc[i]:
                is_trough = False
                break
        if is_trough:
            troughs.append(i)

    return peaks, troughs


def hunt_macd_divergence(df: pd.DataFrame) -> Optional[dict]:
    """
    MACD底背离买点识别函数

    Args:
        df: 包含OHLCV数据的DataFrame

    Returns:
        dict: 包含买点信息的字典，如果不符合条件则返回None
    """
    if df is None or df.empty or len(df) < 60:
        return None

    ret = {}

    # 1. 添加MACD指标
    add_macd_to_dataframe(df, inplace=True)

    # 2. 添加RSI指标（辅助判断超卖）
    add_rsi_to_dataframe(df, period=14, inplace=True)

    # 3. 在最近60天内寻找背离形态
    lookback = min(60, len(df))
    recent_df = df.iloc[-lookback:].copy()
    recent_df.reset_index(drop=True, inplace=True)

    # 4. 找出价格和MACD DIF的局部低点
    price_peaks, price_troughs = find_local_extremes(recent_df['close'], window=3)
    macd_peaks, macd_troughs = find_local_extremes(recent_df['macd_dif'], window=3)

    # 需要至少2个价格低点和2个MACD低点
    if len(price_troughs) < 2 or len(macd_troughs) < 2:
        return None

    # 5. 检测背离：最近的两个低点
    # 找到最近的两个价格低点
    last_price_trough_idx = price_troughs[-1]
    prev_price_trough_idx = price_troughs[-2]

    # 确保两个低点之间至少间隔5天
    if last_price_trough_idx - prev_price_trough_idx < 5:
        return None

    # 6. 找到对应时间段的MACD低点
    # 在每个价格低点附近（±3天）找MACD的最低点
    def find_nearest_macd_trough(price_idx, macd_troughs_list, tolerance=3):
        candidates = [idx for idx in macd_troughs_list
                     if abs(idx - price_idx) <= tolerance]
        if not candidates:
            # 如果没有找到，就用价格低点那天的MACD值
            return price_idx
        # 返回MACD DIF最低的那个点
        return min(candidates, key=lambda x: recent_df.iloc[x]['macd_dif'])

    prev_macd_idx = find_nearest_macd_trough(prev_price_trough_idx, macd_troughs)
    last_macd_idx = find_nearest_macd_trough(last_price_trough_idx, macd_troughs)

    # 7. 判断是否构成背离
    prev_price = recent_df.iloc[prev_price_trough_idx]['close']
    last_price = recent_df.iloc[last_price_trough_idx]['close']
    prev_macd = recent_df.iloc[prev_macd_idx]['macd_dif']
    last_macd = recent_df.iloc[last_macd_idx]['macd_dif']

    # 价格创新低（至少低1%）
    price_new_low = last_price < prev_price * 0.99

    # MACD不创新低（甚至更高）
    macd_not_new_low = last_macd > prev_macd

    # 背离强度：MACD的改善幅度
    macd_improvement = (last_macd - prev_macd) / abs(prev_macd) if prev_macd != 0 else 0

    if not (price_new_low and macd_not_new_low):
        return None

    # 要求MACD改善至少5%
    if macd_improvement < 0.05:
        return None

    ret['prev_price_low'] = round(prev_price, 2)
    ret['last_price_low'] = round(last_price, 2)
    ret['price_drop_pct'] = round((last_price / prev_price - 1) * 100, 2)
    ret['prev_macd_dif'] = round(prev_macd, 4)
    ret['last_macd_dif'] = round(last_macd, 4)
    ret['macd_improvement_pct'] = round(macd_improvement * 100, 2)
    ret['divergence_strength'] = 'strong' if macd_improvement > 0.15 else 'medium'

    # 8. 确认当前已经过了最后一个低点，并且开始反转
    last_row = recent_df.iloc[-1]
    last_idx = len(recent_df) - 1

    # 最后一个价格低点不能是昨天或今天（需要有一定时间来确认反转）
    if last_idx - last_price_trough_idx < 2:
        return None

    # 当前价格应该高于最后一个低点
    if last_row['close'] <= last_price * 1.01:  # 至少反弹1%
        return None

    ret['current_price'] = round(last_row['close'], 2)
    ret['rebound_from_low_pct'] = round((last_row['close'] / last_price - 1) * 100, 2)

    # 9. 检查MACD是否出现金叉或即将金叉
    prev_row = recent_df.iloc[-2]

    # 已经金叉
    macd_golden = (
        prev_row['macd_dif'] < prev_row['macd_dea'] and
        last_row['macd_dif'] >= last_row['macd_dea']
    )

    # 或者DIF正在向上接近DEA（距离缩小）
    macd_approaching = (
        last_row['macd_dif'] < last_row['macd_dea'] and
        (last_row['macd_dea'] - last_row['macd_dif']) <
        (prev_row['macd_dea'] - prev_row['macd_dif'])
    )

    # 或者已经金叉且保持多头
    macd_bullish = (
        last_row['macd_dif'] > last_row['macd_dea'] and
        last_row['macd_bar'] > prev_row['macd_bar']
    )

    if not (macd_golden or macd_approaching or macd_bullish):
        return None

    ret['macd_status'] = 'golden_cross' if macd_golden else 'approaching' if macd_approaching else 'bullish'
    ret['current_macd_dif'] = round(last_row['macd_dif'], 4)
    ret['current_macd_dea'] = round(last_row['macd_dea'], 4)

    # 10. RSI超卖确认（加分项）
    if 'rsi' in last_row.index:
        ret['rsi'] = round(last_row['rsi'], 2)
        # RSI低于30认为超卖，低于40也算较低
        ret['is_oversold'] = last_row['rsi'] < 40

    # 11. 计算风险收益比
    # 止损位：最后一个低点再下3%
    stop_loss = last_price * 0.97
    # 目标位：根据背离强度，设定5%-15%的目标
    target_gain = 0.08 if macd_improvement > 0.15 else 0.05
    target_price = last_row['close'] * (1 + target_gain)

    risk = last_row['close'] - stop_loss
    reward = target_price - last_row['close']
    risk_reward_ratio = reward / risk if risk > 0 else 0

    ret['stop_loss_price'] = round(stop_loss, 2)
    ret['target_price'] = round(target_price, 2)
    ret['risk_reward_ratio'] = round(risk_reward_ratio, 2)

    # 风险收益比至少要大于2
    if risk_reward_ratio < 2:
        return None

    # 12. 排除近期涨幅过大的股票（可能已经反弹完成）
    if ret['rebound_from_low_pct'] > 15:
        return None

    return ret


def main():
    """测试函数"""
    from hunter.hunt_machine import HuntMachine, HuntResult
    from hunters.hunt_output import draw_hunt_results
    from datetime import datetime

    hunter = HuntMachine(max_workers=12)

    # 运行扫描
    results: list[HuntResult] = hunter.hunt(hunt_macd_divergence, min_bars=120)

    if not results:
        print("没有找到符合MACD底背离条件的股票。")
        return

    # 输出结果
    codes: list[str] = [result.code for result in results]

    print(f"\n🎉 找到 {len(results)} 只符合MACD底背离买点的股票:")
    for result in results:
        print(f"{result.code} {result.name}")
        print(f"  详情: {result.result_info}")

    print(f"\n股票代码列表: {','.join(codes)}")

    # 绘制图表（限制数量避免过多）
    if len(results) <= 10:
        date_in_title = datetime.now().strftime('%Y-%m-%d')
        draw_hunt_results(results, title="MACD底背离买点", desc=date_in_title, theme_name="dark_minimal")
    else:
        # 分批绘制
        batch_size = 6
        for i in range(0, min(len(results), 18), batch_size):
            batch_results = results[i:i + batch_size]
            date_in_title = datetime.now().strftime('%Y-%m-%d')
            draw_hunt_results(
                batch_results,
                title=f"MACD底背离买点 - 第{i//batch_size + 1}批",
                desc=date_in_title,
                theme_name="dark_minimal"
            )


if __name__ == "__main__":
    main()
