"""
notion_client.py
Notion API client – sync & async, built on httpx.

This module re-exports NotionClient and AsyncNotionClient for backward compatibility.
"""

from notion.notion_sync_client import NotionClient
from notion.notion_async_client import AsyncNotionClient

__all__ = ["NotionClient", "AsyncNotionClient"]
