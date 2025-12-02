from dataclasses import dataclass, field
from typing import Dict

@dataclass
class KlineTheme:
    """
    Theme configuration for a K-line (candlestick) chart card.
    Includes color sets for candles, indicators, text, and card layout.
    """

    name: str = "default"

    # Candle colors
    up_color: str = "#EF4846"      # Color for bullish candles
    down_color: str = "#28A85D"    # Color for bearish candles

    # Indicator colors
    bbi_color: str = "#E8AC2B"
    macd_color: str = "#4E79A7"
    quick_line_color: str = "#F3E9E0"  # Fast moving average line
    slow_line_color: str = "#4C68A1"   # Slow moving average line
    line_color_0: str = "#EDC949" # e.g. kdj k line color
    line_color_1: str = "#AF7AA1" # e.g. kdj d line color
    line_color_2: str = "#FF9DA7" # e.g. kdj j line color
    volume_opacity: float = 0.8

    # Card layout
    grid_color: str = "#333333"
    card_border_color: str = "#444444"
    card_border_width: int = 1
    card_background: str = "#1E1E1E"  # card background color
    plot_background: str = "#1E1E1E" # plot area color
    
    card_corner_radius: int = 6

    # Text styles
    text_color: str = "#FFFFFF"
    font_size: int = 12
    text_font: str = "Arial"

    def invert_candle_colors(self) -> None:
        """
        Swap bullish and bearish candle colors.
        Useful for markets where red means down and green means up.
        """
        self.up_color, self.down_color = self.down_color, self.up_color

class ThemeRegistry:
    """
    Registry for predefined KlineTheme presets.
    Allows easy extension and theme selection by name.
    """

    themes: Dict[str, KlineTheme] = {}

    @classmethod
    def register(cls, theme: KlineTheme) -> None:
        """Register a new theme preset."""
        cls.themes[theme.name] = theme

    @classmethod
    def get(cls, name: str) -> KlineTheme:
        """Retrieve a theme preset by name."""
        return cls.themes.get(name, cls.themes["dark_minimal"])

# Dark Minimalist (default)
ThemeRegistry.register(KlineTheme(
    name="dark_minimal",
    up_color="#EF4846",
    down_color="#28A85D",
    bbi_color="#E8AC2B",
    macd_color="#4E79A7",
    quick_line_color="#F3E9E0",
    slow_line_color="#4C68A1",
    line_color_0="#EDC949",
    line_color_1="#AF7AA1",
    line_color_2="#FF9DA7",
    grid_color="#3A3A3A",
    card_background="#1E1E1E"
))

# Sunset Glow
ThemeRegistry.register(KlineTheme(
    name="sunset_glow",
    up_color="#FF7A59",      # warm orange
    down_color="#4CAF50",    # calm green
    bbi_color="#FFD166",
    macd_color="#EF476F",
    quick_line_color="#F4A261",
    slow_line_color="#E76F51",
    line_color_0="#F2CC8F",
    line_color_1="#E29578",
    line_color_2="#FFCAD4",
    grid_color="#4A3322",
    card_background="#2B1A12",
    plot_background="#2B1A12",
    text_color="#FFEDE2"
))

# 适合白天使用、嵌入白底报告、网页 UI 特点：浅灰背景 + 柔和红绿，不刺眼
ThemeRegistry.register(KlineTheme(
    name="light_fresh",
    up_color="#E74C3C",       # 清晰但不刺眼的红（涨）
    down_color="#27AE60",     # 自然绿（跌）
    bbi_color="#F39C12",
    macd_color="#3498DB",
    quick_line_color="#E67E22",
    slow_line_color="#9B59B6",
    line_color_0="#1ABC9C",
    line_color_1="#2980B9",
    line_color_2="#E91E63",
    volume_opacity=0.9,
    grid_color="#DDDDDD",
    card_background="#FFFFFF",
    plot_background="#FAFAFA",
    card_border_color="#CCCCCC",
    text_color="#2C3E50",
    font_size=12,
    text_font="Segoe UI"
))

# 科技感、专业量化交易员偏好 特点：深蓝黑背景 + 霓虹指示线，突出数据
ThemeRegistry.register(KlineTheme(
    name="deep_space",
    up_color="#00FFA3",       # 荧光青绿（涨）
    down_color="#FF3B30",     # 鲜红（跌）
    bbi_color="#FFD700",
    macd_color="#00BFFF",
    quick_line_color="#FF70A6",
    slow_line_color="#7DF9FF",
    line_color_0="#FF9AA2",
    line_color_1="#FFB7CE",
    line_color_2="#FFDAC1",
    volume_opacity=0.9,
    grid_color="#2A2D3E",
    card_background="#0F0F1B",
    plot_background="#0F0F1B",
    card_border_color="#3A3F58",
    text_color="#E0E0FF",
    font_size=13,
    text_font="Consolas"
))

# 仿 20 世纪股票行情纸带风格 特点：米黄纸色 + 黑墨色蜡烛，怀旧感强
ThemeRegistry.register(KlineTheme(
    name="vintage_ticker",
    up_color="#2E294E",       # 深紫黑（代表“上涨”用实心）
    down_color="#B2996E",     # 古铜金（代表“下跌”用空心，但此处用颜色区分）
    bbi_color="#8C6A4F",
    macd_color="#5D4037",
    quick_line_color="#7B6B5D",
    slow_line_color="#A68A64",
    line_color_0="#C19A6B",
    line_color_1="#8B7355",
    line_color_2="#D2B48C",
    volume_opacity=0.9,
    grid_color="#D7CCC8",
    card_background="#F4F1ED",  # 米白色，像旧纸
    plot_background="#F4F1ED",
    card_border_color="#C5B3A0",
    text_color="#3E2723",
    font_size=12,
    text_font="Georgia"
))

# 低饱和度、护眼、适合长时间盯盘 特点：莫兰迪色系，减少视觉疲劳
ThemeRegistry.register(KlineTheme(
    name="muted_pastel",
    up_color="#D8A7A7",       # 灰粉红（涨）
    down_color="#A8C3B1",     # 灰青绿（跌）
    bbi_color="#C5A8C0",
    macd_color="#A9B8D0",
    quick_line_color="#D1C4A9",
    slow_line_color="#B5A3C1",
    line_color_0="#C2B2B7",
    line_color_1="#AFC2B8",
    line_color_2="#D0B8C5",
    volume_opacity=0.65,
    grid_color="#4A4A4A",
    card_background="#2A2A2A",
    plot_background="#2A2A2A",
    card_border_color="#555555",
    text_color="#E0E0E0",
    font_size=12,
    text_font="Helvetica Neue"
))
