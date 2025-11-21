import akshare as ak
import sqlite3
import pandas as pd
from pathlib import Path
from datas.query_stock import query_latest_bars
from datas.stock_index_list import hs300_code_list, csi500_code_list, csi2000_code_list

def close_at_20_high_serise(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or 'close' not in df.columns:
        return pd.DataFrame(columns=['date', 'close_at_20_high'])
    
    rolling_max = df['close'].rolling(window=20, min_periods=1).max()
    df['close_at_20_high'] = (df['close'] >= rolling_max).astype(int)

    high_df = df[['date', 'close_at_20_high']]
    
    return high_df


def analyse_close_20_high_count(stock_codes: pd.Series, days: int = 365) -> pd.DataFrame:
    all_high_dfs = []
    for code in stock_codes:
        df = query_latest_bars(code, days)
        if df.empty:
            continue
        high_df = close_at_20_high_serise(df)
        all_high_dfs.append(high_df)

    if not all_high_dfs:
        return pd.DataFrame(columns=['date', 'close_at_20_high_count'])
    
    combined_df = pd.concat(all_high_dfs, ignore_index=True)
    result = (
        combined_df.groupby('date')['close_at_20_high']
        .sum()
        .reset_index()
        .rename(columns={'close_at_20_high': 'close_at_20_high_count'})
    )

    return result

if __name__ == "__main__":
    result_df = analyse_close_20_high_count(hs300_code_list(), days=365)
    # print("Recent 365-day high counts for HS300 stocks in the past year:")
    print(result_df)
    date_2024_09_24 = result_df[result_df['date'] == '2024-09-24']
    count = date_2024_09_24.iloc[0]['close_at_20_high_count'] if not date_2024_09_24.empty else 0
    print(f"20_high at 2024-09-24: {count}")