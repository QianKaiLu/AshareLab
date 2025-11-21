import pandas as pd
from datas.query_stock import query_latest_bars, query_all_stock_code_list

def mark_close_not_lower_than_previous(df: pd.DataFrame) -> pd.DataFrame:
    
    df['prev_close'] = df['close'].shift(1)
    df['is_up'] = (df['close'] > df['prev_close']).fillna(False).astype(int)
    df['is_down'] = (df['close'] < df['prev_close']).fillna(False).astype(int)
    
    return df[['date', 'is_up', 'is_down']]


def count_stocks_with_price_not_lower(stock_codes: pd.Series, days: int = 365) -> pd.DataFrame:
    daily_signals = []

    for code in stock_codes:
        price_df = query_latest_bars(code, days)
        if price_df.empty:
            continue
        signal_df = mark_close_not_lower_than_previous(price_df)
        daily_signals.append(signal_df)

    if not daily_signals:
        return pd.DataFrame(columns=['date', 'up_count', 'down_count'])

    all_signals = pd.concat(daily_signals, ignore_index=True)

    summary = (
        all_signals.groupby('date')[['is_up', 'is_down']]
        .sum()
        .reset_index()
        .rename(columns={'is_up': 'up_count', 'is_down': 'down_count'})
    )

    return summary.tail(days).reset_index(drop=True)


if __name__ == "__main__":
    all_codes = query_all_stock_code_list()
    result_df = count_stocks_with_price_not_lower(all_codes, days=30)
    print(result_df)

    # target_date = "2024-09-24"
    # row = result_df[result_df['date'] == target_date]
    # count = row['up_count'].iloc[0] if not row.empty else 0
    # print(f"Number of stocks with close > previous day on {target_date}: {count}")