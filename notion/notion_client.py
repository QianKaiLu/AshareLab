"""
notion_client_wrapper.py
Notion API client – sync & async, built on httpx (no notion-client dependency).
"""

from __future__ import annotations

import asyncio
from tools.log import get_analyze_logger
from pathlib import Path
from typing import Optional, Union
from notion.emoji import random_emoji

import httpx

from notion.notion_types import NotionPageResult, NotionPageRequest, NotionAPIError, NotionChildPage
from notion.notion_markdown import (
    load_markdown,
    extract_title_from_markdown,
    prepare_markdown_for_notion,
)

logger = get_analyze_logger()

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _build_parent(
    parent_page_id: Optional[str],
    parent_data_source_id: Optional[str],
) -> dict:
    if parent_page_id and parent_data_source_id:
        raise ValueError("Cannot specify both parent_page_id and parent_data_source_id")
    if not parent_page_id and not parent_data_source_id:
        raise ValueError("Must specify either parent_page_id or parent_data_source_id")

    if parent_page_id:
        return {"type": "page_id", "page_id": parent_page_id}
    return {"type": "data_source_id", "data_source_id": parent_data_source_id}


def _build_payload(
    md_content: str,
    parent: dict,
    title: Optional[str],
    properties: Optional[dict],
    is_database: bool,
) -> dict:
    payload: dict = {"parent": parent, "markdown": md_content}
    properties = properties or {}

    if title:
        if "title" not in properties:
            properties["title"] = {"title": [{"text": {"content": title}}]}
    
    payload["properties"] = properties
    payload["icon"] = {"type": "emoji", "emoji": random_emoji()}

    return payload


def _parse_error(resp: httpx.Response) -> NotionAPIError:
    try:
        body = resp.json()
        return NotionAPIError(
            status=resp.status_code,
            code=body.get("code", ""),
            message=body.get("message", resp.text),
        )
    except Exception:
        return NotionAPIError(status=resp.status_code, message=resp.text)


def _parse_success(resp: httpx.Response, title: Optional[str]) -> NotionPageResult:
    data = resp.json()
    return NotionPageResult(
        page_id=data.get("id"),
        url=data.get("url"),
        title=title,
        success=True,
    )

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------

