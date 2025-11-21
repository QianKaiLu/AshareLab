import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hunters.hunt_machine import HuntMachine
import pandas as pd

def simple_analyzer(df: pd.DataFrame) -> bool:
    """
    Simple analyzer: checks if the latest close is higher than the open.
    """
    if df.empty:
        return False
    latest = df.iloc[-1]
    return latest['close'] > latest['open']

def test_hunt_machine():
    print("🚀 Starting HuntMachine test...")
    hunter = HuntMachine(max_workers=4)
    
    # We can't easily mock the database here without more setup, 
    # so we'll run it on the real data but maybe we can limit it?
    # The current implementation scans ALL stocks. 
    # For a quick test, we might want to modify HuntMachine to accept a list of codes, 
    # but for now let's just run it and see if it crashes. 
    # It might take a while if there are many stocks.
    # To make it faster, we can rely on the fact that it prints progress.
    # Or we can just trust it works if it starts processing.
    
    # Actually, let's modify HuntMachine slightly to allow passing a subset of codes for testing?
    # Or just monkeypatch query_all_stock_code_list.
    
    from unittest.mock import patch
    
    # Mocking query_all_stock_code_list to return a small subset
    with patch('hunters.hunt_machine.query_all_stock_code_list') as mock_query:
        # Return a few real codes if possible, or just some dummy ones if we can't easily get real ones.
        # Let's try to get a few real codes first.
        from datas.query_stock import query_all_stock_code_list as real_query
        all_codes = real_query()
        mock_query.return_value = all_codes[:10] # Test with first 10 stocks
        
        print(f"Testing with {len(mock_query.return_value)} stocks...")
        
        results = hunter.hunt(simple_analyzer, min_bars=5)
        
        print(f"Found {len(results)} matches.")
        print("Matches:", results)

if __name__ == "__main__":
    test_hunt_machine()
