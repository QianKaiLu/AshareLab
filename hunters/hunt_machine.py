import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Any, Optional
from tqdm import tqdm
from datas.query_stock import query_all_stock_code_list, query_latest_bars
from tools.log import get_fetch_logger

logger = get_fetch_logger()

class HuntMachine:
    def __init__(self, max_workers: int = 8):
        self.max_workers = max_workers

    def hunt(self, analyzer: Callable[[pd.DataFrame], Any], min_bars: int = 30, hunt_pool: Optional[List[str]] = None) -> List[str]:
        """
        Scan all stocks and apply the analyzer function.
        
        Args:
            analyzer: A function that takes a DataFrame (daily bars) and returns a truthy value if the stock matches.
                      The return value can be a boolean or any object (e.g., a dict with details).
            min_bars: Minimum number of bars required for the analyzer.
            hunt_pool: A list of stock codes to analyze.

        Returns:
            A list of results. If the analyzer returns a boolean, it returns the stock codes where it was True.
            If the analyzer returns other objects, it returns a list of (code, result) tuples.
        """
        stock_codes = []
        if hunt_pool is None:
            stock_codes = query_all_stock_code_list()
        else:
            stock_codes = hunt_pool
        results = []
        
        logger.info(f"🏹 Start hunting among {len(stock_codes)} stocks...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_stock, code, analyzer, min_bars): code
                for code in stock_codes
            }
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="Hunting"):
                code = futures[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error processing {code}: {e}")
                    
        logger.info(f"✅ Hunt finished. Found {len(results)} matches.")
        return results

    def _process_stock(self, code: str, analyzer: Callable[[pd.DataFrame], Any], min_bars: int) -> Optional[Any]:
        # Fetch data
        df = query_latest_bars(code, n=min_bars)
        if df.empty or len(df) < min_bars:
            return None
            
        # Apply analyzer
        try:
            res = analyzer(df)
            if res:
                # If boolean True, return code. If object, return (code, object)
                if isinstance(res, bool):
                    return code
                else:
                    return (code, res)
        except Exception as e:
            # logger.debug(f"Analyzer failed for {code}: {e}") # Optional: debug log
            pass
            
        return None
