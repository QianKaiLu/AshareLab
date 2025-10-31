import markdown
from jinja2 import Template
from playwright.sync_api import sync_playwright
import os
from pathlib import Path
from tools.log import get_analyze_logger
import webbrowser
from tools.export import EXPORT_PATH
from typing import Optional

logger = get_analyze_logger()

template = Template("""
<html><head>
<meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
  body { 
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    max-width: 580px; 
    margin: 40px auto; 
    padding: 36px;
    background: #f8f9fa;          /* 浅灰背景 */
    color: #2d3748;               /* 深灰文字（非纯黑） */
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
    line-height: 1.65;
  }
  
  /* 标题样式 */
  h1, h2, h3 {
    color: #1a202c;               /* 深炭灰 */
    font-weight: 600;
    margin-top: 1.4em;
  }
  
  /* 链接颜色 */
  a {
    color: #2b6cb0;               /* 专业蓝 */
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
  }
  
  img {
    max-width: 100%;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
    margin: 1.2em 0;
    box-sizing: border-box;
  }
  
  /* 表格优化 */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.2em 0;
    max-width: 100%;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  }
  th {
    background-color: #edf2f7;    /* 浅灰蓝表头 */
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
    color: #4a5568;
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid #e2e8f0;
  }
  tr:hover td {
    background-color: #f8fafc;
  }
  
  /* 关键数据强调 */
  .positive { color: #2f855a; }   /* 稳重绿色（上涨） */
  .negative { color: #e53e3e; }   /* 深红色（下跌） */
  .highlight { 
    background-color: #ebf8ff; 
    padding: 2px 6px;
    border-radius: 4px;
  }
</style></head><body>{{ content }}</body></html>
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

def render_markdown_to_image(md_content: str, image_path: Path, open_folder_after: bool = False):
    """Render markdown content to an image using Playwright"""
    try:
        # Convert markdown to HTML
        html_body = markdown.markdown(md_content)
        
        # Create full HTML with styling
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
