import time
from datetime import timedelta
from tools.log import get_fetch_logger
from datas.query_stock import query_all_stock_code_list
from datas.fetch_all_market import fetch_stock_bars_parallel

logger = get_fetch_logger()
start_time = time.time()

# round 1
fetch_stock_bars_parallel(query_all_stock_code_list(), source="tushare")

# round 2
fetch_stock_bars_parallel(query_all_stock_code_list(), source="tushare")

end_time = time.time()
total_seconds = end_time - start_time
logger.info(f"📊 used: {total_seconds:.2f} seconds ({timedelta(seconds=total_seconds)})") 
