"""
qk-notion — Notion 笔记写入命令行工具

用法:
    qk-notion write <source> [选项]          将 markdown / 网页 / stdin 写入 Notion
    qk-notion children <page_id> [选项]       列出子页面
    qk-notion batch [选项]                    批量导入

示例:
    # Markdown 文件写入
    qk-notion write docs/report.md -p <page_id>

    # 网页抓取并写入
    qk-notion write https://example.com/article -p <page_id>

    # stdin 输入
    cat notes.md | qk-notion write - -p <page_id>

    # 批量导入文件
    qk-notion batch -f "output/*.md" -p <page_id>

    # 查看子页面
    qk-notion children <page_id> -r
"""

import argparse
import asyncio
import glob
import logging
import os
import sys
from pathlib import Path

import colorlog
from dotenv import load_dotenv

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from notion.notion_sync_client import NotionClient   # noqa: E402
from notion.notion_markdown import (                  # noqa: E402
    load_markdown,
    extract_title_from_markdown,
)

# ══════════════════════════════════════════════════════════════════════════════
# 日志
# ══════════════════════════════════════════════════════════════════════════════

LOG_COLORS = {
    "INFO": "white",
    "SUCCESS": "bold_green",
    "WARNING": "bold_yellow",
    "ERROR": "bold_red",
}

SUCCESS_LEVEL = 21
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def _success(self, message, *args, **kwargs):
    if self.isEnabledFor(SUCCESS_LEVEL):
        self._log(SUCCESS_LEVEL, message, args, **kwargs)


logging.Logger.success = _success


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("qk_notion")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.handlers.clear()

    handler = colorlog.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(colorlog.ColoredFormatter(
        fmt="%(log_color)s%(message)s",
        log_colors=LOG_COLORS,
        reset=True,
    ))
    logger.addHandler(handler)
    return logger


log = _setup_logger()


# ══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════════════════

def _get_token(token_arg: str | None = None) -> str:
    """获取 Notion token，优先级：命令行参数 > 环境变量。"""
    token = token_arg or os.getenv("NOTION_TOKEN", "")
    if not token:
        log.error("未找到 Notion token。请设置 NOTION_TOKEN 环境变量或通过 --token 指定。")
        sys.exit(1)
    return token


def _detect_source_type(source: str) -> str:
    """识别输入来源类型：url | stdin | file | text"""
    if source == "-":
        return "stdin"
    if source.startswith(("http://", "https://")):
        return "url"
    if len(source) <= 255:
        p = Path(source)
        try:
            if p.exists() and p.is_file():
                return "file"
        except (OSError, ValueError):
            pass
    return "text"


def _load_content(source: str) -> tuple[str, str | None]:
    """根据来源类型加载内容，返回 (markdown, title_or_None)。"""
    src_type = _detect_source_type(source)

    if src_type == "stdin":
        log.info("📖 从标准输入读取...")
        md = sys.stdin.read()
        title = extract_title_from_markdown(md)
        return md, title

    if src_type == "url":
        log.info(f"🌐 抓取网页: {source}")
        from notion.url_to_markdown import batch_url_to_markdown
        results = asyncio.run(batch_url_to_markdown(source))
        r = results[0]
        if not r.success:
            log.error(f"抓取失败: {r.error}")
            sys.exit(1)
        log.success(f"  ✓  标题: {r.title}")
        log.success(f"  ✓  长度: {len(r.markdown)} 字符")
        return r.markdown, r.title

    if src_type == "file":
        log.info(f"📄 读取文件: {source}")
        md = load_markdown(source)
        title = extract_title_from_markdown(md)
        log.success(f"  ✓  长度: {len(md)} 字符")
        return md, title

    # src_type == "text"
    title = extract_title_from_markdown(source)
    return source, title


def _print_page_result(result, source_label: str = ""):
    """打印单页创建结果。"""
    if result.success:
        log.success(f"✅ {source_label}创建成功")
        log.success(f"   URL: {result.url}")
        log.success(f"   标题: {result.title}")
    else:
        log.error(f"❌ {source_label}创建失败: {result.error}")


# ══════════════════════════════════════════════════════════════════════════════
# 子命令: write
# ══════════════════════════════════════════════════════════════════════════════

