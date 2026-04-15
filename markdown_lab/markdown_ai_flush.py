from pathlib import Path
from typing import Optional, Any
from jinja2 import Template

from ai.ai_api_profile import QWEN_MAX, DEEPSEEK_REASONER, DOUBAO_Seed_2_0_mini, QWEN_3_6_PLUS
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

prompt2 = """
# Role
你是一位精通 Markdown 语法和排版美学的专业内容编辑专家。你的任务是将一段从网页中抓取、含有噪声的原始 Markdown 文本转化为结构清晰、视觉精美、纯净的文章正文。

# Goals
1. **去粗取精**：彻底移除与文章主体无关的网页残留（如：导航栏、侧边栏、社交分享按钮、评论区、广告、页脚版权、相关推荐等）。
2. **完美保留**：严禁修改文章的核心正文内容。严禁改动任何图片链接 `![]()`、链接 `[]()`、代码块以及 `<meta name="referrer" ...>` 标签。
3. **格式美化**：优化标题层级（H1, H2, H3），规范段落间距，修正加粗、列表、引用（Blockquote）和表格的排版，使其符合专业排版规范。

# Constraints
- **内容完整性**：不得遗漏任何文章正文段落。
- **图片安全**：确保所有图片 Markdown 语法保持原样，不得删除或重写图片 URL。
- **禁止幻觉**：不要尝试续写文章或添加原文中不存在的观点。
- **输出要求**：仅输出清洗美化后的 Markdown 内容，不要包含任何自我陈述或解释。
- 文章头部的链接、作者信息、日期等元信息不要删除。

# Workflow
1. **识别主体**：分析输入的 Markdown，确定文章的标题、作者、日期和正文起始/结束位置。
2. **清理噪声**：去除文章中和正文无关的内容，包括网页的一些残留、广告等。
3. **结构重组**：确保全文只有一个 H1 标题，合理分布 H2/H3。修正 Markdown 语法错误（如标题前缺少空格、列表嵌套错误等），可以适当丰富格式。
4. **细节打磨**：
    - 在中英文、数字之间增加一个空格。
    - 统一标点符号（如中文环境下使用全角标点）。
    - 确保段落之间有且仅有一个空行。
"""

def markdown_ai_flush(content: str) -> Optional[str]:
    if not content:
        logger.warning("No content to flush.")
        return None

    try:
        result = chat(
            prompt=prompt2,
            contents=[f"{content}"],
            profile=QWEN_3_6_PLUS(),
            config=ChatConfig(print_output=True),
        )
        return result.content

    except Exception as e:
        logger.error(f"Error during markdown content flushing: {e}")
        return None