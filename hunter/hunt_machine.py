import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Any, Optional
from tqdm import tqdm
from datas.query_stock import query_all_stock_code_list, query_latest_bars, get_stock_info_by_code, format_stock_info
from tools.log import get_fetch_logger
from dataclasses import dataclass, field

logger = get_fetch_logger()
    
@dataclass
class HuntResult:
    code: str
    result_info: Any
    stockInfo: pd.DataFrame = field(default_factory=pd.DataFrame, init=False)
    format_info: str = field(default="", init=False)

    def __post_init__(self):
        if self.stockInfo.empty:
            self.stockInfo = get_stock_info_by_code(self.code)
        if not self.format_info:
            self.format_info = format_stock_info(self.stockInfo, level='brief')
            
    def __repr__(self):
        return self.format_info
    
    def __eq__(self, other):
        if not isinstance(other, HuntResult):
            return False
        return self.code == other.code
    
    def __hash__(self):
        return hash(self.code)
    
    @staticmethod
    def union(left: List['HuntResult'], right: List['HuntResult']) -> List['HuntResult']:
        result_dict = {res.code: res for res in left}
        for res in right:
            if res.code not in result_dict:
                result_dict[res.code] = res
        return list(result_dict.values())
    
    @staticmethod
    def intersection(left: List['HuntResult'], right: List['HuntResult']) -> List['HuntResult']:
        right_codes = {res.code for res in right}
        return [res for res in left if res.code in right_codes]

class HuntMachine:
    def __init__(self, max_workers: int = 8):
        self.max_workers = max_workers

    def hunt(self, analyzer: Callable[[pd.DataFrame], Any], min_bars: int = 365, hunt_pool: Optional[List[str]] = None) -> List[HuntResult]:
        """
        Scan all stocks and apply the analyzer function.
        
        Args:
            analyzer: A function that takes a DataFrame (daily bars) and returns a truthy value if the stock matches.
                      The return value can be a boolean or any object (e.g., a dict with details).
            min_bars: Minimum number of bars required for the analyzer.
            hunt_pool: A list of stock codes to analyze.

        Returns:
            A list of HuntResult objects for stocks that matched the analyzer criteria.
        """
        stock_codes = []
        if hunt_pool is None:
            stock_codes = query_all_stock_code_list()
        else:
            stock_codes = hunt_pool
        results: list[HuntResult] = []
        
        logger.info(f"🏹 Start hunting among {len(stock_codes)} stocks...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_stock, code, analyzer, min_bars): code
                for code in stock_codes
            }
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="Hunting"):
                code = futures[future]
                try:
                    result: Optional[HuntResult] = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Error processing {code}: {e}")
                    
        logger.info(f"✅ Hunt finished. Found {len(results)} matches.")
        return results

    def _process_stock(self, code: str, analyzer: Callable[[pd.DataFrame], Any], min_bars: int) -> Optional[HuntResult]:
        # Fetch data
        df = query_latest_bars(code, n=min_bars)
        if df.empty or len(df) < min_bars:
            return None
            
        # Apply analyzer
        try:
            res = analyzer(df)
            if res:
                return HuntResult(code, res)
        except Exception as e:
            # logger.debug(f"Analyzer failed for {code}: {e}") # Optional: debug log
            pass
            
        return None