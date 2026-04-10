"""
notion_client_wrapper.py
Core Notion API client wrapper with sync and async interfaces.
"""

import asyncio
from pathlib import Path
from typing import Optional, Union
from notion_client import Client, AsyncClient
from notion_client.errors import APIResponseError

import sys
sys.path.append(str(Path(__file__).parent.parent))
from tools.log import get_fetch_logger
from notion.notion_types import NotionPageResult, NotionPageRequest
from notion.notion_markdown import (
    load_markdown,
    extract_title_from_markdown,
    prepare_markdown_for_notion
)


NOTION_VERSION = "2026-03-11"


class NotionClient:
    """Synchronous Notion API client wrapper."""

    def __init__(self, token: str):
        """
        Initialize Notion client.

        Args:
            token: Notion integration token (format: ntn_...).
        """
        self._client = Client(auth=token, notion_version=NOTION_VERSION)
        self._logger = get_fetch_logger()

    def create_page_from_markdown(
        self,
        markdown: Union[str, Path],
        parent_page_id: Optional[str] = None,
        parent_data_source_id: Optional[str] = None,
        title: Optional[str] = None,
        properties: Optional[dict] = None
    ) -> NotionPageResult:
        """
        Create a Notion page from markdown content.

        Args:
            markdown: Markdown content (string) or file path.
            parent_page_id: Parent page ID (for creating sub-pages).
            parent_data_source_id: Database data source ID (for database entries).
            title: Page title (optional, extracted from H1 if not provided).
            properties: Properties dict for database entries (optional).

        Returns:
            NotionPageResult with success status and page info or error.
        """
        try:
            # Load markdown content
            md_content = load_markdown(markdown)
            md_content = prepare_markdown_for_notion(md_content)

            # Extract title if not provided
            if not title:
                title = extract_title_from_markdown(md_content)

            # Build parent object
            parent = self._build_parent(parent_page_id, parent_data_source_id)

            # Build request payload
            payload = {
                "parent": parent,
                "markdown": md_content
            }

            # Add properties for database entries
            if properties:
                payload["properties"] = properties
            elif title and parent_data_source_id:
                # For database entries, ensure title property exists
                payload["properties"] = {
                    "title": {
                        "title": [{"text": {"content": title}}]
                    }
                }

            # Create page via API
            response = self._client.pages.create(**payload)

            page_id = response.get("id")
            page_url = response.get("url")

            self._logger.info(f"✅ Notion page created: {page_id}")

            return NotionPageResult(
                page_id=page_id,
                url=page_url,
                title=title,
                success=True
            )

        except APIResponseError as e:
            error_msg = f"API error: {e.code} - {e.message}"
            self._logger.error(f"❌ Notion API error: {error_msg}")
            return NotionPageResult(error=error_msg, success=False)
        except Exception as e:
            self._logger.error(f"❌ Failed to create Notion page: {e}", exc_info=True)
            return NotionPageResult(error=str(e), success=False)

    def _build_parent(
        self,
        parent_page_id: Optional[str],
        parent_data_source_id: Optional[str]
    ) -> dict:
        """Build parent object for API request."""
        if parent_page_id and parent_data_source_id:
            raise ValueError("Cannot specify both parent_page_id and parent_data_source_id")

        if not parent_page_id and not parent_data_source_id:
            raise ValueError("Must specify either parent_page_id or parent_data_source_id")

        if parent_page_id:
            return {"type": "page_id", "page_id": parent_page_id}
        else:
            return {"type": "data_source_id", "data_source_id": parent_data_source_id}


class AsyncNotionClient:
    """Asynchronous Notion API client wrapper."""

    def __init__(self, token: str):
        """
        Initialize async Notion client.

        Args:
            token: Notion integration token (format: ntn_...).
        """
        self._client = AsyncClient(auth=token, notion_version=NOTION_VERSION)
        self._logger = get_fetch_logger()

    async def create_page_from_markdown(
        self,
        markdown: Union[str, Path],
        parent_page_id: Optional[str] = None,
        parent_data_source_id: Optional[str] = None,
        title: Optional[str] = None,
        properties: Optional[dict] = None
    ) -> NotionPageResult:
        """
        Create a Notion page from markdown content (async).

        Args:
            markdown: Markdown content (string) or file path.
            parent_page_id: Parent page ID (for creating sub-pages).
            parent_data_source_id: Database data source ID (for database entries).
            title: Page title (optional, extracted from H1 if not provided).
            properties: Properties dict for database entries (optional).

        Returns:
            NotionPageResult with success status and page info or error.
        """
        try:
            # Load markdown content
            md_content = load_markdown(markdown)
            md_content = prepare_markdown_for_notion(md_content)

            # Extract title if not provided
            if not title:
                title = extract_title_from_markdown(md_content)

            # Build parent object
            parent = self._build_parent(parent_page_id, parent_data_source_id)

            # Build request payload
            payload = {
                "parent": parent,
                "markdown": md_content
            }

            # Add properties for database entries
            if properties:
                payload["properties"] = properties
            elif title and parent_data_source_id:
                # For database entries, ensure title property exists
                payload["properties"] = {
                    "title": {
                        "title": [{"text": {"content": title}}]
                    }
                }

            # Create page via API
            response = await self._client.pages.create(**payload)

            page_id = response.get("id")
            page_url = response.get("url")

            self._logger.info(f"✅ Notion page created: {page_id}")

            return NotionPageResult(
                page_id=page_id,
                url=page_url,
                title=title,
                success=True
            )

        except APIResponseError as e:
            error_msg = f"API error: {e.code} - {e.message}"
            self._logger.error(f"❌ Notion API error: {error_msg}")
            return NotionPageResult(error=error_msg, success=False)
        except Exception as e:
            self._logger.error(f"❌ Failed to create Notion page: {e}", exc_info=True)
            return NotionPageResult(error=str(e), success=False)

    async def batch_create_pages(
        self,
        requests: list[NotionPageRequest],
        max_concurrent: int = 5
    ) -> list[NotionPageResult]:
        """
        Create multiple pages concurrently with rate limiting.

        Args:
            requests: List of NotionPageRequest objects.
            max_concurrent: Maximum concurrent requests (default: 5).

        Returns:
            List of NotionPageResult objects in same order as requests.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _worker(req: NotionPageRequest) -> NotionPageResult:
            async with semaphore:
                return await self.create_page_from_markdown(
                    markdown=req.markdown,
                    parent_page_id=req.parent.id if req.parent.type == "page_id" else None,
                    parent_data_source_id=req.parent.id if req.parent.type == "data_source_id" else None,
                    title=req.title,
                    properties=req.properties
                )

        results = await asyncio.gather(*[_worker(r) for r in requests])
        return list(results)

    def _build_parent(
        self,
        parent_page_id: Optional[str],
        parent_data_source_id: Optional[str]
    ) -> dict:
        """Build parent object for API request."""
        if parent_page_id and parent_data_source_id:
            raise ValueError("Cannot specify both parent_page_id and parent_data_source_id")

        if not parent_page_id and not parent_data_source_id:
            raise ValueError("Must specify either parent_page_id or parent_data_source_id")

        if parent_page_id:
            return {"type": "page_id", "page_id": parent_page_id}
        else:
            return {"type": "data_source_id", "data_source_id": parent_data_source_id}
