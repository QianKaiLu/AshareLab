"""报告图版渲染：markdown → PNG（市场日报、B1 日更通用）。

薄封装，**不做任何数据加工**——图版的排版由各 skill 按自己的
`references/image_report_format.md` 重写完成，这里只负责渲染。

**为什么必须重写而不是直接渲终端输出**：`market/analyze.py:render()` 那种逐行拼接的
紧凑文本，配合渲染器开着的 `nl2br`，相邻两行会被粘进同一个 `<p>`，成一块没有呼吸感
的文字墙。实测记录见 `qk-stock-market-daily/references/image_report_format.md`。

归档约定：日期命名的 markdown 与其 PNG 同目录存放（`market_reports/`、`b1_results/`），
**两个都入 git**（用户 2026-09-15 决定）。

用法:
    python workflow/render_report.py                                # market_reports/ 最新一份
    python workflow/render_report.py --dir b1_results               # B1 存档最新一份
    python workflow/render_report.py b1_results/2026-09-15.md       # 指定文件
    python workflow/render_report.py <md> --no-open                 # 不自动打开
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from tools.log import get_analyze_logger
from tools.markdown_lab import render_markdown_to_image

logger = get_analyze_logger()

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DIR = "market_reports"


def latest_markdown(report_dir: Path) -> Optional[Path]:
    """目录下最新的图版 markdown。按文件名排序取（日期命名，字典序即时间序），
    同一天重跑覆盖同名文件，所以不需要看 mtime。"""
    if not report_dir.is_dir():
        return None
    files = sorted(report_dir.glob("*.md"))
    return files[-1] if files else None


def render(md_path: Path, out_path: Optional[Path] = None,
           open_after: bool = True) -> Optional[Path]:
    """把图版 markdown 渲染成 PNG。返回图片路径，失败返回 None。"""
    if not md_path.is_file():
        logger.error(f"❌ markdown 不存在: {md_path}")
        return None

    out = out_path or md_path.with_suffix(".png")
    content = md_path.read_text(encoding="utf-8")
    if not content.strip():
        logger.error(f"❌ markdown 为空: {md_path}")
        return None

    logger.info(f"🖼️ 渲染 {md_path.name} → {out.name}（{len(content)} 字符）")
    render_markdown_to_image(content, out, open_folder_after=open_after)
    if not out.is_file():
        logger.error("❌ 渲染未产出文件，检查 Playwright 浏览器是否已安装"
                     "（conda run -n stock playwright install chromium）")
        return None
    logger.info(f"✅ 已生成 {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="报告图版渲染（市场日报 / B1 日更通用）")
    ap.add_argument("md", nargs="?", help="图版 markdown 路径，缺省取 --dir 下最新的")
    ap.add_argument("--dir", default=DEFAULT_DIR,
                    help=f"缺省扫描的目录（默认 {DEFAULT_DIR}，B1 用 b1_results）")
    ap.add_argument("--out", help="输出 PNG 路径，缺省与 md 同名")
    ap.add_argument("--no-open", action="store_true", help="渲染后不自动打开")
    args = ap.parse_args()

    report_dir = Path(args.dir)
    if not report_dir.is_absolute():
        report_dir = REPO / report_dir
    md = Path(args.md) if args.md else latest_markdown(report_dir)
    if md is None:
        logger.error(f"❌ {report_dir} 下没有 markdown，先生成图版报告")
        return 1
    md.parent.mkdir(parents=True, exist_ok=True)

    out = render(md, Path(args.out) if args.out else None, open_after=not args.no_open)
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
