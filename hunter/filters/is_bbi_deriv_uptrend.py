import numpy as np
import pandas as pd

"""
Check if BBI derivative indicates an uptrend
Args:
min_window = 20,
max_window = 120,
q_threshold = 0.2,
"""

def is_bbi_deriv_uptrend(
    bbi: pd.Series,
    *,
    min_window: int = 20,
    max_window: int | None = None,
    q_threshold: float = 0.0,
) -> bool:
    if not 0.0 <= q_threshold <= 1.0:
        raise ValueError("q_threshold must be between 0 and 1")

    bbi = bbi.dropna()
    if len(bbi) < min_window:
        return False

    if max_window:
        longest = min(len(bbi), max_window)
    else:
        longest = len(bbi)
    
    for w in range(longest, min_window - 1, -1):
        seg = bbi.iloc[-w:]
        norm = seg / seg.iloc[0]
        diffs = np.diff(norm.values)
        quantile_value = np.quantile(diffs, q_threshold)
        if quantile_value >= 0:
            return True
    return False

def is_price_deriv_uptrend(
    price: pd.Series,
    *,
    min_window: int = 20,
    max_window: int | None = None,
    q_threshold: float = 0.0,
) -> bool:
    if not 0.0 <= q_threshold <= 1.0:
        raise ValueError("q_threshold must be between 0 and 1")

    price = price.dropna()
    if len(price) < min_window:
        return False

    if max_window:
        longest = min(len(price), max_window)
    else:
        longest = len(price)
    
    for w in range(longest, min_window - 1, -1):
        seg = price.iloc[-w:]
        norm = seg / seg.iloc[0]
        diffs = np.diff(norm.values)
        if np.quantile(diffs, q_threshold) >= 0:
            return True
    return False