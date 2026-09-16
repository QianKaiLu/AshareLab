import markdown
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
from urllib.parse import urlparse, unquote

logger = get_analyze_logger()

template = Template("""
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    /* 深暖背景与文字 */
    --bg: #1a140f;           /* 主背景：深棕黑，像咖啡底色 */
    --text: #e6d7c3;         /* 主文本：米白色/暖白 */
    --muted: #b8a594;        /* 次要文字：灰褐色，柔和不刺眼 */
    --border: #3c322b;       /* 边框：中深棕 */

    /* 强调色 —— 暖调主次色 */
    --primary: #d19a66;      /* 主色：琥珀橙/暖铜色（原 fuchsia 替代）*/
    --success: #8b9b66;      /* 成功/正面：橄榄绿，偏暖 */
    --danger: #cc775d;       /* 警告/负面：陶土红，温暖但警觉 */

    /* 组件背景色 */
    --blockquote-bg: #2a221a; /* 引用块背景：稍亮的深棕 */
    --table-header: #2d241c;  /* 表头背景：略亮于主背景 */
    --code-bg: #241d17;       /* 代码块背景：深可可色 */

    /* 字体 */
    --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  }

  body {
    font-family: var(--font-sans);
    max-width: 680px;
    margin: 32px auto;
    padding: 20px;
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    box-sizing: border-box;
    font-size: 16px;
  }

  /* 标题 */
  h1, h2, h3 {
    color: #ead7c0;
    margin-top: 1.6em;
    margin-bottom: 0.6em;
    font-weight: 600;
    letter-spacing: -0.02em;
  }
  h1 { font-size: 1.8rem; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
  h2 { font-size: 1.45rem; }
  h3 { font-size: 1.25rem; }
  /* 章节标题前一个小琥珀块：取代「一、二、三」这类列序——编号是呆板的，
     而一个色块既能让各节视觉上分得开，又不必给章节排座次 */
  h2::before {
    content: "";
    display: inline-block;
    width: 4px;
    height: 0.82em;
    background: var(--primary);
    margin-right: 10px;
    vertical-align: -0.04em;
    border-radius: 2px;
  }

  /* 引用块 —— 左边橙棕条+暖暗背景 */
  blockquote {
    border-left: 5px solid var(--primary);
    background-color: var(--blockquote-bg);
    padding: 18px 22px;
    margin: 24px 0;
    border-radius: 0 8px 8px 0;
    color: var(--muted);
    font-style: italic;
    box-shadow: inset 2px 0 0 rgba(255,255,255,0.05);
  }

  /* 表格样式：温润深棕风格 */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.8em 0;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  }
  th {
    background-color: var(--table-header);
    color: #d6c7b5;
    padding: 13px 16px;
    text-align: left;
    font-weight: 600;
    font-size: 0.95em;
    border-bottom: 2px solid var(--primary);
  }
  td {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    transition: background 0.2s;
  }
  tr:nth-child(even) {
    background-color: #221a13;
  }
  tr:hover {
    background-color: #2b2016;
  }

  /* 代码块 */
  pre {
    background: var(--code-bg);
    border-radius: 9px;
    padding: 18px 20px;
    overflow-x: auto;
    margin: 1.8em 0;
    border: 1px solid var(--border);
    box-shadow: inset 0 1px 3px rgba(0,0,0,0.3);
  }
  code {
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 0.9em;
    color: var(--primary);
    background: var(--blockquote-bg);
    padding: 0.2em 0.4em;
    border-radius: 4px;
  }
  pre code {
    background: none;
    color: #dcd0ba;
    padding: 0;
    font-size: 1em;
  }

  /* 链接 & 状态类 */
  a {
    color: var(--primary);
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
    color: #e6af7a;
  }
  /* 语义上的「好 / 坏」——个股分析报告在用 */
  .positive {
    color: var(--success);
    font-weight: 600;
  }
  .negative {
    color: var(--danger);
    font-weight: 600;
  }
  /* 涨跌方向：A 股惯例红涨绿跌，与上面两个类的语义**不同**。
     市场日报图版用这两个；不要拿 .positive/.negative 当涨跌使唤——
     它们表达的是「利好/利空」，与价格方向不是一回事。 */
  .up {
    color: #d05a4a;
    font-weight: 600;
  }
  .down {
    color: #6f9b6a;
    font-weight: 600;
  }
  /* 旁注：术语解释这类「辅助信息」用。与 blockquote（章节小结）刻意区分——
     引用块是琥珀色粗边 + 大字，表示「这是本章结论」；旁注是灰色细边 + 小字 +
     弱化色，表示「可以跳过，需要时回查」。层级不同，不能长一个样。
     另：两个相邻的 `>` 块会被 markdown 合并成同一个 blockquote，所以旁注不能用
     引用块写，否则会跟章节小结粘在一起。 */
  .aside {
    border-left: 3px solid var(--border);
    padding: 2px 0 2px 14px;
    margin: 22px 0;
    color: var(--muted);
    font-size: 0.92em;
    line-height: 1.7;
  }
  .aside b { color: #d6c7b5; }
</style>
</head>
<body>{{ content }}</body>
</html>
""")