class NotionClient:
    """Synchronous Notion API client."""

    def __init__(self, token: str, *, timeout: float = 30.0):
        self._token = token
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers=_build_headers(token),
            timeout=timeout,
        )

    # -- public API ----------------------------------------------------------

    def create_page_from_markdown(
        self,
        markdown: Union[str, Path],
        parent_page_id: Optional[str] = None,
        parent_data_source_id: Optional[str] = None,
        title: Optional[str] = None,
        properties: Optional[dict] = None,
    ) -> NotionPageResult:
        """Create a Notion page from markdown content.

        Args:
            markdown: Markdown string **or** path to a ``.md`` file.
            parent_page_id: Parent page ID (create sub-page).
            parent_data_source_id: Database data-source ID (create DB entry).
            title: Explicit title. Falls back to first ``# H1`` in markdown.
            properties: Extra Notion properties (required for DB entries).

        Returns:
            ``NotionPageResult`` – check ``.success`` before using other fields.
        """
        try:
            md_content = prepare_markdown_for_notion(load_markdown(markdown))
            if not title:
                title = extract_title_from_markdown(md_content)

            parent = _build_parent(parent_page_id, parent_data_source_id)
            payload = _build_payload(
                md_content, parent, title, properties,
                is_database=bool(parent_data_source_id),
            )

            resp = self._http.post("/pages", json=payload)

            if resp.is_success:
                result = _parse_success(resp, title)
                logger.info("Page created: %s", result.page_id)
                return result

            err = _parse_error(resp)
            logger.error("Notion API error: %s", err)
            return NotionPageResult(error=str(err), success=False)

        except ValueError:
            raise
        except Exception as e:
            logger.error("Failed to create page: %s", e, exc_info=True)
            return NotionPageResult(error=str(e), success=False)

    def batch_create_pages(
        self,
        requests: list[NotionPageRequest],
        max_concurrent: int = 3,  # 保留参数名以对齐异步接口，但同步中实际为串行或简单限流
    ) -> list[NotionPageResult]:
        """Create multiple pages sequentially (synchronous version of async batch).

        Note: Since this is synchronous, it does not run concurrently.
        However, we respect `max_concurrent` by optionally adding delays
        to avoid hitting rate limits (Notion allows ~3 req/s).

        Args:
            requests: Page creation requests.
            max_concurrent: Treated as rate-limit hint; adds delay if >0.
        """
        import time

        results = []
        delay = 1.0 / max_concurrent if max_concurrent > 0 else 0.0

        for req in requests:
            result = self.create_page_from_markdown(
                markdown=req.markdown,
                parent_page_id=req.parent.id if req.parent.type == "page_id" else None,
                parent_data_source_id=req.parent.id if req.parent.type == "data_source_id" else None,
                title=req.title,
                properties=req.properties,
            )
            results.append(result)

            if delay > 0:
                time.sleep(delay)  # 简单节流，避免触发 429

        return results
    
    def get_block_children(
        self,
        block_id: str,
        page_size: int = 100,
    ) -> list[dict]:
        """Get all children blocks of a block (with pagination)."""
        all_results = []
        cursor = None

        while True:
            url = f"/blocks/{block_id}/children"
            params = {"page_size": page_size}
            if cursor:
                params["start_cursor"] = cursor

            try:
                resp = self._http.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                all_results.extend(data.get("results", []))

                if not data.get("has_more", False):
                    break
                cursor = data.get("next_cursor")

            except httpx.HTTPStatusError as e:
                logger.error("Failed to get block children: %s", _parse_error(e.response))
                raise
            except Exception as e:
                logger.error("Failed to get block children: %s", e, exc_info=True)
                raise

        return all_results

    def get_child_pages(
        self,
        page_id: str,
        recursive: bool = False,
    ) -> list[NotionChildPage]:
        """Get all child pages under a page."""
        children = self.get_block_children(page_id)
        child_pages = [b for b in children if b.get("type") == "child_page"]

        results = []
        for page_block in child_pages:
            child_page = NotionChildPage(
                id=page_block["id"],
                title=page_block.get("child_page", {}).get("title", "Untitled"),
                has_children=page_block.get("has_children", False),
                parent_id=page_id,
            )

            if recursive and child_page.has_children:
                child_page.children = self.get_child_pages(
                    child_page.id,
                    recursive=True,
                )

            results.append(child_page)

        return results
    
    def get_all_child_pages_flat(
        self,
        page_id: str,
    ) -> list[NotionChildPage]:
        """Get all child pages recursively in a flat list."""
        all_pages = []

        def _collect(pid: str):
            pages = self.get_child_pages(pid, recursive=False)
            for page in pages:
                all_pages.append(page)
                if page.has_children:
                    _collect(page.id)

        _collect(page_id)
        return all_pages

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------

