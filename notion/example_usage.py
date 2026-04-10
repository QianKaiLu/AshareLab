"""
example_usage.py
Simple examples demonstrating how to use the Notion client.
"""

import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from notion import NotionClient, AsyncNotionClient, NotionPageRequest, NotionParent

# Load environment
load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN")


def example_1_basic_sync():
    """Example 1: Create a simple page synchronously."""
    client = NotionClient(NOTION_TOKEN)

    markdown = """# My First Notion Page

This is a simple example of creating a Notion page from markdown.

## Features
- Easy to use
- Supports standard markdown
- Automatic title extraction
"""

    result = client.create_page_from_markdown(
        markdown=markdown,
        parent_page_id="YOUR_PARENT_PAGE_ID"
    )

    if result.success:
        print(f"✅ Page created: {result.url}")
    else:
        print(f"❌ Error: {result.error}")


def example_2_from_file():
    """Example 2: Create page from markdown file."""
    client = NotionClient(NOTION_TOKEN)

    # Load from file
    result = client.create_page_from_markdown(
        markdown="path/to/your/report.md",
        parent_page_id="YOUR_PARENT_PAGE_ID",
        title="Stock Analysis Report"  # Optional: override title
    )

    if result.success:
        print(f"✅ Page created: {result.url}")


def example_3_database_entry():
    """Example 3: Create database entry with properties."""
    client = NotionClient(NOTION_TOKEN)

    markdown = """## Task Details

Implement the new feature for stock analysis.

### Requirements
- Add technical indicators
- Create visualization
- Write tests
"""

    result = client.create_page_from_markdown(
        markdown=markdown,
        parent_data_source_id="YOUR_DATABASE_DATA_SOURCE_ID",
        properties={
            "任务名称": {
                "title": [{"text": {"content": "Stock Analysis Feature"}}]
            },
            "优先级": {
                "select": {"name": "高"}
            },
            "状态": {
                "status": {"name": "进行中"}
            }
        }
    )

    if result.success:
        print(f"✅ Database entry created: {result.url}")


async def example_4_async_batch():
    """Example 4: Create multiple pages concurrently."""
    client = AsyncNotionClient(NOTION_TOKEN)

    # Prepare multiple page requests
    reports = [
        ("Stock A Analysis", "# Stock A\n\nBullish trend..."),
        ("Stock B Analysis", "# Stock B\n\nBearish trend..."),
        ("Stock C Analysis", "# Stock C\n\nSideways movement..."),
    ]

    requests = [
        NotionPageRequest(
            markdown=content,
            parent=NotionParent(type="page_id", id="YOUR_PARENT_PAGE_ID"),
            title=title
        )
        for title, content in reports
    ]

    # Create all pages concurrently
    results = await client.batch_create_pages(requests, max_concurrent=3)

    success_count = sum(1 for r in results if r.success)
    print(f"✅ Created {success_count}/{len(results)} pages")


async def example_5_async_single():
    """Example 5: Single async page creation."""
    client = AsyncNotionClient(NOTION_TOKEN)

    result = await client.create_page_from_markdown(
        markdown="# Async Page\n\nCreated with async client.",
        parent_page_id="YOUR_PARENT_PAGE_ID"
    )

    if result.success:
        print(f"✅ Async page created: {result.url}")


if __name__ == "__main__":
    print("Notion Client Usage Examples\n")

    # Run sync examples
    # example_1_basic_sync()
    # example_2_from_file()
    # example_3_database_entry()

    # Run async examples
    # asyncio.run(example_4_async_batch())
    # asyncio.run(example_5_async_single())

    print("\nUncomment the examples you want to run and set your page IDs.")
