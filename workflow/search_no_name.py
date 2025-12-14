import pandas as pd
from typing import Optional, Dict, Any
import sys
import os
from datas.fetch_stock_bars import update_daily_bars_for_code, query_daily_bars
from tools.export import export_bars_to_csv
from tools.log import get_fetch_logger
from datas.query_stock import get_stock_info_by_code, format_stock_info

logger = get_fetch_logger()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hunter.hunt_machine import HuntMachine, HuntResult
from hunter.strategy_breakout_pullback import analyze_breakout_pullback
from datas.query_stock import get_stock_info_by_codes

def search_no_name(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    if df.empty or len(df) < 30:
        return None
    
    latest = df.iloc[-1]
    latest_price = latest['close']
    if latest_price > 22.3 and latest_price < 22.5:
        return {
        "price": latest['close'],
    }

def main():
    print("🚀 Starting Hunt")
    hunter = HuntMachine(max_workers=20)
    
    # Run the hunt
    results: list[HuntResult] = hunter.hunt(search_no_name, min_bars=100)
    
    if not results:
        print("No stocks found matching the criteria.")
        return

    codes: list[str] = [result.code for result in results]
    
    print(f"\n🎉 Found {len(results)} stocks:")
    
    for code in codes:
        stock_info = get_stock_info_by_code(code)
        if stock_info is not None and not stock_info.empty:
            logger.info(format_stock_info(df=stock_info))

    logger.info(f"codes: {','.join(codes)}")


if __name__ == "__main__":
    main()