def _cmd_write(args: argparse.Namespace) -> None:
    """将内容写入 Notion 页面。"""
    token = _get_token(args.token)
    content, auto_title = _load_content(args.source)
    title = args.title or auto_title

    if not title:
        log.warning("⚠️  未检测到标题，请使用 --title 指定")

    if args.dry_run:
        log.info("")
        log.warning("🔍 [DRY RUN] 预览模式，不实际写入")
        log.info(f"   标题: {title or '(无)'}")
        log.info(f"   父页面: {args.parent or '(无)'}")
        log.info(f"   数据库: {args.database or '(无)'}")
        log.info(f"   内容长度: {len(content)} 字符")
        preview = content[:300]
        if len(content) > 300:
            preview += "\n  ..."
        log.info(f"   内容预览:\n{preview}")
        return

    with NotionClient(token) as client:
        result = client.create_page_from_markdown(
            markdown=content,
            parent_page_id=args.parent,
            parent_data_source_id=args.database,
            title=title,
        )
        _print_page_result(result)


# ══════════════════════════════════════════════════════════════════════════════
# 子命令: children
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_tree(pages: list, indent: int = 0) -> list[str]:
    """将 NotionChildPage 列表格式化为树形文本。"""
    lines = []
    prefix = "  " * indent
    for page in pages:
        icon = "📁" if page.has_children else "📄"
        lines.append(f"{prefix}{icon} {page.title}  ({page.id})")
        if page.children:
            lines.extend(_fmt_tree(page.children, indent + 1))
    return lines


def _cmd_children(args: argparse.Namespace) -> None:
    """列出子页面。"""
    token = _get_token(args.token)

    with NotionClient(token) as client:
        if args.recursive or args.flat:
            pages = client.get_all_child_pages_flat(args.page_id)
        else:
            pages = client.get_child_pages(args.page_id, recursive=False)

    if not pages:
        log.info("(无子页面)")
        return

    if args.flat or not args.recursive:
        for p in pages:
            icon = "📁" if p.has_children else "📄"
            log.info(f"{icon} {p.title}  ({p.id})")
    else:
        for line in _fmt_tree(pages):
            log.info(line)

    log.success(f"\n共 {len(pages)} 个子页面")


# ══════════════════════════════════════════════════════════════════════════════
# 子命令: batch
# ══════════════════════════════════════════════════════════════════════════════

def _cmd_batch(args: argparse.Namespace) -> None:
    """批量导入。"""
    token = _get_token(args.token)
    requests: list[tuple[str, str | None, str]] = []  # (content, title, label)

    # ── 收集文件 ──
    if args.files:
        for pattern in args.files:
            paths = glob.glob(os.path.expanduser(pattern))
            if not paths:
                log.warning(f"⚠️  {pattern}: 未匹配到任何文件")
            for p in paths:
                md = load_markdown(p)
                title = extract_title_from_markdown(md)
                requests.append((md, title, str(p)))

    # ── 收集 URL ──
    if args.urls:
        urls_path = Path(args.urls)
        if not urls_path.exists():
            log.error(f"URL 列表文件不存在: {args.urls}")
            sys.exit(1)
        urls = [line.strip() for line in urls_path.read_text().splitlines()
                if line.strip() and not line.startswith("#")]
        if urls:
            log.info(f"🌐 批量抓取 {len(urls)} 个网页...")
            from notion.url_to_markdown import batch_url_to_markdown
            results = asyncio.run(batch_url_to_markdown(urls,
                                   max_concurrent=args.max_concurrent))
            for r in results:
                if r.success:
                    requests.append((r.markdown, r.title, r.url))
                else:
                    log.error(f"❌ {r.url}: {r.error}")

    # ── 收集 stdin ──
    if args.stdin:
        md = sys.stdin.read()
        title = extract_title_from_markdown(md)
        requests.append((md, title, "stdin"))

    if not requests:
        log.warning("没有可导入的内容。")
        return

    log.info(f"\n📦 准备导入 {len(requests)} 篇内容")
    log.info(f"   父页面: {args.parent or '(无)'}")
    log.info(f"   并发数: {args.max_concurrent}")
    log.info("")

    if args.dry_run:
        log.warning("🔍 [DRY RUN] 预览模式\n")
        for content, title, label in requests:
            log.info(f"  {label}: {title or '(无标题)'}  ({len(content)} 字符)")
        return

    with NotionClient(token) as client:
        success_count = 0
        for content, title, label in requests:
            log.info(f"📤 {label}")
            result = client.create_page_from_markdown(
                markdown=content,
                parent_page_id=args.parent,
                title=title or None,
            )
            if result.success:
                success_count += 1
                log.success(f"   ✅ {result.url}")
            else:
                log.error(f"   ❌ {result.error}")

    log.info("")
    log.success(f"✅ 成功 {success_count}/{len(requests)}")


