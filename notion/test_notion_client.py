"""
test_notion_client.py
Test script for Notion API client wrapper.

Usage:
    1. Set NOTION_TOKEN in .env file
    2. Set TEST_PAGE_ID to a valid parent page ID
    3. Run: python notion/test_notion_client.py
"""

import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from notion import NotionClient, AsyncNotionClient, NotionPageRequest, NotionParent

# Load environment variables
load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")

# IMPORTANT: Replace with your actual parent page ID
TEST_PAGE_ID = "YOUR_PAGE_ID_HERE"


def test_sync_basic():
    """Test synchronous client with basic markdown string."""
    print("\n=== Test 1: Sync Client - Basic Markdown ===")

    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN not found in .env")
        return

    if TEST_PAGE_ID == "YOUR_PAGE_ID_HERE":
        print("⚠️  Please set TEST_PAGE_ID in test_notion_client.py")
        return

    client = NotionClient(NOTION_TOKEN)

    markdown = """# Test Page from Sync Client

This is a test page created by the NotionClient.

## Features

- Markdown support
- Automatic title extraction
- Error handling

## Code Example

```python
client = NotionClient(token)
result = client.create_page_from_markdown(markdown, parent_page_id="...")
```

**Status:** ✅ Working
"""

    result = client.create_page_from_markdown(
        markdown=markdown,
        parent_page_id=TEST_PAGE_ID
    )

    if result.success:
        print(f"✅ Sync test passed")
        print(f"   Page ID: {result.page_id}")
        print(f"   URL: {result.url}")
        print(f"   Title: {result.title}")
    else:
        print(f"❌ Sync test failed: {result.error}")


def test_sync_with_title():
    """Test synchronous client with explicit title."""
    print("\n=== Test 2: Sync Client - Explicit Title ===")

    if not NOTION_TOKEN or TEST_PAGE_ID == "YOUR_PAGE_ID_HERE":
        print("⚠️  Skipping (configure NOTION_TOKEN and TEST_PAGE_ID)")
        return

    client = NotionClient(NOTION_TOKEN)

    markdown = """This page has no H1 heading.

But it has an explicit title set via the API parameter.

- Item 1
- Item 2
- Item 3
"""

    result = client.create_page_from_markdown(
        markdown=markdown,
        parent_page_id=TEST_PAGE_ID,
        title="Custom Title Test"
    )

    if result.success:
        print(f"✅ Title test passed")
        print(f"   Page ID: {result.page_id}")
        print(f"   Title: {result.title}")
    else:
        print(f"❌ Title test failed: {result.error}")


def test_sync_from_file():
    """Test synchronous client loading markdown from file."""
    print("\n=== Test 3: Sync Client - Load from File ===")

    if not NOTION_TOKEN or TEST_PAGE_ID == "YOUR_PAGE_ID_HERE":
        print("⚠️  Skipping (configure NOTION_TOKEN and TEST_PAGE_ID)")
        return

    # Create a temporary markdown file
    test_file = Path(__file__).parent / "test_temp.md"
    test_file.write_text("""# File-based Test

This content was loaded from a markdown file.

## Details

- File path: test_temp.md
- Loaded automatically by the client
- Cleaned up after test
""", encoding='utf-8')

    try:
        client = NotionClient(NOTION_TOKEN)

        result = client.create_page_from_markdown(
            markdown=test_file,
            parent_page_id=TEST_PAGE_ID
        )

        if result.success:
            print(f"✅ File test passed")
            print(f"   Page ID: {result.page_id}")
            print(f"   Title: {result.title}")
        else:
            print(f"❌ File test failed: {result.error}")
    finally:
        # Clean up temp file
        if test_file.exists():
            test_file.unlink()


async def test_async_basic():
    """Test asynchronous client."""
    print("\n=== Test 4: Async Client - Basic ===")

    if not NOTION_TOKEN or TEST_PAGE_ID == "YOUR_PAGE_ID_HERE":
        print("⚠️  Skipping (configure NOTION_TOKEN and TEST_PAGE_ID)")
        return

    client = AsyncNotionClient(NOTION_TOKEN)

    markdown = """# Async Test Page

This page was created using the AsyncNotionClient.

## Async Features

- Non-blocking I/O
- Batch processing support
- Concurrent page creation

**Created:** via async/await
"""

    result = await client.create_page_from_markdown(
        markdown=markdown,
        parent_page_id=TEST_PAGE_ID
    )

    if result.success:
        print(f"✅ Async test passed")
        print(f"   Page ID: {result.page_id}")
        print(f"   URL: {result.url}")
    else:
        print(f"❌ Async test failed: {result.error}")


async def test_async_batch():
    """Test asynchronous batch creation."""
    print("\n=== Test 5: Async Client - Batch Creation ===")

    if not NOTION_TOKEN or TEST_PAGE_ID == "YOUR_PAGE_ID_HERE":
        print("⚠️  Skipping (configure NOTION_TOKEN and TEST_PAGE_ID)")
        return

    client = AsyncNotionClient(NOTION_TOKEN)

    # Create 3 pages concurrently
    requests = [
        NotionPageRequest(
            markdown=f"# Batch Test {i+1}\n\nThis is page {i+1} of 3 created concurrently.",
            parent=NotionParent(type="page_id", id=TEST_PAGE_ID),
            title=f"Batch Page {i+1}"
        )
        for i in range(3)
    ]

    results = await client.batch_create_pages(requests, max_concurrent=3)

    success_count = sum(1 for r in results if r.success)
    print(f"✅ Batch test: {success_count}/{len(results)} pages created")

    for i, result in enumerate(results):
        if result.success:
            print(f"   Page {i+1}: {result.page_id}")
        else:
            print(f"   Page {i+1}: Failed - {result.error}")


def test_error_handling():
    """Test error handling with invalid parameters."""
    print("\n=== Test 6: Error Handling ===")

    if not NOTION_TOKEN:
        print("⚠️  Skipping (configure NOTION_TOKEN)")
        return

    client = NotionClient(NOTION_TOKEN)

    # Test 1: No parent specified
    try:
        result = client.create_page_from_markdown(
            markdown="# Test",
            parent_page_id=None,
            parent_data_source_id=None
        )
        print(f"   Test 1 (no parent): {'❌ Should have raised error' if result.success else '✅ Correctly failed'}")
    except ValueError as e:
        print(f"   Test 1 (no parent): ✅ Correctly raised ValueError")

    # Test 2: Both parents specified
    try:
        result = client.create_page_from_markdown(
            markdown="# Test",
            parent_page_id="123",
            parent_data_source_id="456"
        )
        print(f"   Test 2 (both parents): {'❌ Should have raised error' if result.success else '✅ Correctly failed'}")
    except ValueError as e:
        print(f"   Test 2 (both parents): ✅ Correctly raised ValueError")

    # Test 3: Invalid page ID (should return error result, not raise)
    result = client.create_page_from_markdown(
        markdown="# Test",
        parent_page_id="invalid-id-12345"
    )
    if not result.success and result.error:
        print(f"   Test 3 (invalid ID): ✅ Returned error result")
    else:
        print(f"   Test 3 (invalid ID): ❌ Should have failed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Notion Client Test Suite")
    print("=" * 60)

    # Sync tests
    test_sync_basic()
    test_sync_with_title()
    test_sync_from_file()

    # Async tests
    asyncio.run(test_async_basic())
    asyncio.run(test_async_batch())

    # Error handling
    test_error_handling()

    print("\n" + "=" * 60)
    print("Test suite completed")
    print("=" * 60)


if __name__ == "__main__":
    main()
