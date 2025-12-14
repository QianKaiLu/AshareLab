from tools.path import export_file_path
from draws.kline_card import make_kline_card, save_img_file
from draws.kline_theme import ThemeRegistry, KlineTheme
from datas.query_stock import get_stock_info_by_code, get_stock_info_by_name, get_latest_date_by_code
import webbrowser
from datetime import datetime
from draws.card_list.card_list_factory import render_card_list_to_file

theme_name = "desert_dusk"

codes = ['002970', '301189', '603217', '688209']
images = [make_kline_card(code=code, n=60, width=600, height=800, theme_name=theme_name) for code in codes]

date_in_file_name = datetime.now().strftime('%m%d-%H%M')
date_in_title = datetime.now().strftime('%Y-%m-%d')
file_path = export_file_path(filename=f"list_{date_in_file_name}", format="png")

render_card_list_to_file(output_path=file_path, 
                         title = "热门图形", 
                         desc = f"{date_in_title}", 
                         note = "投资有风险，入市需谨慎",
                         images=images,
                         theme_name=theme_name,
                         open_folder_after=True)