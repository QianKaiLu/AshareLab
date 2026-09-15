"""市场日报图版渲染：markdown → PNG。

薄封装，**不做任何数据加工**——图版的排版由 `qk-stock-market-daily` skill 的步骤 4
按 `references/image_report_format.md` 重写完成，这里只负责渲染。

不把 `market/analyze.py:render()` 的输出直接喂进来的原因见那份规范：它是逐行拼接的
紧凑文本，渲染器的 `nl2br` 会把单换行变成 `<br>`，整段粘成一块文字墙。

归档约定与 `b1_results/`、`portfolio/swing/daily/` 一致：日期命名的 markdown 落
`market_reports/YYYY-MM-DD.md` 并**入 git**（那是可回溯的记录）；PNG 落在同目录但
**不入 git**（1.1MB/天，一年 275MB，且随时可从 md 重新渲染）。

用法:
    python workflow/render_market_report.py                    # market_reports/ 下最新的一份
    python workflow/render_market_report.py market_reports/2026-09-15.md
    python workflow/render_market_report.py <md> --no-open
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
REPORT_DIR = REPO / "market_reports"
DEFAULT_GLOB = "*.md"


def latest_markdown() -> Optional[Path]:
    """market_reports/ 下最新的图版 markdown。按文件名排序取（日期命名，字典序即时间序），
    同一天重跑覆盖同名文件，所以不需要看 mtime。"""
    if not REPORT_DIR.is_dir():
        return None
    files = sorted(REPORT_DIR.glob(DEFAULT_GLOB))
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
    ap = argparse.ArgumentParser(description="市场日报图版渲染")
    ap.add_argument("md", nargs="?", help="图版 markdown 路径，缺省取 output/ 下最新的")
    ap.add_argument("--out", help="输出 PNG 路径，缺省与 md 同名")
    ap.add_argument("--no-open", action="store_true", help="渲染后不打开文件夹")
    args = ap.parse_args()

    md = Path(args.md) if args.md else latest_markdown()
    if md is None:
        logger.error(f"❌ {REPORT_DIR} 下没有 markdown，先生成图版报告")
        return 1
    md.parent.mkdir(parents=True, exist_ok=True)

    out = render(md, Path(args.out) if args.out else None, open_after=not args.no_open)
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
