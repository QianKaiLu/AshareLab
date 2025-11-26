import pandas as pd
from typing import Optional, List
import numpy as np

def zxdkx(
    close: pd.Series,
    m1: int = 14,
    m2: int = 28,
    m3: int = 57,
    m4: int = 114
) -> pd.DataFrame:
    """
    Calculate z_white and z_yellow indicators.
    
    z_white is the double EMA of closing prices with a span of 10.
    z_yellow is the average of moving averages of closing prices over periods m1, m2, m3, and m4.
    
    Args:
        close: pd.Series of closing prices
        m1: int, period for first moving average, default is 14
        m2: int, period for second moving average, default is 28
        m3: int, period for third moving average, default is 57
        m4: int, period for fourth moving average, default is 114
    
    Returns:
        pd.DataFrame: DataFrame with columns 'z_white' and 'z_yellow'
    """
    z_white = close.ewm(span=10, adjust=False).mean().ewm(span=10, adjust=False).mean()
    ma1 = close.rolling(window=m1, min_periods=1).mean()
    ma2 = close.rolling(window=m2, min_periods=1).mean()
    ma3 = close.rolling(window=m3, min_periods=1).mean()
    ma4 = close.rolling(window=m4, min_periods=1).mean()
    z_yellow = (ma1 + ma2 + ma3 + ma4) / 4.0
    zxdkx_df = pd.DataFrame({'z_white': z_white, 'z_yellow': z_yellow}).round(2)
    return zxdkx_df

def add_zxdkx_to_dataframe(
    df: pd.DataFrame,
    close_col: str = 'close',
    m1: int = 14,
    m2: int = 28,
    m3: int = 57,
    m4: int = 114,
    inplace: bool = False
) -> Optional[pd.DataFrame]:
    """
    Add z_white and z_yellow columns to DataFrame.
    
    Args:
        df: pd.DataFrame containing price data
        close_col: str, column name for close price, default is 'close'
        m1: int, period for first moving average, default is 14
        m2: int, period for second moving average, default is 28
        m3: int, period for third moving average, default is 57
        m4: int, period for fourth moving average, default is 114
        inplace: bool, if True modify df in place and return None; if False return modified copy
    Returns:
        pd.DataFrame: Modified DataFrame with z_white and z_yellow columns (if inplace=False), or None (if inplace=True)
    """
    zxdkx_df = zxdkx(
        close=df[close_col],
        m1=m1,
        m2=m2,
        m3=m3,
        m4=m4
    )
    
    if inplace:
        df['z_white'] = zxdkx_df['z_white']
        df['z_yellow'] = zxdkx_df['z_yellow']
        return None
    else:
        result = df.copy()
        result['z_white'] = zxdkx_df['z_white']
        result['z_yellow'] = zxdkx_df['z_yellow']
        return result