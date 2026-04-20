"""
notion_utils.py
Shared utilities for Notion API clients.
"""

from typing import Optional
import httpx

from notion.emoji import random_emoji
from notion.notion_types import NotionAPIError, NotionPageResult

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"


def build_headers(token: str) -> dict[str, str]:
    """Build HTTP headers for Notion API requests."""
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def build_parent(
    parent_page_id: Optional[str],
    parent_data_source_id: Optional[str],
) -> dict:
    """Build parent object for page creation."""
    if parent_page_id and parent_data_source_id:
        raise ValueError("Cannot specify both parent_page_id and parent_data_source_id")
    if not parent_page_id and not parent_data_source_id:
        raise ValueError("Must specify either parent_page_id or parent_data_source_id")

    if parent_page_id:
        return {"type": "page_id", "page_id": parent_page_id}
    return {"type": "data_source_id", "data_source_id": parent_data_source_id}


def build_payload(
    md_content: str,
    parent: dict,
    title: Optional[str],
    properties: Optional[dict],
    is_database: bool,
) -> dict:
    """Build request payload for page creation."""
    payload: dict = {"parent": parent, "markdown": md_content}
    properties = properties or {}

    if title:
        if "title" not in properties:
            properties["title"] = {"title": [{"text": {"content": title}}]}

    payload["properties"] = properties
    payload["icon"] = {"type": "emoji", "emoji": random_emoji()}

    return payload


def parse_error(resp: httpx.Response) -> NotionAPIError:
    """Parse error response from Notion API."""
    try:
        body = resp.json()
        return NotionAPIError(
            status=resp.status_code,
            code=body.get("code", ""),
            message=body.get("message", resp.text),
        )
    except Exception:
        return NotionAPIError(status=resp.status_code, message=resp.text)


def parse_success(resp: httpx.Response, title: Optional[str]) -> NotionPageResult:
    """Parse successful response from Notion API."""
    data = resp.json()
    return NotionPageResult(
        page_id=data.get("id"),
        url=data.get("url"),
        title=title,
        success=True,
    )
