"""
test_notion_client.py

Usage:
    1. Set NOTION_TOKEN in .env
    2. Set TEST_PAGE_ID below
    3. python3 -m notion.test_notion_client       (from project root)
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv

# Add project root so ``from notion import ...`` works when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notion import NotionClient, AsyncNotionClient, NotionPageRequest, NotionParent

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")

# ⬇️ Replace with a real parent page ID to run live tests
TEST_PAGE_ID = "YOUR_PAGE_ID_HERE"

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _skip() -> bool:
    if not NOTION_TOKEN:
        print("  skipped (no NOTION_TOKEN)")
        return True
    if TEST_PAGE_ID == "YOUR_PAGE_ID_HERE":
        print("  skipped (set TEST_PAGE_ID)")
        return True
    return False


def test_sync_basic():
    print("\n--- sync: basic markdown ---")
    if _skip():
        return

    with NotionClient(NOTION_TOKEN) as client:
        result = client.create_page_from_markdown(
            markdown="# Sync Test\n\nHello from sync client.\n\n- a\n- b\n- c",
            parent_page_id=TEST_PAGE_ID,
        )
    print(f"  {'OK' if result.success else 'FAIL'}  {result.page_id or result.error}")


def test_sync_explicit_title():
    print("\n--- sync: explicit title ---")
    if _skip():
        return

    with NotionClient(NOTION_TOKEN) as client:
        result = client.create_page_from_markdown(
            markdown="No H1 heading here.\n\nJust some content.",
            parent_page_id=TEST_PAGE_ID,
            title="Explicit Title",
        )
    print(f"  {'OK' if result.success else 'FAIL'}  {result.page_id or result.error}")


def test_sync_from_file():
    print("\n--- sync: from file ---")
    if _skip():
        return

    tmp = Path(__file__).parent / "_test_tmp.md"
    tmp.write_text("# File Test\n\nLoaded from disk.", encoding="utf-8")
    try:
        with NotionClient(NOTION_TOKEN) as client:
            result = client.create_page_from_markdown(
                markdown=tmp, parent_page_id=TEST_PAGE_ID,
            )
        print(f"  {'OK' if result.success else 'FAIL'}  {result.page_id or result.error}")
    finally:
        tmp.unlink(missing_ok=True)


async def test_async_basic():
    print("\n--- async: basic ---")
    if _skip():
        return

    async with AsyncNotionClient(NOTION_TOKEN) as client:
        result = await client.create_page_from_markdown(
            markdown="# Async Test\n\nHello from async client.",
            parent_page_id=TEST_PAGE_ID,
        )
    print(f"  {'OK' if result.success else 'FAIL'}  {result.page_id or result.error}")


async def test_async_batch():
    print("\n--- async: batch (3 pages) ---")
    if _skip():
        return

    async with AsyncNotionClient(NOTION_TOKEN) as client:
        reqs = [
            NotionPageRequest(
                markdown=f"# Batch {i+1}\n\nPage {i+1} of 3.",
                parent=NotionParent(type="page_id", id=TEST_PAGE_ID),
            )
            for i in range(3)
        ]
        results = await client.batch_create_pages(reqs)

    ok = sum(r.success for r in results)
    print(f"  {ok}/{len(results)} created")


def test_error_handling():
    print("\n--- error handling ---")
    if not NOTION_TOKEN:
        print("  skipped (no NOTION_TOKEN)")
        return

    client = NotionClient(NOTION_TOKEN)

    # no parent → ValueError
    try:
        client.create_page_from_markdown(markdown="# x")
        print("  no-parent check: FAIL (no exception)")
    except ValueError:
        print("  no-parent check: OK")

    # both parents → ValueError
    try:
        client.create_page_from_markdown(
            markdown="# x", parent_page_id="a", parent_data_source_id="b",
        )
        print("  both-parents check: FAIL (no exception)")
    except ValueError:
        print("  both-parents check: OK")

    # invalid page id → API error in result
    result = client.create_page_from_markdown(
        markdown="# x", parent_page_id="0000000000000000",
    )
    print(f"  invalid-id check: {'OK' if not result.success else 'FAIL'}")

    client.close()


# ---------------------------------------------------------------------------

def main():
    print("=" * 50)
    print("Notion Client Tests")
    print("=" * 50)

    test_sync_basic()
    test_sync_explicit_title()
    test_sync_from_file()
    asyncio.run(test_async_basic())
    asyncio.run(test_async_batch())
    test_error_handling()

    print("\n" + "=" * 50)
    print("Done")


if __name__ == "__main__":
    main()