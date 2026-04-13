"""
notion_markdown.py
Markdown loading and preprocessing utilities.
"""

import re
from pathlib import Path
from typing import Union, Optional

def load_markdown(source: Union[str, Path]) -> str:
    # 如果是 Path 对象，直接按路径处理
    if isinstance(source, Path):
        if source.is_file():
            return source.read_text(encoding="utf-8")
        else:
            raise FileNotFoundError(f"Path is not a file: {source}")
    
    # 如果是字符串：仅当它“看起来像合理路径”时才尝试读文件
    if len(source) > 255:  # 避免超长字符串触发系统错误
        return source
    
    path = Path(source)
    try:
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8")
    except (OSError, ValueError):  # 捕获路径非法或过长等异常
        pass  # 当作普通字符串处理
    
    return source


def extract_title_from_markdown(markdown: str) -> Optional[str]:
    """Return the first ``# H1`` heading text, or *None*."""
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def prepare_markdown_for_notion(markdown: str) -> str:
    """Normalise markdown before sending to the Notion API."""
    return markdown.replace("\r\n", "\n")