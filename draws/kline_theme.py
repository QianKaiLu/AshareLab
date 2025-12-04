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
    
    card_corner_radius: int = 20

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

# 深海幽蓝 - 深色背景配合明亮线条，科技感强
ThemeRegistry.register(KlineTheme(
    name="deep_ocean",
    up_color="#00B4D8",       # 明亮的青蓝（涨）
    down_color="#FF6B6B",     # 珊瑚红（跌）
    bbi_color="#FFD166",      # 金黄 - 与主色形成强对比
    macd_color="#9D4EDD",     # 紫色 - 明显区别于主色
    quick_line_color="#4CC9F0", # 浅蓝 - 快速线
    slow_line_color="#4361EE",  # 深蓝 - 慢速线
    line_color_0="#F72585",   # 玫红 - KDJ K线
    line_color_1="#7209B7",   # 深紫 - KDJ D线
    line_color_2="#38B000",   # 鲜绿 - KDJ J线
    volume_opacity=0.7,
    grid_color="#1A3A5F",     # 深蓝网格
    card_background="#0A192F", # 深海蓝背景
    plot_background="#0A192F",
    card_border_color="#1E4D8C",
    text_color="#E2E8F0",
    font_size=12,
    text_font="Inter"
))

# 沙漠黄昏 - 暖色调主题，适合夜间使用
ThemeRegistry.register(KlineTheme(
    name="desert_dusk",
    up_color="#F94144",       # 鲜红（涨）
    down_color="#90BE6D",     # 橄榄绿（跌）
    bbi_color="#F9C74F",      # 金黄 - 在暖色背景中突出
    macd_color="#577590",     # 冷蓝 - 与暖主色形成反差
    quick_line_color="#F8961E", # 橙色 - 快速线
    slow_line_color="#43AA8B",  # 青绿 - 慢速线
    line_color_0="#FF5A8C",   # 粉红 - KDJ K线
    line_color_1="#9A4C95",   # 紫红 - KDJ D线
    line_color_2="#2A9D8F",   # 青蓝 - KDJ J线
    volume_opacity=0.75,
    grid_color="#5A3A22",     # 深棕网格
    card_background="#2D1B0E", # 深巧克力背景
    plot_background="#2D1B0E",
    card_border_color="#7A5C3C",
    text_color="#F8F3E6",
    font_size=12,
    text_font="Roboto"
))

# 赛博霓虹 - 荧光色系，高对比度
ThemeRegistry.register(KlineTheme(
    name="cyber_neon",
    up_color="#00FF88",       # 荧光绿（涨）
    down_color="#FF0080",     # 荧光粉（跌）
    bbi_color="#FFE600",      # 荧光黄 - 最亮的颜色用于重要指标
    macd_color="#00D4FF",     # 荧光青 - 与主色色相区分
    quick_line_color="#FF7A00", # 橙色 - 明度较高
    slow_line_color="#8A2BE2",  # 紫色 - 明度较低
    line_color_0="#FF2600",   # 荧光红 - KDJ K线
    line_color_1="#2600FF",   # 荧光蓝 - KDJ D线
    line_color_2="#00FFFB",   # 荧光青 - KDJ J线
    volume_opacity=0.6,
    grid_color="#222222",     # 深灰网格
    card_background="#0A0A0A", # 纯黑背景
    plot_background="#0A0A0A",
    card_border_color="#444444",
    text_color="#FFFFFF",
    font_size=12,
    text_font="Montserrat"
))

