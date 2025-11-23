from ta.momentum import rsi as ta_rsi
import pandas as pd
from typing import Optional

def rsi(
    close: pd.Series,
    window: int = 14,
    fillna: bool = False
) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI) indicator.
    
    RSI is a momentum oscillator that measures the speed and change of price movements.
    
    Args:
        close: pd.Series of closing prices
        window: int, the period for RSI calculation, default is 14
        fillna: bool, whether to fill NaN values, default is False
    Returns:
        pd.Series: RSI values
    """
    rsi_values = ta_rsi(close=close, window=window, fillna=fillna).round(2)
    return rsi_values

def add_rsi_to_dataframe(
    df: pd.DataFrame,
    close_col: str = 'close',
    window: int = 14,
    rsi_col: str = 'rsi',
    fillna: bool = False,
    inplace: bool = False
) -> Optional[pd.DataFrame]:
    """
    Add RSI column to DataFrame.
    
    Args:
        df: pd.DataFrame containing price data
        close_col: str, column name for close price, default is 'close'
        window: int, the period for RSI calculation, default is 14
        rsi_col: str, name for the new RSI column, default is 'rsi'
        fillna: bool, whether to fill NaN values, default is False
        inplace: bool, if True modify df in place and return None; if False return modified copy
    
    Returns:
        pd.DataFrame: Modified DataFrame with RSI column (if inplace=False), or None (if inplace=True)
    """
    if inplace:
        df[rsi_col] = rsi(df[close_col], window=window, fillna=fillna)
        return None
    else:
        result = df.copy()
        result[rsi_col] = rsi(result[close_col], window=window, fillna=fillna)
        return result