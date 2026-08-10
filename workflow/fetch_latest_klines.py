import time
from datetime import timedelta
from tools.log import get_fetch_logger
from datas.query_stock import query_all_stock_code_list
from datas.fetch_all_market import fetch_stock_bars_parallel

logger = get_fetch_logger()
start_time = time.time()

# round 1: tushare 增量更新（锚定缩放，不调 adj_factor 接口）
failed_codes = fetch_stock_bars_parallel(query_all_stock_code_list(), source="tushare")

# round 2: 只对失败的股票用 akshare qfq 兜底，避免全市场二次压榨东财接口
if failed_codes:
    logger.info(f"Retrying {len(failed_codes)} failed stocks via akshare")
    fetch_stock_bars_parallel(failed_codes, source="akshare")

end_time = time.time()
total_seconds = end_time - start_time
logger.info(f"📊 used: {total_seconds:.2f} seconds ({timedelta(seconds=total_seconds)})")
