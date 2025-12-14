import pandas as pd
from typing import Optional, List
from ta.trend import macd as ta_macd , macd_signal, macd_diff

def macd(
    close: pd.Series,
    window_slow: int = 26,
    window_fast: int = 12,
    window_sign: int = 9,
    fillna: bool = False
) -> pd.DataFrame:
    """
    Calculate MACD (Moving Average Convergence Divergence) indicator.
    
    MACD is a trend-following momentum indicator that shows the relationship between
    two moving averages of a security’s price.
    
    Args:
        close: pd.Series of closing prices
        window_slow: int, the period for the slow EMA, default is 26
        window_fast: int, the period for the fast EMA, default is 12
        window_sign: int, the period for the signal line, default is 9
        fillna: bool, whether to fill NaN values, default is False
    
    Returns:
        pd.DataFrame: DataFrame with columns 'macd', 'macd_dif', and 'macd_dea'
    """
    macd_line = ta_macd(close=close, window_slow=window_slow, window_fast=window_fast, fillna=fillna)
    signal_line = macd_signal(close=close, window_slow=window_slow, window_fast=window_fast, window_sign=window_sign, fillna=fillna)
    macd_bar = macd_diff(close=close, window_slow=window_slow, window_fast=window_fast, window_sign=window_sign, fillna=fillna)*2
    
    df = pd.DataFrame({
        'macd_dif': macd_line,
        'macd_dea': signal_line,
        'macd_bar': macd_bar
    }).round(2)
    
    return df

def add_macd_to_dataframe(
    df: pd.DataFrame,
    close_col: str = 'close',
    window_slow: int = 26,
    window_fast: int = 12,
    window_sign: int = 9,
    fillna: bool = False,
    inplace: bool = False
) -> Optional[pd.DataFrame]:
    """
    Add MACD columns to DataFrame.
    
    Args:
        df: pd.DataFrame containing price data
        close_col: str, column name for close price, default is 'close'
        window_slow: int, the period for the slow EMA, default is 26
        window_fast: int, the period for the fast EMA, default is 12
        window_sign: int, the period for the signal line, default is 9
        macd_cols: list of str, names for the new MACD columns, default is ['macd_dif', 'macd_dea', 'macd_bar']
        fillna: bool, whether to fill NaN values, default is False
        inplace: bool, if True modify df in place and return None; if False return modified copy
    
    Returns:
        pd.DataFrame: Modified DataFrame with MACD columns (if inplace=False), or None (if inplace=True)
    """
    macd_df = macd(
        close=df[close_col],
        window_slow=window_slow,
        window_fast=window_fast,
        window_sign=window_sign,
        fillna=fillna
    )
    
    if inplace:
        for col_name, macd_col in zip(['macd_dif', 'macd_dea', 'macd_bar'], macd_df.columns):
            df[col_name] = macd_df[macd_col]
        return None
    else:
        result = df.copy()
        for col_name, macd_col in zip(['macd_dif', 'macd_dea', 'macd_bar'], macd_df.columns):
            result[col_name] = macd_df[macd_col]
        return result