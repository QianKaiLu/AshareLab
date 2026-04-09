import pandas as pd
from typing import Optional
from tools.log import get_analyze_logger
from indicators.zxdkx import add_zxdkx_to_dataframe
from indicators.kdj import add_kdj_to_dataframe
from hunter.hunt_machine import HuntMachine, HuntResult, HuntInputLike, HuntInput

logger = get_analyze_logger()

# 允许前一天收盘价略微高于黄线的容忍度。1.01 表示允许超出黄线 1%（即“一丢丢”的范围）
PREV_YELLOW_TOLERANCE = 1.01 

def back_to_yellow_hunter(df: pd.DataFrame) -> Optional[dict]:
    """
    寻找股价重新站上黄线（或回踩黄线成功），且白线在黄线上方的标的。
    """
    # 处理空数据或数据量不足
    if df is None or len(df) < 2:
        return None
    
    # 添加双线系统指标（生成 z_white 和 z_yellow 列）
    add_zxdkx_to_dataframe(df, inplace=True)
    
    add_kdj_to_dataframe(df, inplace=True)
    
    ret = {}
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    # 当日数据
    curr_close = last_row["close"]
    curr_yellow = last_row["z_yellow"]
    curr_white = last_row["z_white"]
    
    # 前一日数据
    prev_close = prev_row["close"]
    prev_yellow = prev_row["z_yellow"]

    # ------------------ 核心条件判断 ------------------
    
    # 条件1：白线必须要在黄线上（表示短期趋势强）
    if curr_white < curr_yellow:
        return None

    # 条件2：前一天在黄线以下，或者非常接近黄线（允许在黄线上方一丢丢）
    # 如果前一天的收盘价大于（黄线 * 容忍度），说明前一天已经明显在黄线之上了，不符合“刚刚回到黄线”或“回踩到位”的定义
    if prev_close > prev_yellow * PREV_YELLOW_TOLERANCE:
        return None

    # 条件3：当天必须回到了黄线之上
    if curr_close <= curr_yellow:
        return None

    # 条件4（可选，作为质量控制）：当天收盘价也最好在白线附近或以上，排除那种离白线过远的深水炸弹
    # 如果不需要可以注释掉
    # if curr_close < curr_white * 0.95:
    #     return None

    # ------------------ 组装返回结果 ------------------
    ret.update({
        "curr_close": round(curr_close, 2),
        "curr_yellow": round(curr_yellow, 2),
        "curr_white": round(curr_white, 2),
        "prev_close": round(prev_close, 2),
        "prev_yellow": round(prev_yellow, 2),
        "cross_up_pct": round((curr_close / curr_yellow - 1) * 100, 2)  # 当天收盘价超过黄线的百分比
    })

    return ret

# 测试用例池（保留部分用于本地调试）
target_pool: list[HuntInputLike] = [
    HuntInput(code="000725", to_date='20251223', days=500),  # 京东方A
    HuntInput(code="600138", to_date='20260106', days=500),  # 中青旅
    HuntInput(code="600750", to_date="20251230", days=500),  # 江中药业
    HuntInput(code="688799", to_date="20250509", days=500),  # 娜娜图
]

def main():
    def print_result(result: HuntResult):
        logger.info(f"{result.format_info}")

    hunter = HuntMachine(max_workers=20, on_result_found=print_result)
    
    print("back_to_yellow_hunter ...")
    
    # 执行选股（可以替换 hunt_pool=None 以扫描全市场，这里用 target_pool 做演示）
    results: list[HuntResult] = hunter.hunt(back_to_yellow_hunter, min_bars=500, hunt_pool=None)
    
    if not results:
        print("\nno stocks found that meet the criteria.")
        return

    codes = [r.code for r in results]
    print(f"\n🎉 Scan complete, found {len(results)} stocks that meet the criteria:")
    
    print("-" * 40)
    for r in results:
        print(f"Code: {r.code} | Latest Close: {r.result_info['curr_close']} | Yellow Line: {r.result_info['curr_yellow']} | White Line: {r.result_info['curr_white']}")
    print("-" * 40)
    
    print("股票代码列表：")
    for i in range(0, len(codes), 10):
        print(",".join(codes[i:i+10]))

if __name__ == "__main__":
    main()