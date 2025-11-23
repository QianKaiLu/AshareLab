import pandas as pd
from typing import Optional, List
import numpy as np

def kdj(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 9,
    k_period: int = 3,
    d_period: int = 3
) -> pd.DataFrame:
    """
    Calculate KDJ indicator.
    
    KDJ is a momentum indicator that consists of three lines: %K, %D, and %J.
    
    Args:
        high: pd.Series of high prices
        low: pd.Series of low prices
        close: pd.Series of closing prices
        period: int, the period for RSV calculation, default is 9
        k_period: int, the smoothing period for %K, default is 3
        d_period: int, the smoothing period for %D, default is 3
    
    Returns:
        pd.DataFrame: DataFrame with columns 'K', 'D', 'J'
    """
    low_min = low.rolling(window=period, min_periods=1).min()
    high_max = high.rolling(window=period, min_periods=1).max()
    denom = high_max - low_min
    
    rsv = np.where(denom == 0, 50.0, (close - low_min) / denom * 100)
    rsv = pd.Series(rsv, index=close.index)
    
    k = rsv.ewm(com=k_period - 1, adjust=False).mean()
    d = k.ewm(com=d_period - 1, adjust=False).mean()
    j = 3 * k - 2 * d
    
    kdj_df = pd.DataFrame({'kdj_k': k, 'kdj_d': d, 'kdj_j': j}).round(2)
    
    return kdj_df

def add_kdj_to_dataframe(
    df: pd.DataFrame,
    high_col: str = 'high',
    low_col: str = 'low',
    close_col: str = 'close',
    period: int = 9,
    k_period: int = 3,
    d_period: int = 3,
    inplace: bool = False
) -> Optional[pd.DataFrame]:
    """
    Add KDJ columns to DataFrame.
    
    Args:
        df: pd.DataFrame containing price data
        high_col: str, column name for high price, default is 'high'
        low_col: str, column name for low price, default is 'low'
        close_col: str, column name for close price, default is 'close'
        period: int, the period for RSV calculation, default is 9
        k_period: int, the smoothing period for %K, default is 3
        d_period: int, the smoothing period for %D, default is 3
        inplace: bool, if True modify df in place and return None; if False return modified copy
    
    Returns:
        pd.DataFrame: Modified DataFrame with KDJ columns (if inplace=False), or None (if inplace=True)
    """
    kdj_df = kdj(
        high=df[high_col],
        low=df[low_col],
        close=df[close_col],
        period=period,
        k_period=k_period,
        d_period=d_period
    )
    
    if inplace:
        for col_name, kdj_col in zip(['kdj_k', 'kdj_d', 'kdj_j'], kdj_df.columns):
            df[col_name] = kdj_df[kdj_col]
        return None
    else:
        result = df.copy()
        for col_name, kdj_col in zip(['kdj_k', 'kdj_d', 'kdj_j'], kdj_df.columns):
            result[col_name] = kdj_df[kdj_col]
        return result