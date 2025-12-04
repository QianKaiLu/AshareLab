from tools.path import export_file_path
from draws.kline_card import make_kline_card, save_img_file
from draws.kline_theme import ThemeRegistry, KlineTheme
from datas.query_stock import get_stock_info_by_code, get_stock_info_by_name, get_latest_date_by_code
import webbrowser
from datetime import datetime

theme_name = "vintage_ticker"

stock_info = get_stock_info_by_name("比亚迪")
code = stock_info.index[0]
latest_date = get_latest_date_by_code(code) or datetime.now()

theme = ThemeRegistry.get(name=theme_name)
name = stock_info.at[code, 'name']

img = make_kline_card(code=code, n=60, width=600, height=500, theme_name=theme_name)
file_path = export_file_path(filename=f"{name}({code})_{latest_date.strftime('%Y%m%d')}_card", format="png")

save_img_file(img, file_path)
webbrowser.open(file_path.resolve().as_uri())