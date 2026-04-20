"""
notion_async_client.py
Asynchronous Notion API client.
"""

from pathlib import Path
from typing import Optional, Union
import asyncio

import httpx
from tools.log import get_analyze_logger

from notion.notion_types import NotionPageResult, NotionPageRequest, NotionChildPage
from notion.notion_markdown import (
    load_markdown,
    extract_title_from_markdown,
    prepare_markdown_for_notion,
)
from notion.notion_utils import (
    BASE_URL,
    build_headers,
    build_parent,
    build_payload,
    parse_error,
    parse_success,
)

logger = get_analyze_logger()


class AsyncNotionClient:
    """Asynchronous Notion API client."""

    def __init__(self, token: str, *, timeout: float = 30.0):
        self._token = token
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=build_headers(token),
            timeout=timeout,
        )

    async def create_page_from_markdown(
        self,
        markdown: Union[str, Path],
        parent_page_id: Optional[str] = None,
        parent_data_source_id: Optional[str] = None,
        title: Optional[str] = None,
        properties: Optional[dict] = None,
    ) -> NotionPageResult:
        """Create a Notion page from markdown content (async).

        Args:
            markdown: Markdown string or path to a .md file.
            parent_page_id: Parent page ID (create sub-page).
            parent_data_source_id: Database data-source ID (create DB entry).
            title: Explicit title. Falls back to first # H1 in markdown.
            properties: Extra Notion properties (required for DB entries).

        Returns:
            NotionPageResult – check .success before using other fields.
        """
        try:
            md_content = prepare_markdown_for_notion(load_markdown(markdown))
            if not title:
                title = extract_title_from_markdown(md_content)

            parent = build_parent(parent_page_id, parent_data_source_id)
            payload = build_payload(
                md_content, parent, title, properties,
                is_database=bool(parent_data_source_id),
            )

            resp = await self._http.post("/pages", json=payload)

            if resp.is_success:
                result = parse_success(resp, title)
                logger.info("Page created: %s", result.page_id)
                return result

            err = parse_error(resp)
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
                logger.error("Failed to get block children: %s", parse_error(e.response))
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

    async def close(self):
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()




