import sys
import os
import pandas as pd

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hunter.hunt_machine import HuntMachine, HuntResult
from hunter.wyckoff_a import wyckoff_analyze
from datas.query_stock import get_stock_info_by_codes

def main():
    print("🚀 Starting Hunt: Wyckoff High-Probability Buy Setup")
    print("Strategy: Wyckoff Spring and Secondary Test Detection")
    
    hunter = HuntMachine(max_workers=8)
    
    # Run the hunt
    results = hunter.hunt(wyckoff_analyze, min_bars=180)
    
    if not results:
        print("No stocks found matching the criteria.")
        return
    
    # Process results
    # results is a list of HuntResult objects
    codes: list[str] = [result.code for result in results]
    
    print(f"\n🎉 Found {len(results)} stocks:")
    for result in results:
        print(result)
    print(f"codes: {','.join(codes)}")

if __name__ == "__main__":
    main()