def save_md_to_file_name(md_content: str, file_name: str) -> Optional[Path]:
    """save markdown content to a file"""
    file_path = EXPORT_PATH / f"{file_name}.md"
    save_md_to_file(md_content, file_path)
    return file_path

def save_md_to_file(md_content: str, file_path: Path):
    """save markdown content to a file"""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info(f"✅ Markdown saved to: {file_path}")
    except Exception as e:
        logger.error(f"❌ Failed to save markdown to {file_path}: {e}")
        
def render_markdown_to_image_file_name(md_content: str, file_name: str, open_folder_after: bool = False)  -> Optional[Path]:
    """Render markdown content to an image file with given name"""
    image_path = EXPORT_PATH / f"{file_name}.png"
    render_markdown_to_image(md_content, image_path, open_folder_after)
    return image_path

def preprocess_markdown(md: str) -> str:
    """Preprocess markdown content to ensure proper rendering of certain elements."""
    patterns = [
        r'(\*\*.*?\*\*)(\s*\n\s*[-*])',
        r'(###?\s+.*?)(\s*\n\s*[-*])',
    ]
    for pattern in patterns:
        md = re.sub(pattern, r'\1\n\n\2', md)

    return md


def convert_local_images_to_base64(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for img in soup.find_all("img"):
        src = img.get("src", "")

        local_path = None
        if src.startswith("file://"):
            raw_path = urlparse(src).path
            local_path = unquote(raw_path)
        elif os.path.exists(src):
            local_path = src
        else:
            continue

        if local_path and os.path.exists(local_path):
            try:
                with open(local_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                    img["src"] = f"data:image/png;base64,{b64}"
            except Exception as e:
                print(f"⚠️ Failed to load image {src}: {e}")
        else:
            print(f"⚠️ Image file not found: {local_path or src}")

    return str(soup)

def render_markdown_to_image(md_content: str, image_path: Path, open_folder_after: bool = False):
    """Render markdown content to an image using Playwright"""
    try:
        # Convert markdown to HTML
        md_content = preprocess_markdown(md_content)
        html_body = markdown.markdown(
            md_content,
            extensions=[
                'tables',
                'fenced_code',
                'codehilite',
                'attr_list',
                'nl2br',
                'md_in_html',
                'extra',
            ],
            extension_configs={
                'codehilite': {'css_class': 'highlight'},
            }
        )
        
        # Create full HTML with styling
        html_body = convert_local_images_to_base64(html_body)
        html = template.render(content=html_body)
        
        # Use Playwright to render HTML to image
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": 600, "height": 1200},
                device_scale_factor=2
            )
            page.set_content(html)
            page.screenshot(path=str(image_path), full_page=True)
            browser.close()
        
        logger.info(f"✅ Image rendered and saved to: {image_path}")
        if open_folder_after:
            webbrowser.open(image_path.resolve().as_uri())
    except Exception as e:
        logger.error(f"❌ Failed to render markdown to image {image_path}: {e}")

if __name__ == "__main__":
    markdown_path = EXPORT_PATH / "比亚迪(002594)_分析报告.md"
    image_path = EXPORT_PATH / "比亚迪(002594)_分析报告.png"
    if markdown_path.exists():
        with open(markdown_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        render_markdown_to_image(md_content, image_path, open_folder_after=True)