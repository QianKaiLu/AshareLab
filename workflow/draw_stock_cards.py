from tools.path import export_file_path
from draws.kline_card import make_kline_card, save_img_file
from draws.kline_theme import ThemeRegistry, KlineTheme
from datas.query_stock import get_stock_info_by_code, get_stock_info_by_name, get_latest_date_by_code
import webbrowser
from datetime import datetime
from draws.card_list.card_list_factory import render_card_list_to_file
from dataclasses import dataclass, field

theme_name = "dark_minimal"

@dataclass
class Scope:
    codes: list = field(default_factory=list)
    title: str = ""
    note: str = ""

ev_scope = Scope(
    codes=['600418', '601127', '002594'],
    title="ev 三傻",
    note=""
)

aidi_scope = Scope(
    codes=['601888', '300394', '002594', '002460'],
    title="艾迪概念股",
    note=""
)

scope = aidi_scope
codes = scope.codes
images = [make_kline_card(code=code, n=60, width=600, height=800, theme_name=theme_name) for code in codes]

date_in_file_name = datetime.now().strftime('%m%d-%H%M')
date_in_title = datetime.now().strftime('%Y-%m-%d')
file_path = export_file_path(filename=f"list_{date_in_file_name}", format="png")

render_card_list_to_file(output_path=file_path, 
                         title = scope.title, 
                         desc = f"{date_in_title}", 
                         note = scope.note,
                         images=images,
                         theme_name=theme_name,
                         open_folder_after=True)