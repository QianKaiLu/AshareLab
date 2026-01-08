from tools.path import export_file_path
from draws.kline_card import make_kline_card, save_img_file
from draws.kline_theme import ThemeRegistry, KlineTheme
from datas.query_stock import get_stock_info_by_code, get_stock_info_by_name, get_latest_date_by_code
import webbrowser
from datetime import datetime
from draws.card_list.card_list_factory import render_card_list_to_file
from dataclasses import dataclass, field
from hunter.hunt_machine import HuntMachine, HuntResult, HuntInputLike, HuntInput

theme_name = "dark_minimal"

def draw_hunt_results(hunt_results: list[HuntResult], title: str = "Hunt Results", desc: str = "", theme_name: str = "dark_minimal"):
    codes = []
    images = []
    for result in hunt_results:
        code = result.code
        input = result.input
        if isinstance(input, HuntInput):
            img = make_kline_card(code=code, n=60, width=600, height=800, to_date=input.to_date, theme_name=theme_name)
        else:
            img = make_kline_card(code=code, n=60, width=600, height=800, theme_name=theme_name)
        images.append(img)
        codes.append(code)

    date_in_file_name = datetime.now().strftime('%m%d-%H%M%S')
    file_path = export_file_path(filename=f"hunt_list_{date_in_file_name}", format="png")

    render_card_list_to_file(output_path=file_path, 
                             title = title, 
                             desc = desc, 
                             note = "",
                             images=images,
                             theme_name=theme_name,
                             open_folder_after=True)