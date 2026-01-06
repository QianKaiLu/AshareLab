import pandas as pd
from typing import Optional, List
import numpy as np

def volume_ma(
    volume: pd.Series,
    periods: List[int] = [5, 10, 20],
    fillna: bool = False
) -> pd.DataFrame:
    """
    Calculate Volume Moving Averages (Volume MA) for given periods.
    
    Volume MA is used to analyze the average trading volume over specified periods.
    
    Args:
        volume: pd.Series of trading volumes
        periods: list of int, periods for moving averages, default is [5, 10, 20]
        fillna: bool, whether to fill NaN values, default is False
    Returns:
        pd.DataFrame: DataFrame with Volume MA columns for each specified period
    """
    ma_values = {}
    for period in periods:
        ma = volume.rolling(window=period, min_periods=1).mean()
        if fillna:
            ma = ma.bfill().fillna(0)
        ma_values[f'volume_ma_{period}'] = ma.round(2)
    
    return pd.DataFrame(ma_values)

def add_volume_ma_to_dataframe(
    df: pd.DataFrame,
    volume_col: str = 'volume',
    periods: List[int] = [5, 10, 20],
    fillna: bool = False,
    inplace: bool = False
) -> Optional[pd.DataFrame]:
    """
    Add Volume MA columns to DataFrame.
    
    Args:
        df: pd.DataFrame containing price data
        volume_col: str, column name for volume, default is 'volume'
        periods: list of int, periods for moving averages, default is [5, 10, 20]
        fillna: bool, whether to fill NaN values, default is False
        inplace: bool, if True modify df in place and return None; if False return modified copy
    Returns:
        pd.DataFrame: Modified DataFrame with Volume MA columns (if inplace=False), or None (if inplace=True)
    """
    volume_ma_df = volume_ma(
        volume=df[volume_col],
        periods=periods,
        fillna=fillna
    )
    
    if inplace:
        for col_name in volume_ma_df.columns:
            df[col_name] = volume_ma_df[col_name]
        return None
    else:
        result = df.copy()
        for col_name in volume_ma_df.columns:
            result[col_name] = volume_ma_df[col_name]
        return result