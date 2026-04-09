"""
url_to_markdown.py
使用 Playwright (async) 渲染动态网页，在浏览器内提取阅读模式内容，输出结构化 Markdown。
支持单 URL 或批量并发拉取，返回包含 markdown 内容或错误信息的结果对象。

依赖: playwright, trafilatura, markdownify, readability-lxml, lxml
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import sys
from dataclasses import dataclass
from typing import Optional, Union
from urllib.parse import urljoin

import trafilatura
from lxml import html as lxml_html
from markdownify import markdownify
from playwright.async_api import async_playwright, Page
from readability import Document as ReadabilityDocument

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

CONSENT_SELECTORS = [
    "button:has-text('Accept')",
    "button:has-text('Accept All')",
    "button:has-text('OK')",
    "button:has-text('Got it')",
    "button:has-text('接受')",
    "button:has-text('同意')",
    "button:has-text('我知道了')",
    "[id*='cookie'] button",
    "[class*='consent'] button",
]

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
window.chrome = {runtime: {}};
"""

# 在浏览器内执行的内容提取脚本
# 策略：找到包含最多文本+图片的主内容区域，清理噪声元素，返回干净 HTML
EXTRACT_CONTENT_JS = """
() => {
    // 移除噪声元素
    const removeSelectors = [
        'script', 'style', 'noscript', 'iframe', 'svg',
        'nav', 'header', 'footer',
        '[class*="comment"]', '[id*="comment"]',
        '[class*="sidebar"]', '[id*="sidebar"]',
        '[class*="recommend"]', '[class*="related"]',
        '[class*="share"]', '[class*="social"]',
        '[class*="ad-"]', '[class*="advertisement"]',
        '[class*="banner"]', '[id*="banner"]',
    ];

    // 克隆 body 避免修改原始 DOM
    const clone = document.body.cloneNode(true);

    for (const sel of removeSelectors) {
        clone.querySelectorAll(sel).forEach(el => el.remove());
    }

    // 评分：找到包含最多正文的容器
    function score(el) {
        const text = el.textContent || '';
        const imgs = el.querySelectorAll('img');
        const paragraphs = el.querySelectorAll('p, [class*="bjh-p"], span.bjh-p');
        // 文本长度 + 图片加分 + 段落加分
        return text.length + imgs.length * 200 + paragraphs.length * 50;
    }

    // 候选容器：article、data-testid=article、或评分最高的 div
    let best = null;
    let bestScore = 0;

    // 优先查找语义化容器
    const candidates = clone.querySelectorAll(
        'article, [data-testid="article"], [role="article"], ' +
        '[class*="article-content"], [class*="post-content"], ' +
        '[class*="entry-content"], [class*="content-text"], ' +
        '[itemprop="articleBody"], main'
    );
    for (const el of candidates) {
        const s = score(el);
        if (s > bestScore) { bestScore = s; best = el; }
    }

    // 如果语义化容器分数不够，用启发式算法
    if (bestScore < 500) {
        const divs = clone.querySelectorAll('div, section');
        for (const el of divs) {
            const s = score(el);
            // 选择分数最高但不是整个 body 的容器
            if (s > bestScore && el.children.length > 1 && el.children.length < 100) {
                bestScore = s;
                best = el;
            }
        }
    }

    if (!best) return null;

    // 清理容器内的噪声
    best.querySelectorAll(
        'script, style, [class*="comment"], [class*="share"], ' +
        '[class*="recommend"], [class*="related"], [class*="ad-"]'
    ).forEach(el => el.remove());

    // 处理懒加载图片：data-src -> src
    best.querySelectorAll('img').forEach(img => {
        const dataSrc = img.getAttribute('data-src') ||
                        img.getAttribute('data-original') ||
                        img.getAttribute('data-lazy-src');
        if (dataSrc && !img.getAttribute('src')) {
            img.setAttribute('src', dataSrc);
        }
        // 移除极小的图标/追踪像素
        const w = parseInt(img.getAttribute('width') || '999');
        const h = parseInt(img.getAttribute('height') || '999');
        if (w < 10 || h < 10) img.remove();
    });

    return best.innerHTML;
}
"""


