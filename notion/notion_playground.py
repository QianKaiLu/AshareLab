import os
from dotenv import load_dotenv
import asyncio
from notion_client_wrapper import NotionClient
from url_to_markdown import batch_url_to_markdown
from tools.log import get_analyze_logger

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", default="")

notionClient = NotionClient(token=NOTION_TOKEN)
logger = get_analyze_logger()

async def test():
    test_urls = [
        "https://mp.weixin.qq.com/s/voh2WPGcU2J990qZZk4row",
        # "https://www.ruanyifeng.com/blog/2024/07/weekly-issue-308.html",
    ]
    results = await batch_url_to_markdown(test_urls[0])
    r = results[0]
    if r.success:
        logger.info(f"Successfully fetched and converted URL to markdown:")
        logger.info(f"  Title: {r.title}")
        logger.info(f"  Length: {len(r.markdown)} chars")
        markdown = r.markdown
        # logger.info(f"  Markdown preview:\n{markdown[:500]}...")
        
        result = notionClient.create_page_from_markdown(
            markdown=markdown,
            parent_page_id="32225008aa4280a3a9b2e7f956e88286",
            title=r.title)
        
        logger.info(f"Notion page creation result: {result}")
    else:
        logger.error(f"  Error: {r.error}")

if __name__ == "__main__":
    asyncio.run(test())