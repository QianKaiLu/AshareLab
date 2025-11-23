import pandas as pd
from typing import Optional

def bbi(
    close: pd.Series,
    periods: tuple = (3, 6, 12, 24)
) -> pd.Series:
    """
    Calculate BBI (Bull and Bear Index) indicator
    
    BBI is the average of multiple moving averages, typically used to identify
    trend direction and support/resistance levels.
    
    Args:
        df: DataFrame containing price data
        close_col: column name for close price, default 'close'
        periods: tuple of MA periods to use, default (3, 6, 12, 24)
    
    Returns:
        pd.Series: BBI values
    
    Example:
        >>> df = pd.DataFrame({'close': [10, 11, 12, 13, 14, 15]})
        >>> df['bbi'] = bbi(df['close'])
    """
    if len(periods) == 0:
        raise ValueError("At least one period must be specified")
    
    ma_values = []
    for period in periods:
        ma = close.rolling(window=period, min_periods=1).mean()
        ma_values.append(ma)
    
    bbi = pd.concat(ma_values, axis=1).mean(axis=1)
    
    return bbi

def add_bbi_to_dataframe(
    df: pd.DataFrame,
    close_col: str = 'close',
    periods: tuple = (3, 6, 12, 24),
    bbi_col: str = 'bbi',
    inplace: bool = False
) -> Optional[pd.DataFrame]:
    """
    Add BBI column to DataFrame
    
    Args:
        df: DataFrame containing price data
        close_col: column name for close price, default 'close'
        periods: tuple of MA periods to use, default (3, 6, 12, 24)
        bbi_col: name for the new BBI column, default 'bbi'
        inplace: if True, modify df in place and return None; if False, return modified copy
    
    Returns:
        Modified DataFrame with BBI column (if inplace=False), or None (if inplace=True)
    
    Example:
        >>> df = pd.DataFrame({'close': [10, 11, 12, 13, 14, 15]})
        >>> df = add_bbi_to_dataframe(df)
        >>> print(df['bbi'])
    """
    if inplace:
        df[bbi_col] = bbi(df[close_col], periods=periods)
        return None
    else:
        result = df.copy()
        result[bbi_col] = bbi(result[close_col], periods=periods)
        return result
