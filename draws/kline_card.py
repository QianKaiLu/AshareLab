import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datas.query_stock import query_latest_bars
from pathlib import Path
import plotly.io as pio
from PIL import Image, ImageOps, ImageDraw, ImageFile
import io
import base64
from draws.kline_fig_factory import standard_fig
from draws.kline_theme import ThemeRegistry, KlineTheme
from draws.figs_factory.ztalk_fig_v2 import ztalk_fig_v2
from typing import Optional

def add_rounded_rectangle_border(
    image: Image.Image, radius: int, border_color, border_width: int
) -> Image.Image:
    
    img = image.convert("RGBA")
    w, h = img.size
 
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (w, h)], radius=radius, fill=255
    )
  
    border_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    inner_w = w - 2 * border_width
    inner_h = h - 2 * border_width
    adjusted_radius = min(radius, inner_w // 2, inner_h // 2)
    ImageDraw.Draw(border_layer).rounded_rectangle(
        (border_width, border_width, w - border_width, h - border_width),
        radius=adjusted_radius,
        outline=border_color,
        width=border_width
    )

    result = Image.composite(img, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask)
    result = Image.alpha_composite(result, border_layer)
    return result

def make_kline_card(code: str, n: int = 60, width: int = 600, height: int = 800, to_date: Optional[str] = None, theme_name: str = "vintage_ticker") -> Image.Image:
    fig = ztalk_fig_v2(code=code, n=n, width=width, height=height, to_date=to_date, theme_name=theme_name)
    theme = ThemeRegistry.get(name=theme_name)
    img_bytes = fig.to_image(format="png", width=width, height=height, scale=3)
    img = Image.open(io.BytesIO(img_bytes))
    img = add_rounded_rectangle_border(img, radius=20, border_color=theme.card_border_color, border_width=5)
    return img
    
def save_img_file(img: Image.Image, path: Path):
    img.save(path, format="PNG")
    
def card_to_base64(img: Image.Image) -> str:
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


if __name__ == "__main__":
    # code = '600423'
    # img = make_kline_card(code=code, n=60, width=600, height=500, theme_name="vintage_ticker")
    # img.show()
    
    codes = ['600423', '600519', '000001']
    base64_cards = [card_to_base64(make_kline_card(code=code, n=60, width=600, height=450, theme_name="vintage_ticker")) for code in codes]
    print(base64_cards)