# ══════════════════════════════════════════════════════════════════════════════
# 参数解析
# ══════════════════════════════════════════════════════════════════════════════

def _add_parent_args(parser: argparse.ArgumentParser) -> None:
    """添加 Notion 通用参数到 parser。"""
    group = parser.add_argument_group("Notion 选项")
    group.add_argument("--token", type=str, default=None,
                       help="Notion API token（默认读 $NOTION_TOKEN）")


def _add_target_args(parser: argparse.ArgumentParser) -> None:
    """添加目标位置参数（--parent / --database 互斥）。"""
    target = parser.add_argument_group("目标位置（二选一）")
    target.add_argument("-p", "--parent", type=str, default=None,
                        help="父页面 ID（创建子页面）")
    target.add_argument("-d", "--database", type=str, default=None,
                        help="数据库 data_source ID（创建数据库条目）")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Notion 笔记写入工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s write docs/notes.md -p <page_id>
  %(prog)s write https://example.com/article -p <page_id>
  %(prog)s write "### 笔记" -t "我的笔记" -p <page_id>
  %(prog)s children <page_id> -r
  %(prog)s batch -f "output/*.md" -p <page_id>
        """,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")
    sub.required = True

    # ── write ──
    p_write = sub.add_parser("write", help="写入内容到 Notion")
    p_write.add_argument("source", type=str,
                         help="Markdown 文件路径、网页 URL、'-' (stdin)、或纯文本")
    p_write.add_argument("-t", "--title", type=str, default=None,
                         help="页面标题（缺省时自动从 # H1 提取）")
    p_write.add_argument("--dry-run", action="store_true",
                         help="预览模式，不实际写入")
    _add_parent_args(p_write)
    _add_target_args(p_write)

    # ── children ──
    p_children = sub.add_parser("children", help="列出子页面")
    p_children.add_argument("page_id", type=str, help="父页面 ID")
    p_children.add_argument("-r", "--recursive", action="store_true",
                            help="递归列出所有子孙页面")
    p_children.add_argument("--flat", action="store_true",
                            help="扁平列表（不显示树形结构）")
    _add_parent_args(p_children)

    # ── batch ──
    p_batch = sub.add_parser("batch", help="批量导入")
    p_batch.add_argument("-f", "--files", type=str, nargs="+", default=None,
                         help="文件 glob 模式，如 'output/*.md'")
    p_batch.add_argument("-u", "--urls", type=str, default=None,
                         help="URL 列表文件（每行一个 URL，# 开头为注释）")
    p_batch.add_argument("--stdin", action="store_true",
                         help="从 stdin 读取内容")
    p_batch.add_argument("-c", "--max-concurrent", type=int, default=3,
                         help="最大并发数（默认 3）")
    p_batch.add_argument("--dry-run", action="store_true",
                         help="预览模式，不实际写入")
    _add_parent_args(p_batch)
    # batch 只支持 --parent，不支持 --database
    p_batch.add_argument("-p", "--parent", type=str, default=None,
                         help="父页面 ID")

    return parser.parse_args()


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

def main():
    args = parse_args()

    try:
        if args.command == "write":
            _cmd_write(args)
        elif args.command == "children":
            _cmd_children(args)
        elif args.command == "batch":
            _cmd_batch(args)
    except KeyboardInterrupt:
        log.warning("\n⚠️  用户中断")
        sys.exit(130)
    except Exception as e:
        log.error(f"\n❌ {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