@dataclass
class FetchResult:
    """单个 URL 的拉取结果。"""

    url: str
    title: Optional[str] = None
    markdown: Optional[str] = None
    error: Optional[str] = None
    success: bool = False


async def fetch_page_html(url: str, page: Page, timeout_ms: int = 30000) -> str:
    """使用 Playwright 异步渲染页面，返回完整 HTML。"""
    logger.info(f"Loading: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        logger.warning(f"networkidle timeout for {url}, continuing.")

    # 尝试关闭 cookie / 隐私弹窗
    for selector in CONSENT_SELECTORS:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=500):
                await btn.click(timeout=1000)
                break
        except Exception:
            continue

    # 滚动触发懒加载
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1500)

    return await page.content()


async def extract_article_html(page: Page) -> Optional[str]:
    """在浏览器内执行 JS 提取文章主体 HTML（保留图片）。"""
    return await page.evaluate(EXTRACT_CONTENT_JS)


def _fix_relative_urls(html_str: str, base_url: str) -> str:
    """将 HTML 中的相对 URL 转为绝对 URL。"""
    tree = lxml_html.fromstring(html_str)
    for img in tree.iter("img"):
        src = img.get("src")
        if src and not src.startswith(("http://", "https://", "data:")):
            img.set("src", urljoin(base_url, src))
    for a in tree.iter("a"):
        href = a.get("href")
        if href and not href.startswith(("http://", "https://", "mailto:", "#", "javascript:")):
            a.set("href", urljoin(base_url, href))
    return lxml_html.tostring(tree, encoding="unicode")


def _html_to_markdown(html_str: str) -> str:
    """将清理后的 HTML 转为 Markdown，保留标题、图片、链接、表格。"""
    md = markdownify(html_str, heading_style="ATX", strip=["script", "style"])
    # 清理多余空行
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def _extract_metadata(html: str, url: str) -> dict:
    """使用 trafilatura 提取元数据（标题、作者、日期等）。"""
    doc = trafilatura.bare_extraction(html, url=url, with_metadata=True)
    meta = {}
    if doc:
        meta = {
            "title": doc.title,
            "author": doc.author,
            "date": doc.date,
            "sitename": doc.sitename,
        }
    # trafilatura 标题可能不准（如百度家号会拿到"评论"），多源取标题再择优
    tree = lxml_html.fromstring(html)
    candidates: list[str] = []
    # 优先级：og:title > h1 > <title> > trafilatura
    og = tree.find('.//meta[@property="og:title"]')
    if og is not None and og.get("content", "").strip():
        candidates.append(og.get("content").strip())
    h1 = tree.find(".//h1")
    if h1 is not None and h1.text_content().strip():
        candidates.append(h1.text_content().strip())
    title_el = tree.find(".//title")
    if title_el is not None and title_el.text_content().strip():
        candidates.append(title_el.text_content().strip())
    if meta.get("title"):
        candidates.append(meta["title"])
    # 选第一个合理长度的候选（跳过"评论"等噪声短标题）
    valid = [c for c in candidates if 4 < len(c) < 200]
    if valid:
        meta["title"] = valid[0]
    return meta


def build_markdown(article_html: str, metadata: dict, url: str) -> str:
    """组装最终 Markdown：元数据头 + 正文。"""
    article_html = _fix_relative_urls(article_html, url)
    body = _html_to_markdown(article_html)
    if not body:
        return ""

    parts: list[str] = []
    title = metadata.get("title")
    if title:
        parts.append(f"# {title}\n")

    meta_lines: list[str] = []
    if metadata.get("author"):
        meta_lines.append(f"**Author**: {metadata['author']}")
    if metadata.get("date"):
        meta_lines.append(f"**Date**: {metadata['date']}")
    if metadata.get("sitename"):
        meta_lines.append(f"**Source**: {metadata['sitename']}")
    if meta_lines:
        parts.append("> " + "  \n> ".join(meta_lines) + "\n")
    if parts:
        parts.append("---\n")
    parts.append(body)

    return "\n".join(parts)


