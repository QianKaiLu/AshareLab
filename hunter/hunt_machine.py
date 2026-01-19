import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Any, Optional
from tqdm import tqdm
from datas.query_stock import query_all_stock_code_list, query_latest_bars, get_stock_info_by_code, format_stock_info, query_bars_by_days
from tools.log import get_fetch_logger
from dataclasses import dataclass, field

logger = get_fetch_logger()

@dataclass
class HuntInput:
    code: str
    to_date: Optional[str] = None
    days: int = 500
    df: pd.DataFrame = field(init=False)
    
    def dataframe(self) -> pd.DataFrame:
        if hasattr(self, 'df') and self.df is not None:
            return self.df
        df = query_bars_by_days(self.code, days=self.days, to_date=self.to_date)
        self.df = df
        return df

HuntInputLike = str | HuntInput

@dataclass
class HuntResult:
    code: str
    result_info: Any
    input: Optional[HuntInputLike]
    stockInfo: pd.DataFrame = field(default_factory=pd.DataFrame, init=False)
    format_info: str = field(default="", init=False)
    name: str = field(default="", init=False)

    def __post_init__(self):
        if self.stockInfo.empty:
            self.stockInfo = get_stock_info_by_code(self.code)
        if not self.format_info:
            self.format_info = format_stock_info(self.stockInfo, level='brief')
        if not self.name:
            self.name = self.stockInfo['name'].values[0] if not self.stockInfo.empty else ""
            
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
    def __init__(self, max_workers: int = 8, on_result_found: Optional[Callable[[HuntResult], None]] = None):
        """
        Initialize HuntMachine.

        Args:
            max_workers: Number of concurrent workers for parallel processing
            on_result_found: Optional callback function that gets called immediately when a match is found.
                           The callback receives a HuntResult object as parameter.
        """
        self.max_workers = max_workers
        self.on_result_found = on_result_found

    def hunt(self, analyzer: Callable[[pd.DataFrame], Any], min_bars: int = 500, hunt_pool: Optional[List[HuntInputLike]] = None) -> List[HuntResult]:
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
        pool = []
        if hunt_pool is None:
            pool = query_all_stock_code_list()
        else:
            pool = hunt_pool
        results: list[HuntResult] = []
        
        logger.info(f"🏹 Start hunting among {len(pool)} inputs...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._process_stock, input, analyzer, min_bars): (input.code if isinstance(input, HuntInput) else input)
                for input in pool
            }
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="Hunting"):
                code = futures[future]
                try:
                    result: Optional[HuntResult] = future.result()
                    if result:
                        results.append(result)
                        # Trigger callback immediately when a result is found
                        if self.on_result_found:
                            try:
                                self.on_result_found(result)
                            except Exception as callback_error:
                                logger.error(f"Error in callback for {code}: {callback_error}")
                except Exception as e:
                    logger.error(f"Error processing {code}: {e}")
                    
        logger.info(f"✅ Hunt finished. Found {len(results)} matches.")
        return results

    def _process_stock(self, input: HuntInputLike, analyzer: Callable[[pd.DataFrame], Any], min_bars: int) -> Optional[HuntResult]:
        # Fetch data
        if isinstance(input, HuntInput):
            code = input.code
            df = input.dataframe()
        else:
            code = input
            df = query_latest_bars(code, n=min_bars)
        
        if df.empty or len(df) < min_bars:
            return None
            
        # Apply analyzer
        try:
            res = analyzer(df)
            if res:
                return HuntResult(code, res, input)
        except Exception as e:
            # logger.debug(f"Analyzer failed for {code}: {e}") # Optional: debug log
            pass
            
        return None