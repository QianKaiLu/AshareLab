from datas.fetch_stock_bars import update_daily_bars_for_code, query_daily_bars
from tools.export import export_bars_to_csv
from tools.log import get_fetch_logger
from datas.query_stock import get_stock_info_by_code, format_stock_info

logger = get_fetch_logger()

code = '601127'

stock_info = get_stock_info_by_code(code)
if stock_info is not None and not stock_info.empty:
    logger.info(format_stock_info(df=stock_info))

update_daily_bars_for_code(code)

logger.info("Exporting...")

df = query_daily_bars(code=code, from_date='20241113')
if df is not None and not df.empty:
    path = export_bars_to_csv(df, only_base_info=True, open_folder_after=True)
    if path is not None:
        logger.info(f"Exported bars to {path}")