# 北欧极光 - 冷色调，清爽干净
ThemeRegistry.register(KlineTheme(
    name="nordic_aurora",
    up_color="#4ECDC4",       # 青绿（涨）
    down_color="#FF6B6B",     # 粉红（跌）
    bbi_color="#FFE66D",      # 亮黄 - 在冷色调中突出
    macd_color="#6A0572",     # 深紫 - 明度差异大
    quick_line_color="#1A535C", # 深青 - 快速线
    slow_line_color="#4ECDC4",  # 主青 - 慢速线
    line_color_0="#FF6B6B",   # 粉红 - KDJ K线
    line_color_1="#1A535C",   # 深青 - KDJ D线
    line_color_2="#FFE66D",   # 亮黄 - KDJ J线
    volume_opacity=0.8,
    grid_color="#34495E",     # 钢蓝网格
    card_background="#2C3E50", # 深蓝灰背景
    plot_background="#2C3E50",
    card_border_color="#5D6D7E",
    text_color="#ECF0F1",
    font_size=12,
    text_font="Open Sans"
))

# 莫奈花园 - 印象派色彩，柔和而区分清晰
ThemeRegistry.register(KlineTheme(
    name="monet_garden",
    up_color="#E74C3C",       # 朱红（涨）- 保持一定饱和度
    down_color="#27AE60",     # 翡翠绿（跌）
    bbi_color="#F39C12",      # 琥珀色
    macd_color="#8E44AD",     # 紫罗兰
    quick_line_color="#3498DB", # 天蓝 - 明度较高
    slow_line_color="#2C3E50",  # 深蓝 - 明度较低
    line_color_0="#E67E22",   # 南瓜橙 - KDJ K线
    line_color_1="#16A085",   # 绿松石 - KDJ D线
    line_color_2="#C0392B",   # 深红 - KDJ J线
    volume_opacity=0.7,
    grid_color="#BDC3C7",     # 浅灰网格
    card_background="#ECF0F1", # 浅灰背景
    plot_background="#FFFFFF",
    card_border_color="#95A5A6",
    text_color="#2C3E50",
    font_size=12,
    text_font="Lato"
))

# 石墨工业 - 专业交易风格
ThemeRegistry.register(KlineTheme(
    name="graphite_industrial",
    up_color="#2ECC71",       # 亮绿（涨）
    down_color="#E74C3C",     # 亮红（跌）
    bbi_color="#F1C40F",      # 金色 - 工业警示色
    macd_color="#3498DB",     # 工业蓝
    quick_line_color="#E67E22", # 橙色 - 高可见性
    slow_line_color="#95A5A6",  # 灰色 - 中性背景
    line_color_0="#9B59B6",   # 紫色 - 清晰区分
    line_color_1="#1ABC9C",   # 青色 - 高识别度
    line_color_2="#E91E63",   # 玫红 - 强对比
    volume_opacity=0.75,
    grid_color="#444444",     # 中灰网格
    card_background="#1C1C1C", # 深灰背景
    plot_background="#1C1C1C",
    card_border_color="#555555",
    text_color="#F5F5F5",
    font_size=12,
    text_font="SF Mono"
))

# 复古纸带增强版 - 保持怀旧感的同时增强线条区分度
ThemeRegistry.register(KlineTheme(
    name="vintage_ticker_enhanced",
    up_color="#2E294E",       # 深紫黑（上涨）- 像墨迹
    down_color="#B2996E",     # 古铜金（下跌）- 像褪色的墨水
    
    # 增强指标线颜色 - 使用更饱和的复古色调
    bbi_color="#8B4513",      # 马鞍棕 - 更深的棕色，在米色背景上更醒目
    macd_color="#556B2F",     # 橄榄绿 - 复古报纸上常用的绿色
    
    quick_line_color="#A0522D", # 赭石色 - 快速线，比原版更深
    slow_line_color="#8B7355",  # 卡其色 - 慢速线，保持复古感
    
    # KDJ三条线使用更有区分度的复古色
    line_color_0="#B22222",   # 砖红 - K线，在米色背景上清晰
    line_color_1="#2F4F4F",   # 深石板灰 - D线，中性色
    line_color_2="#8B6914",   # 金褐色 - J线，略带金属感
    
    volume_opacity=0.9,
    
    # 布局微调
    grid_color="#C5B3A0",     # 浅褐网格 - 保持柔和但更清晰
    card_background="#F4F1ED", # 米白色，像旧纸
    plot_background="#F4F1ED",
    card_border_color="#C5B3A0",
    text_color="#3E2723",
    font_size=12,
    text_font="Georgia"
))