async def _process_single(url: str, page: Page, timeout_ms: int) -> FetchResult:
    """处理单个 URL：渲染 + 提取，返回 FetchResult，不抛异常。"""
    try:
        html = await fetch_page_html(url, page, timeout_ms)
        metadata = _extract_metadata(html, url)

        # 方案 1：在浏览器内 JS 提取（保留图片最可靠）
        article_html = await extract_article_html(page)

        # 方案 2：fallback 到 readability-lxml
        if not article_html or len(article_html) < 100:
            logger.info(f"JS extraction insufficient, falling back to readability: {url}")
            rdoc = ReadabilityDocument(html)
            article_html = rdoc.summary()
            if not metadata.get("title"):
                metadata["title"] = rdoc.title()

        if not article_html or len(article_html) < 50:
            return FetchResult(
                url=url,
                title=metadata.get("title"),
                error="No main content extracted (anti-bot or empty page).",
            )

        markdown = build_markdown(article_html, metadata, url)
        if not markdown:
            return FetchResult(
                url=url,
                title=metadata.get("title"),
                error="Markdown conversion produced empty result.",
            )

        return FetchResult(
            url=url,
            title=metadata.get("title"),
            markdown=markdown,
            success=True,
        )
    except Exception as e:
        logger.error(f"Failed for {url}: {e}")
        return FetchResult(url=url, error=str(e))


async def batch_url_to_markdown(
    urls: Union[str, list[str]],
    max_concurrent: int = 5,
    timeout_ms: int = 30000,
) -> list[FetchResult]:
    """
    批量并发拉取网页并转换为 Markdown。

    Args:
        urls: 单个 URL 字符串或 URL 列表。
        max_concurrent: 最大并发数（同时打开的浏览器标签页数）。
        timeout_ms: 每个页面的导航超时时间（毫秒）。

    Returns:
        与输入顺序一致的 FetchResult 列表。
    """
    if isinstance(urls, str):
        urls = [urls]

    semaphore = asyncio.Semaphore(max_concurrent)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=DEFAULT_UA,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            java_script_enabled=True,
        )
        await context.add_init_script(STEALTH_SCRIPT)

        async def _worker(url: str) -> FetchResult:
            async with semaphore:
                page = await context.new_page()
                try:
                    await asyncio.sleep(random.uniform(0.3, 1.5))
                    return await _process_single(url, page, timeout_ms)
                finally:
                    await page.close()

        results = await asyncio.gather(*[_worker(u) for u in urls])
        await context.close()
        await browser.close()

    return list(results)


def _print_result(r: FetchResult, preview_len: int = 500):
    status = "OK" if r.success else "FAIL"
    print(f"\n[{status}] {r.url}")
    if r.success:
        print(f"  Title: {r.title}")
        print(f"  Length: {len(r.markdown)} chars")
        preview = r.markdown[:preview_len]
        if len(r.markdown) > preview_len:
            preview += "\n  ..."
        print(f"  Preview:\n{preview}")
    else:
        print(f"  Error: {r.error}")


async def main():
    """Demo: 单 URL + 批量拉取。"""
    test_urls = [
        "https://mp.weixin.qq.com/s/voh2WPGcU2J990qZZk4row",
        # "https://www.ruanyifeng.com/blog/2024/07/weekly-issue-308.html",
    ]

    # 单 URL 测试
    logger.info("=== Single URL ===")
    results = await batch_url_to_markdown(test_urls[0])
    for r in results:
        _print_result(r, preview_len=2000)

    # # 批量测试
    # logger.info("\n=== Batch URLs ===")
    # results = await batch_url_to_markdown(test_urls, max_concurrent=3)
    # for r in results:
    #     _print_result(r, preview_len=800)


if __name__ == "__main__":
    asyncio.run(main())
