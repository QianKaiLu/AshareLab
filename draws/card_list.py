import pandas as pd
from datas.query_stock import query_latest_bars
from pathlib import Path
import plotly.io as pio
from PIL import Image, ImageOps, ImageDraw, ImageFile
import io
from draws.kline_fig_factory import standard_fig
from draws.kline_theme import ThemeRegistry, KlineTheme
from tools.colors import hex_to_rgba
from kline_card import make_kline_card, save_img_file

def card_collection_by_cards(cards: list[Image.Image], theme_name: str = "vintage_ticker", title: str = "", subtitle: str = "") -> Image.Image:
    
    if not cards:
        raise ValueError("The cards list is empty.")
    
    theme = ThemeRegistry.get(name=theme_name)
    card_width, card_height = cards[0].size
    
    background_color = hex_to_rgba(theme.card_background, alpha=255)
    
    collection_img = Image.new("RGBA", (card_width, card_height * len(cards)), background_color)
    
    for idx, card_img in enumerate(cards):
        collection_img.paste(card_img, (0, idx * card_height))
    
    return collection_img

def card_collection_by_codes(codes: list[str], n: int = 60, width: int = 600, height: int = 500, theme_name: str = "vintage_ticker", title: str = "", subtitle: str = "") -> Image.Image:
    theme = ThemeRegistry.get(name=theme_name)
    collection_img = Image.new("RGBA", (width, height * len(codes)), hex_to_rgba(theme.card_background, alpha=255))
    
    for idx, code in enumerate(codes):
        card_img = make_kline_card(code=code, n=n, width=width, height=height, theme_name=theme_name)
        collection_img.paste(card_img, (0, idx * height))
    
    return collection_img