# 复古纸带专业版 - 更强的对比度，适合分析
ThemeRegistry.register(KlineTheme(
    name="vintage_ticker_pro",
    up_color="#1A1A2E",       # 更深的海军蓝（上涨）
    down_color="#8B7355",     # 卡其棕（下跌）
    
    # 高对比度指标线 - 保持复古色调但更鲜明
    bbi_color="#B8860B",      # 暗金 - 像旧金器
    macd_color="#2E8B57",     # 海绿 - 复古但清晰
    
    quick_line_color="#8B0000", # 深红 - 快速线，明显可见
    slow_line_color="#4682B4",  # 钢蓝 - 慢速线，冷色调区分
    
    # KDJ线 - 使用互补色增强区分
    line_color_0="#8B4513",   # 马鞍棕 - K线（深棕）
    line_color_1="#4B0082",   # 靛蓝 - D线（深紫蓝）
    line_color_2="#CD853F",   # 秘鲁色 - J线（浅棕橙）
    
    volume_opacity=0.85,
    grid_color="#B0A18E",     # 稍深的网格线
    card_background="#F5F0E6", # 暖米色，略带黄色调
    plot_background="#F5F0E6",
    card_border_color="#C1A78E",
    text_color="#2C1810",     # 更深的中性灰黑
    font_size=13,             # 稍大的字体
    text_font="Palatino Linotype"  # 更优雅的衬线字体
))

# 复古报纸风格 - 灵感来自旧报纸印刷
ThemeRegistry.register(KlineTheme(
    name="vintage_newspaper",
    up_color="#333333",       # 报纸黑（上涨）
    down_color="#8C7B6E",     # 报纸灰（下跌）
    
    # 使用报纸印刷的典型颜色
    bbi_color="#8B0000",      # 报纸标题红
    macd_color="#006400",     # 报纸深绿
    
    quick_line_color="#8B4513", # 新闻纸棕色
    slow_line_color="#4682B4",  # 报纸蓝
    
    # KDJ线 - 像报纸上的彩色插图
    line_color_0="#A52A2A",   # 褐红
    line_color_1="#2E8B57",   # 海绿
    line_color_2="#D2691E",   # 巧克力色
    
    volume_opacity=0.8,
    grid_color="#D4C4B0",     # 浅褐网格
    card_background="#FAF3E6", # 新闻纸黄
    plot_background="#FAF3E6",
    card_border_color="#C9B8A4",
    text_color="#2C1810",
    font_size=12,
    text_font="Arial"
))

# 老式行情机风格 - 灵感来自老式电报机
ThemeRegistry.register(KlineTheme(
    name="old_ticker_tape",
    up_color="#191970",       # 午夜蓝（上涨）
    down_color="#A0522D",     # 赭石色（下跌）
    
    # 老式机器的颜色
    bbi_color="#DAA520",      # 金秋色 - 像铜质部件
    macd_color="#5F9EA0",     # 军械蓝 - 老机器色
    
    quick_line_color="#CD5C5C", # 印第安红 - 快速变化
    slow_line_color="#6B8E23",  # 橄榄军绿 - 稳定
    
    # KDJ线 - 使用老式仪表盘颜色
    line_color_0="#8B0000",   # 暗红
    line_color_1="#008080",   # 凫绿
    line_color_2="#D2691E",   # 巧克力橙
    
    volume_opacity=0.75,
    grid_color="#B8A28A",     # 古董白网格
    card_background="#F0E8D8", # 羊皮纸色
    plot_background="#F0E8D8",
    card_border_color="#B8A28A",
    text_color="#3E2C1C",     # 深巧克力色
    font_size=12,
    text_font="Arial"
))