class AsyncNotionClient:
    """Asynchronous Notion API client."""

    def __init__(self, token: str, *, timeout: float = 30.0):
        self._token = token
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=_build_headers(token),
            timeout=timeout,
        )

    # -- public API ----------------------------------------------------------

    async def create_page_from_markdown(
        self,
        markdown: Union[str, Path],
        parent_page_id: Optional[str] = None,
        parent_data_source_id: Optional[str] = None,
        title: Optional[str] = None,
        properties: Optional[dict] = None,
    ) -> NotionPageResult:
        """Async version of :meth:`NotionClient.create_page_from_markdown`."""
        try:
            md_content = prepare_markdown_for_notion(load_markdown(markdown))
            if not title:
                title = extract_title_from_markdown(md_content)

            parent = _build_parent(parent_page_id, parent_data_source_id)
            payload = _build_payload(
                md_content, parent, title, properties,
                is_database=bool(parent_data_source_id),
            )

            resp = await self._http.post("/pages", json=payload)

            if resp.is_success:
                result = _parse_success(resp, title)
                logger.info("Page created: %s", result.page_id)
                return result

            err = _parse_error(resp)
            logger.error("Notion API error: %s", err)
            return NotionPageResult(error=str(err), success=False)

        except ValueError:
            raise
        except Exception as e:
            logger.error("Failed to create page: %s", e, exc_info=True)
            return NotionPageResult(error=str(e), success=False)

    async def batch_create_pages(
        self,
        requests: list[NotionPageRequest],
        max_concurrent: int = 3,
    ) -> list[NotionPageResult]:
        """Create multiple pages concurrently.

        Args:
            requests: Page creation requests.
            max_concurrent: Concurrency limit (Notion rate-limit ≈ 3 req/s).
        """
        sem = asyncio.Semaphore(max_concurrent)

        async def _worker(req: NotionPageRequest) -> NotionPageResult:
            async with sem:
                return await self.create_page_from_markdown(
                    markdown=req.markdown,
                    parent_page_id=req.parent.id if req.parent.type == "page_id" else None,
                    parent_data_source_id=req.parent.id if req.parent.type == "data_source_id" else None,
                    title=req.title,
                    properties=req.properties,
                )

        return list(await asyncio.gather(*[_worker(r) for r in requests]))

    # -- query pages ---------------------------------------------------------

    async def get_block_children(
        self,
        block_id: str,
        page_size: int = 100,
    ) -> list[dict]:
        """Get all children blocks of a block (with pagination).

        Args:
            block_id: Block/page ID.
            page_size: Results per page (max 100).

        Returns:
            List of block objects.
        """
        all_results = []
        cursor = None

        while True:
            url = f"{BASE_URL}/blocks/{block_id}/children"
            params = {"page_size": page_size}
            if cursor:
                params["start_cursor"] = cursor

            try:
                resp = await self._http.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                all_results.extend(data.get("results", []))

                if not data.get("has_more", False):
                    break
                cursor = data.get("next_cursor")

            except httpx.HTTPStatusError as e:
                logger.error("Failed to get block children: %s", _parse_error(e.response))
                raise
            except Exception as e:
                logger.error("Failed to get block children: %s", e, exc_info=True)
                raise

        return all_results

    async def get_child_pages(
        self,
        page_id: str,
        recursive: bool = False,
    ) -> list[NotionChildPage]:
        """Get all child pages under a page.

        Args:
            page_id: Parent page ID.
            recursive: If True, recursively fetch nested child pages.

        Returns:
            List of NotionChildPage objects.
        """
        children = await self.get_block_children(page_id)
        child_pages = [b for b in children if b.get("type") == "child_page"]

        results = []
        for page_block in child_pages:
            child_page = NotionChildPage(
                id=page_block["id"],
                title=page_block.get("child_page", {}).get("title", "Untitled"),
                has_children=page_block.get("has_children", False),
                parent_id=page_id,
            )

            if recursive and child_page.has_children:
                child_page.children = await self.get_child_pages(
                    child_page.id,
                    recursive=True,
                )

            results.append(child_page)

        return results

    async def get_all_child_pages_flat(
        self,
        page_id: str,
    ) -> list[NotionChildPage]:
        """Get all child pages recursively in a flat list.

        Args:
            page_id: Parent page ID.

        Returns:
            Flat list of all nested child pages.
        """
        all_pages = []

        async def _collect(pid: str):
            pages = await self.get_child_pages(pid, recursive=False)
            for page in pages:
                all_pages.append(page)
                if page.has_children:
                    await _collect(page.id)

        await _collect(page_id)
        return all_pages

    # -- lifecycle -----------------------------------------------------------

    async def close(self):
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()