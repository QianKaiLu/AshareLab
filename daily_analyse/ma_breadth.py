import pandas as pd
from datas.query_stock import query_latest_bars, query_all_stock_code_list
from datas.stock_index_list import hs300_code_list

def calculate_ma_status(df: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    if df.empty or 'close' not in df.columns or len(df) < window:
        return pd.DataFrame(columns=['date', 'above_ma'])
    
    ma = df['close'].rolling(window=window).mean()
    df['above_ma'] = (df['close'] > ma).astype(int)
    
    return df[['date', 'above_ma']].dropna()

def analyse_ma_breadth(stock_codes: pd.Series, window: int = 60, days: int = 365) -> pd.DataFrame:
    all_dfs = []
    # We need to fetch enough data to calculate MA. 
    # If we want 'days' of result, we need days + window data.
    fetch_days = days + window + 20 
    
    for code in stock_codes:
        df = query_latest_bars(code, fetch_days)
        if df.empty:
            continue
        
        ma_df = calculate_ma_status(df, window)
        if not ma_df.empty:
            all_dfs.append(ma_df)

    if not all_dfs:
        return pd.DataFrame(columns=['date', 'count_above_ma', 'total_stocks', 'percent_above_ma'])
    
    combined_df = pd.concat(all_dfs, ignore_index=True)
    
    result = (
        combined_df.groupby('date')['above_ma']
        .agg(['sum', 'count'])
        .reset_index()
        .rename(columns={'sum': 'count_above_ma', 'count': 'total_stocks'})
    )
    
    result['percent_above_ma'] = (result['count_above_ma'] / result['total_stocks'] * 100).round(2)
    
    return result.tail(days).reset_index(drop=True)

if __name__ == "__main__":
    # Example: Analyze HS300 stocks
    print("Calculating MA60 Breadth for HS300...")
    codes = hs300_code_list()
    result_df = analyse_ma_breadth(codes, window=60, days=30)
    print(result_df)
