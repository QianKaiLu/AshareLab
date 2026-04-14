from pathlib import Path
from typing import Optional, Any
from jinja2 import Template

from ai.ai_api_profile import QWEN_MAX, DEEPSEEK_REASONER
from ai.chat_service import chat, ChatConfig
from tools.log import get_analyze_logger

logger = get_analyze_logger()

prompt = """
你是一个 Markdown 格式排版助手，负责修复输入的 Markdown 文本。我会给你一段 Markdown 内容，请根据以下要求进行清洗：
- 识别 Markdown 文档内容、主题，一些和文档内容无关的字符、段落（比如广告、按钮、无关信息等）都可以删除。
- 保留正文内容，不要修改任何正文文字，只对格式进行清洗和修复。
- 去除所有无效字符，如控制字符、不可见字符等。
- 可以适当调整格式，使其更符合 Markdown 规范，并且使格式更美观丰富。
- 对于原文中包含的图片、链接等元素，尽量保留其 Markdown 语法，但如果它们明显无效或与内容无关，也可以删除。
- 请直接返回整理后的 Markdown 文本，不要附带别的信息。
"""

def markdown_ai_flush(content: str) -> Optional[str]:
    if not content:
        logger.warning("No content to flush.")
        return None

    try:
        result = chat(
            prompt=prompt,
            contents=[f"{content}"],
            profile=QWEN_MAX(),
            config=ChatConfig(print_output=True),
        )
        return result.content

    except Exception as e:
        logger.error(f"Error during markdown content flushing: {e}")
        return None