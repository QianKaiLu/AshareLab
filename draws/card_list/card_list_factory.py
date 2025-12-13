from jinja2 import Template
from playwright.sync_api import sync_playwright
import os
from pathlib import Path
from tools.log import get_analyze_logger
import webbrowser
from tools.export import EXPORT_PATH
from typing import Optional
import re
import base64
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from PIL import Image, ImageOps, ImageDraw, ImageFile
from draws.kline_card import card_to_base64
from draws.kline_theme import ThemeRegistry, KlineTheme

logger = get_analyze_logger()

def render_card_list_to_file(output_path: Path, title: str = "", desc: str = "", note = "", images: list[Image.Image] = [], theme_name: str = "vintage_ticker", open_folder_after: bool = False):
    if not images:
        raise ValueError("The images list is empty.")
    
    if not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
    
    theme = ThemeRegistry.get(name=theme_name)
    
    with open(Path(__file__).parent / "vertical_list_v1.jinja") as f:
        template = Template(f.read())
        html_content = template.render(
            title=title,
            text_color=theme.text_color,
            desc=desc,
            note=note,
            images=[card_to_base64(img) for img in images],
            background_color=theme.card_background
        )
        
    if not html_content:
        raise ValueError("Rendered HTML content is empty.")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 600, "height": 1200},
            device_scale_factor=2
        )
        
        # Convert HTML to image
        page.set_content(html_content)
        page.screenshot(path=output_path, full_page=True)
        browser.close()
        
    logger.info(f"🎴 Card list rendered and saved to: {output_path}")
    if open_folder_after:
        webbrowser.open(output_path.parent.as_uri())
    
    