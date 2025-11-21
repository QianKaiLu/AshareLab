import pandas as pd
from datas.query_stock import query_latest_bars, query_all_stock_code_list

def calculate_volume_flow(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or 'close' not in df.columns or 'volume' not in df.columns:
        return pd.DataFrame(columns=['date', 'up_vol', 'down_vol'])
    
    df['prev_close'] = df['close'].shift(1)
    
    # Up volume: Close > Prev Close
    df['up_vol'] = df.apply(lambda x: x['volume'] if x['close'] > x['prev_close'] else 0, axis=1)
    
    # Down volume: Close < Prev Close
    df['down_vol'] = df.apply(lambda x: x['volume'] if x['close'] < x['prev_close'] else 0, axis=1)
    
    return df[['date', 'up_vol', 'down_vol']].dropna()

def analyse_volume_breadth(stock_codes: pd.Series, days: int = 365) -> pd.DataFrame:
    all_dfs = []
    
    for code in stock_codes:
        df = query_latest_bars(code, days + 1) # +1 for prev_close
        if df.empty:
            continue
        
        vol_df = calculate_volume_flow(df)
        if not vol_df.empty:
            all_dfs.append(vol_df)

    if not all_dfs:
        return pd.DataFrame(columns=['date', 'total_up_vol', 'total_down_vol', 'vol_ratio'])
    
    combined_df = pd.concat(all_dfs, ignore_index=True)
    
    result = (
        combined_df.groupby('date')[['up_vol', 'down_vol']]
        .sum()
        .reset_index()
        .rename(columns={'up_vol': 'total_up_vol', 'down_vol': 'total_down_vol'})
    )
    
    # Avoid division by zero
    result['vol_ratio'] = result.apply(
        lambda x: x['total_up_vol'] / x['total_down_vol'] if x['total_down_vol'] > 0 else 100.0, 
        axis=1
    ).round(2)
    
    return result.tail(days).reset_index(drop=True)

if __name__ == "__main__":
    print("Calculating Volume Breadth for all stocks (sample)...")
    # For speed in testing, maybe just use HS300, but ideally all stocks
    from datas.stock_index_list import hs300_code_list
    codes = hs300_code_list() 
    result_df = analyse_volume_breadth(codes, days=30)
    print(result_df)
