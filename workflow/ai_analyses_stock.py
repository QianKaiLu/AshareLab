import akshare as ak
from datas.fetch_stock_bars import update_daily_bars_for_code, query_daily_bars
from tools.export import export_bars_to_csv
from tools.log import get_analyze_logger
from datas.query_stock import get_stock_info_by_code, format_stock_info
from ai.ai_kbar_analyses import analyze_kbar_data_openai
from tools.markdown_lab import save_md_to_file_name, render_markdown_to_image_file_name
from draws.kline_card import make_kline_card, save_img_file
from tools.path import export_file_path

logger = get_analyze_logger()

# input parameters
code = '002959'
from_date = '20250102'

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
        print("Fetching recent news...")
        recent_news = ak.stock_news_em(symbol=code).to_dict(orient='records')
    except Exception as e:
        recent_news = None
        logger.warning(f"Error fetching recent news: {e}")

    if recent_news is not None:
        logger.info(f"Fetched {len(recent_news)} recent news articles.")

    if path is not None:
        logger.info("📈 Generating K-line chart image...")
        img = make_kline_card(code=code, n=60, theme_name="vintage_ticker_pro")
        img_file_path = export_file_path(filename=f"{code}_card", format="png")
        save_img_file(img, img_file_path)
        logger.info(f"💾 Saved K-line chart image to {img_file_path}")

        logger.info(f"📊 Exported bars to {path}, starting AI analysis...")
        kline_chart_name = img_file_path.resolve().as_uri()
        logger.info(f"🌐 K-line chart URI: {kline_chart_name}")

        logger.info("🤖 Analyzing K-bar data with AI...")
        md_content = analyze_kbar_data_openai(
            csv_file_path=path,
            base_info=stock_info.to_dict('list'),
            recent_news=recent_news,
            kline_chart_name=kline_chart_name
        )

        if md_content:
            # 默认用 code 命名，若有名称则使用「名称(code)」格式
            stock_name = stock_info.at[code, 'name'] if not stock_info.empty else None
            pre_name = f"{stock_name}({code})" if stock_name else code

            file_name = f"{pre_name}_分析报告"
            logger.info(f"📝 Generated markdown report content for {pre_name}")

            save_md_to_file_name(md_content, file_name)
            logger.info(f"📁 Markdown saved as: {file_name}.md")

            render_markdown_to_image_file_name(md_content, file_name, open_folder_after=True)
            logger.info(f"🖼️ Rendered and opened image report for {file_name}")
