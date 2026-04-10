"""
notion_markdown.py
Markdown processing utilities for Notion API integration.
"""

import re
from pathlib import Path
from typing import Union, Optional


def load_markdown(source: Union[str, Path]) -> str:
    """
    Load markdown from file path or return string directly.

    Args:
        source: Either a markdown string or a file path.

    Returns:
        Markdown content as string.

    Raises:
        FileNotFoundError: If file path provided but doesn't exist.
    """
    # Check if it's a file path
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.exists() and path.is_file():
            return path.read_text(encoding='utf-8')

    # Otherwise treat as markdown string
    return str(source)


def extract_title_from_markdown(markdown: str) -> Optional[str]:
    """
    Extract title from first H1 heading in markdown.

    Args:
        markdown: Markdown content string.

    Returns:
        Title string if H1 found, None otherwise.
    """
    # Match first H1 heading (# Title)
    match = re.search(r'^#\s+(.+)$', markdown, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def prepare_markdown_for_notion(markdown: str) -> str:
    """
    Preprocess markdown for Notion API.

    Currently just returns the markdown as-is since Notion handles
    standard markdown well. This function exists for future preprocessing
    needs (e.g., handling special characters, custom syntax, etc.).

    Args:
        markdown: Raw markdown content.

    Returns:
        Processed markdown ready for Notion API.
    """
    # Notion API handles standard markdown well
    # Just ensure consistent line endings
    return markdown.replace('\r\n', '\n')
