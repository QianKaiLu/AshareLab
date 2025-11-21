import pandas as pd
from typing import Optional, Dict, Any

def analyze_breakout_pullback(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Analyzes if a stock fits the 'Low Volume Pullback after Breakout' strategy.
    
    Strategy Logic:
    1. Trend: Price > MA20 (Uptrend).
    2. Momentum: Max gain in last 15 days > 15% (Strong breakout recently).
    3. Pullback: Current close < 5-day High (Pullback occurring).
    4. Volume: Current volume < 5-day Average Volume * 0.7 (Volume drying up).
    
    Args:
        df: DataFrame containing daily bars (must have 'close', 'open', 'high', 'low', 'volume').
            Assumes df is sorted by date ascending.
            
    Returns:
        A dictionary with details if it matches, otherwise None.
    """
    if df.empty or len(df) < 30:
        return None
        
    # Ensure we work with the latest data
    latest = df.iloc[-1]
    
    # 1. Trend: Price > MA20
    ma20 = df['close'].rolling(20).mean().iloc[-1]
    if latest['close'] <= ma20:
        return None
        
    # 2. Momentum: Max gain in last 15 days > 15%
    # We look at the max close in the last 15 days vs the min close in the 15 days before that high?
    # Or simply: (Max High in last 15 days) / (Min Low in last 15 days) > 1.15?
    # Let's use a simpler metric: Max Close in last 15 days / Close 15 days ago > 1.15
    # Or even better: Max daily return in last 15 days was > 5%? 
    # Let's stick to the plan: "Surged at least 15% in the last 15 days"
    # We can check if (Max High of last 15 days) / (Min Low of last 15 days) > 1.15
    recent_15 = df.iloc[-15:]
    max_price = recent_15['high'].max()
    min_price = recent_15['low'].min()
    
    if min_price == 0: return None # Avoid division by zero
    
    gain = (max_price - min_price) / min_price
    if gain < 0.15:
        return None
        
    # 3. Pullback: Current close < 5-day High
    recent_5 = df.iloc[-5:]
    high_5 = recent_5['high'].max()
    if latest['close'] >= high_5:
        # It's still making new highs, not a pullback
        return None
        
    # 4. Volume Contraction: Volume < MA5_Vol * 0.7
    vol_ma5 = recent_5['volume'].mean()
    if vol_ma5 == 0: return None
    
    vol_ratio = latest['volume'] / vol_ma5
    if vol_ratio > 0.7:
        return None
        
    return {
        "price": latest['close'],
        "ma20": round(ma20, 2),
        "recent_gain_pct": round(gain * 100, 2),
        "pullback_from_high": round((latest['close'] - high_5) / high_5 * 100, 2),
        "vol_ratio": round(vol_ratio, 2)
    }
