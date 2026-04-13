import os
from dotenv import load_dotenv
import asyncio
from notion.notion_client import NotionClient
from url_to_markdown import batch_url_to_markdown
from tools.log import get_analyze_logger
from markdown.markdown_ai_flush import markdown_ai_flush

load_dotenv()
NOTION_TOKEN = os.getenv("NOTION_TOKEN", default="")

notionClient = NotionClient(token=NOTION_TOKEN, timeout=30)
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
        
        ai_result = markdown_ai_flush(r.markdown)
        if ai_result:
            logger.info(f"Successfully flushed markdown content with AI. Length: {len(ai_result)} chars")
            r.markdown = ai_result
        else:
            logger.warning(f"AI flushing returned no content, using original markdown.")
        
        result = notionClient.create_page_from_markdown(
            markdown=r.markdown,
            parent_page_id="2f625008aa42803397fed440bca00ae9",
            title=r.title)
        logger.info(f"Notion page creation result: {result}")
    else:
        logger.error(f"  Error: {r.error}")

if __name__ == "__main__":
    asyncio.run(test())