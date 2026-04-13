"""
example_usage.py
Quick examples for the Notion client.
"""

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")

# --- adjust these before running ---
PAGE_ID = "YOUR_PARENT_PAGE_ID"
DB_DATA_SOURCE_ID = "YOUR_DATABASE_DATA_SOURCE_ID"


def example_sync():
    """Create a sub-page synchronously."""
    from notion import NotionClient

    with NotionClient(NOTION_TOKEN) as client:
        result = client.create_page_from_markdown(
            markdown="# Weekly Report\n\n## Highlights\n- Feature A shipped\n- Bug B fixed",
            parent_page_id=PAGE_ID,
        )
    print(result)


def example_sync_file():
    """Create a page from a local .md file."""
    from notion import NotionClient

    with NotionClient(NOTION_TOKEN) as client:
        result = client.create_page_from_markdown(
            markdown="path/to/report.md",
            parent_page_id=PAGE_ID,
            title="Override Title",
        )
    print(result)


def example_database_entry():
    """Create a database entry with properties."""
    from notion import NotionClient

    with NotionClient(NOTION_TOKEN) as client:
        result = client.create_page_from_markdown(
            markdown="## Details\n\nSome content for the DB entry.",
            parent_data_source_id=DB_DATA_SOURCE_ID,
            properties={
                "Name": {"title": [{"text": {"content": "New Task"}}]},
            },
        )
    print(result)


async def example_async_batch():
    """Create several pages concurrently."""
    from notion import AsyncNotionClient, NotionPageRequest, NotionParent

    async with AsyncNotionClient(NOTION_TOKEN) as client:
        reqs = [
            NotionPageRequest(
                markdown=f"# Report {i}\n\nContent {i}.",
                parent=NotionParent(type="page_id", id=PAGE_ID),
            )
            for i in range(3)
        ]
        results = await client.batch_create_pages(reqs, max_concurrent=3)
    for r in results:
        print(r)


if __name__ == "__main__":
    # Uncomment one:
    # example_sync()
    # example_sync_file()
    # example_database_entry()
    # asyncio.run(example_async_batch())
    print("Edit this file, set IDs, and uncomment an example to run.")