"""
notion_client_wrapper.py
Notion API client – sync & async, built on httpx (no notion-client dependency).
"""

from __future__ import annotations

import asyncio
from tools.log import get_analyze_logger
from pathlib import Path
from typing import Optional, Union
from emoji import random_emoji

import httpx

from notion_types import NotionPageResult, NotionPageRequest, NotionAPIError
from notion_markdown import (
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

    # -- lifecycle -----------------------------------------------------------

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

    # -- lifecycle -----------------------------------------------------------

    async def close(self):
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()