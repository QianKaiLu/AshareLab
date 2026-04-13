from pathlib import Path
from typing import Optional, Any
from jinja2 import Template

from ai.ai_api_profile import QWEN_MAX
from ai.chat_service import chat, ChatConfig
from tools.log import get_analyze_logger

logger = get_analyze_logger()
co_name = "鳗鱼实验室（Lazy-Lab）"
author = "钱大头"


def analyze_kbar_data_openai(csv_file_path: Path, base_info: dict, recent_news: Any, kline_chart_name: str = "") -> Optional[str]:
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")

    with open(Path(__file__).parent / "kbar_analysis_prompt.jinja") as f:
        template = Template(f.read())
        prompt = template.render(co_name=co_name, author=author, kline_chart_name=kline_chart_name)

    try:
        csv_content = csv_file_path.read_text(encoding="utf-8")
        logger.info(f"Read CSV file content from {csv_file_path}")

        result = chat(
            prompt=prompt,
            contents=[
                f"股票基本信息：{base_info}",
                f"近期相关新闻：{recent_news}",
                f"csv文件内容：\n\n{csv_content}",
            ],
            profile=QWEN_MAX(),
            config=ChatConfig(print_output=True),
        )
        return result.content

    except Exception as e:
        logger.error(f"Error during k-bar data analysis: {e}")
        return None
