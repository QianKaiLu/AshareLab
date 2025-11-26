import sys
import os
import pandas as pd

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hunter.hunt_machine import HuntMachine
from hunter.strategy_breakout_pullback import analyze_breakout_pullback
from datas.query_stock import get_stock_info_by_codes

def main():
    print("🚀 Starting Hunt: Breakout Pullback Strategy")
    print("Strategy: Uptrend + Strong Momentum (15%) + Pullback + Low Volume")
    
    hunter = HuntMachine(max_workers=8)
    
    # Run the hunt
    results = hunter.hunt(analyze_breakout_pullback, min_bars=60)
    
    if not results:
        print("No stocks found matching the criteria.")
        return

    # Process results
    # results is a list of (code, dict) tuples
    data = []
    codes = []
    for code, info in results:
        info['code'] = code
        data.append(info)
        codes.append(code)
        
    # Get stock names
    try:
        names_df = get_stock_info_by_codes(codes)
        # names_df index is code
    except Exception as e:
        print(f"Warning: Could not fetch stock names: {e}")
        names_df = pd.DataFrame()

    df_res = pd.DataFrame(data)
    
    if not names_df.empty:
        df_res = df_res.set_index('code')
        df_res['name'] = names_df['name']
        df_res = df_res.reset_index()
    
    # Reorder columns
    cols = ['code', 'name', 'price', 'recent_gain_pct', 'pullback_from_high', 'vol_ratio']
    # Filter cols that exist
    cols = [c for c in cols if c in df_res.columns]
    df_res = df_res[cols]
    
    print(f"\n🎉 Found {len(df_res)} stocks:")
    print(df_res.to_string(index=False))
    
    # Save to CSV
    output_file = "output/hunt_breakout_pullback.csv"
    os.makedirs("output", exist_ok=True)
    df_res.to_csv(output_file, index=False)
    print(f"\nSaved results to {output_file}")

if __name__ == "__main__":
    main()
