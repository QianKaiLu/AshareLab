import akshare as ak
from datas.fetch_stock_bars import update_daily_bars_for_code, query_daily_bars
from tools.export import export_bars_to_csv
from tools.log import get_analyze_logger
from datas.query_stock import get_stock_info_by_code, format_stock_info
from ai.ai_kbar_analyses import analyze_kbar_data_openai
from tools.markdown_lab import save_md_to_file_name, render_markdown_to_image_file_name

logger = get_analyze_logger()

# input parameters
code = '600026'
from_date = '20241113'

stock_info = get_stock_info_by_code(code)
if stock_info is not None and not stock_info.empty:
    logger.info(format_stock_info(df=stock_info))

logger.info("Updating daily bars...")
update_daily_bars_for_code(code)
logger.info("✅ Done updating.")

df = query_daily_bars(code=code, from_date=from_date)

if df is not None and not df.empty:
    path = export_bars_to_csv(df, only_base_info=True)
    try:
        recent_news = ak.stock_news_em(symbol=code).to_dict(orient='records')
    except Exception as e:
        recent_news = None
    
    if path is not None:
        logger.info(f"Exported bars to {path}, starting AI analysis...")
        md_content = analyze_kbar_data_openai(csv_file_path=path,base_info=stock_info.to_dict('list'), recent_news=recent_news)
        if md_content:
            pre_name = f"{code}"
            if not stock_info.empty:
                stock_name = stock_info.at[code, 'name']
                if stock_name:
                    pre_name = f"{stock_name}({code})"
            file_name = f"{pre_name}_分析报告"
            save_md_to_file_name(md_content, file_name)
            render_markdown_to_image_file_name(md_content, file_name, open_folder_after=True)