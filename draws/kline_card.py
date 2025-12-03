import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datas.query_stock import query_latest_bars
from pathlib import Path
from indicators.kdj import add_kdj_to_dataframe
from indicators.macd import add_macd_to_dataframe
from indicators.bbi import add_bbi_to_dataframe
from indicators.zxdkx import add_zxdkx_to_dataframe
import plotly.io as pio
from PIL import Image, ImageOps, ImageDraw
import io

# 先保存图表到内存中的 PNG
img_bytes = fig.to_image(format="png", width=600, height=500, scale=2)  # scale 提高清晰度

# 用 PIL 打开图像并处理
img = Image.open(io.BytesIO(img_bytes))

# ➤ 设置参数：圆角半径、边框颜色、边框宽度
radius = 20           # 圆角半径
border_color = "#4a90e2"  # 边框颜色，可以换成 theme 的颜色，如 theme.border_color
border_width = 4      # 边框宽度

# 创建带透明背景的新画布
def add_rounded_rectangle_border(image, radius, border_color, border_width):
    # 创建新图像，带透明背景
    new_size = (image.width + 2 * border_width, image.height + 2 * border_width)
    result = Image.new("RGBA", new_size, (0, 0, 0, 0))
    mask = Image.new("L", new_size, 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle(
        [(0, 0), new_size],
        radius=radius,
        fill=255,
        width=border_width
    )
    draw_result = ImageDraw.Draw(result)
    draw_result.rounded_rectangle(
        [(0, 0), new_size],
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
output_path = Path(f"{code}_chart.png")
img_with_border.save(output_path, format="PNG")

print(f"✅ 已保存带圆角边框的图表至: {output_path}")
