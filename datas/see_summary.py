import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datas.query_stock import query_latest_bars, get_stock_info_by_code
from pathlib import Path
from indicators.kdj import add_kdj_to_dataframe
from indicators.macd import add_macd_to_dataframe
from indicators.bbi import add_bbi_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe
from indicators.volume_ma import add_volume_ma_to_dataframe
from draws.kline_theme import ThemeRegistry, KlineTheme
from tools.colors import hex_to_rgba

theme = ThemeRegistry.get(name="muted_pastel")

code = '600423'
stock_info = get_stock_info_by_code(code)
df = query_latest_bars(code=code, n=50)

add_bbi_to_dataframe(df, inplace=True)
add_zxdkx_to_dataframe(df, inplace=True)
add_volume_ma_to_dataframe(df, inplace=True)

width = 600
height = 500

print(df.tail(10))

fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    vertical_spacing=0.02,
    row_heights=[0.75, (0.25-0.02)]
)

# 1. 保留原始 date 列用于标签
dates = df['date'].dt.strftime('%m-%d').tolist()  # 或 '%Y-%m-%d' 看你喜好

# 2. 用整数索引（0, 1, 2, ..., N-1）作为 x 坐标
x_index = list(range(len(df)))

fig.add_trace(
    go.Candlestick(
        x=x_index,
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        increasing=dict(
            fillcolor=theme.up_color,
            line=dict(color=theme.up_color, width=2)),
        decreasing=dict(
            fillcolor=theme.down_color,
            line=dict(color=theme.down_color, width=2)),
        showlegend=False
    ),
    row=1, col=1
)

fig.add_trace(
    go.Scatter(
        x=x_index, 
        y=df['bbi'], 
        mode='lines', 
        name='bbi',
        line=dict(color=theme.bbi_color, width=1.5, dash='dot'),
        showlegend=True
    ),
    row=1, col=1
)

fig.add_trace(
    go.Scatter(
        x=x_index, 
        y=df['z_white'], 
        mode='lines', 
        name='快线',
        line=dict(color=theme.quick_line_color, width=1, dash='solid'),
        showlegend=True
    ),
    row=1, col=1
)

fig.add_trace(
    go.Scatter(
        x=x_index, 
        y=df['z_yellow'], 
        mode='lines', 
        name='慢线',
        line=dict(color=theme.slow_line_color, width=1, dash='solid'),
        showlegend=True
    ),
    row=1, col=1
)

colors = [theme.up_color if c > o else theme.down_color for o, c in zip(df['open'], df['close'])]
fig.add_trace(
    go.Bar(
        x=x_index,
        y=df['volume'],
        name='成交量',
        marker=dict(color=colors, opacity=1.0),
        showlegend=False,
    ),
    row=2, col=1
)

fig.add_trace(
    go.Scatter(
        x=x_index, 
        y=df['volume_ma_5'], 
        mode='lines', 
        name='volume MA5',
        line=dict(color=theme.line_color_0, width=1, dash='solid'),
        showlegend=False
    ),
    row=2, col=1
)

nticks = min(len(dates), 7)
step = max(1, len(dates) // nticks)
tick_indices = list(range(0, len(dates), step))
tick_labels = [dates[i] for i in tick_indices]

fig.update_xaxes(
    tickvals=tick_indices,
    ticktext=tick_labels,
    tickangle= -45,
    tickfont=dict(size=8, color=theme.text_color),
    row=1, col=1
)

fig.update_xaxes(
    tickvals=tick_indices,
    ticktext=tick_labels,
    row=2, col=1
)
    
fig.update_layout(
    title=dict(
        text=f'{stock_info.at[code, 'name']} ({code})',
        x=0.5,
        y=0.96,
        xanchor='center',
        font=dict(size=16, color=theme.text_color, family='sans-serif')
    ),
    plot_bgcolor=theme.card_background,
    paper_bgcolor=theme.card_background,
    font=dict(color=theme.text_color, size=10),
    showlegend=True,
    legend=dict(
        font=dict(size=10, color=theme.text_color),
        orientation='v',
        yanchor='middle',
        y=0.9,
        xanchor='right',
        x=1.02,
        bgcolor=hex_to_rgba(theme.card_background, 0.6)
    ),
    xaxis=dict(
        showgrid=False,
        zeroline=False,
        showticklabels=False,
        rangeslider_visible=False
    ),
    yaxis=dict(
        title='Price',
        title_standoff=10,
        title_font = dict(size=10, color=theme.text_color),
        tickfont = dict(size=8, color=theme.text_color),
        showgrid=True,
        gridcolor=theme.grid_color,
        griddash='dot',
        gridwidth=1,
        fixedrange=True,
        zeroline=True,
        tickformat=".2f"
    ),
    yaxis2=dict(
        title='Volume',
        title_standoff=6,
        title_font = dict(size=10, color=theme.text_color),
        tickfont = dict(size=8, color=theme.text_color),
        showticklabels=True,
        showgrid=True,
        griddash='dot',
        gridwidth=1,
        gridcolor=theme.grid_color,
        fixedrange=True,
        zeroline=True,
        tickformat=".2s"
    ),
    margin=dict(l=40, r=30, t=40, b=30),
    height=height,
    width=width
)

fig.show()

import plotly.io as pio
from PIL import Image, ImageOps, ImageDraw
import io

# 先保存图表到内存中的 PNG
img_bytes = fig.to_image(format="png", width=width, height=height, scale=4)  # scale 提高清晰度

# 用 PIL 打开图像并处理
img = Image.open(io.BytesIO(img_bytes))

# ➤ 设置参数：圆角半径、边框颜色、边框宽度
radius = theme.card_corner_radius           # 圆角半径
border_color = theme.card_border_color  # 边框颜色，可以换成 theme 的颜色，如 theme.border_color
border_width = theme.card_border_width  # 边框宽度

# 创建带透明背景的新画布
def add_rounded_rectangle_border(image, radius, border_color, border_width):
    # 创建新图像，带透明背景
    new_size = (image.width + 2 * border_width, image.height + 2 * border_width)
    result = Image.new("RGBA", new_size, (0, 0, 0, 0))
    mask = Image.new("L", new_size, 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle(
        [(0, 0), (new_size[0]-1, new_size[1]-1)],
        radius=radius,
        fill=255,
        width=border_width
    )
    draw_result = ImageDraw.Draw(result)
    draw_result.rounded_rectangle(
        [(0, 0), (new_size[0]-1, new_size[1]-1)],
        radius=radius,
        outline=border_color,
        width=border_width
    )

    # 粘贴原图
    result.paste(image, (border_width, border_width), mask=image.convert("RGBA"))

    # 再用 mask 裁剪圆角
    result.putalpha(mask)
    return result

img_with_border = add_rounded_rectangle_border(img, radius, border_color, border_width)

# 保存最终图片
EXPORT_PATH = Path(__file__).parent.parent / "output"
output_path = EXPORT_PATH / f"{code}_chart.png"
img_with_border.save(output_path, format="PNG")

print(f"✅ 已保存带圆角边框的图表至: {output_path}")