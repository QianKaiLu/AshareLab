import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Any, Optional
from tqdm import tqdm
from datas.query_stock import query_all_stock_code_list, query_latest_bars, get_stock_info_by_code, format_stock_info, query_bars_by_days
from tools.log import get_fetch_logger
from dataclasses import dataclass, field
from datas.stock_index_list import hs300_code_list, csi500_code_list, csi2000_code_list, csi_a500_code_list
from hunter.hunt_machine import HuntInput, HuntInputLike

logger = get_fetch_logger()

def all_stock_hunt_pool(to_date: Optional[str] = None) -> List[HuntInputLike]:
    codes = query_all_stock_code_list()
    return [HuntInput(code=code, to_date=to_date, days=500) for code in codes]

def hs300_hunt_pool(to_date: Optional[str] = None) -> List[HuntInputLike]:
    """Get HuntInput list for HS300 constituent stocks.
    """
    list: pd.Series = hs300_code_list()
    codes = list.tolist()
    return [HuntInput(code=code, to_date=to_date, days=500) for code in codes]

def hs300_csi500_hunt_pool(to_date: Optional[str] = None) -> List[HuntInputLike]:
    """Get HuntInput list for combined HS300 and CSI500 constituent stocks.
    """
    hs300_list: pd.Series = hs300_code_list()
    csi500_list: pd.Series = csi500_code_list()
    combined_codes = pd.Series(pd.concat([hs300_list, csi500_list]).unique())
    codes = combined_codes.tolist()
    return [HuntInput(code=code, to_date=to_date, days=500) for code in codes]

def hs300_csi500_csi2000_hunt_pool(to_date: Optional[str] = None) -> List[HuntInputLike]:
    """Get HuntInput list for combined HS300, CSI500 and CSI2000 constituent stocks.
    """
    hs300_list: pd.Series = hs300_code_list()
    csi500_list: pd.Series = csi500_code_list()
    csi2000_list: pd.Series = csi2000_code_list()
    combined_codes = pd.Series(pd.concat([hs300_list, csi500_list, csi2000_list]).unique())
    codes = combined_codes.tolist()
    return [HuntInput(code=code, to_date=to_date, days=500) for code in codes]