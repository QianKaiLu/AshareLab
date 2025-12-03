from ai.config import QIANWEN_API_KEY
from openai import OpenAI
from pathlib import Path
from typing import Optional, Any
from tools.log import get_analyze_logger
from jinja2 import Template
from ai.ai_api_profile import ApiProfile, QWEN_MAX, DEEPSEEK_REASONER

logger = get_analyze_logger()
co_name = "慢就是稳稳就是快实验室（Lazy-Lab）"
author = "钱大头"

API_PROFILE: ApiProfile = DEEPSEEK_REASONER()

client = OpenAI(
    api_key=API_PROFILE.api_key,
    base_url=API_PROFILE.base_url,
)

with open(Path(__file__).parent / "kbar_analysis_prompt.jinja") as f:
    template = Template(f.read())
    KBAR_ANALYSIS_PROMPT = template.render(co_name=co_name, author=author)

with open(Path(__file__).parent / "kbar_analysis_prompt_short.jinja") as f:
    template = Template(f.read())
    KBAR_ANALYSIS_PROMPT_SHORT = template.render(co_name=co_name, author=author)

def analyze_kbar_data_openai(csv_file_path: Path, base_info: dict, recent_news: Any) -> Optional[str]:
    if not QIANWEN_API_KEY:
        raise ValueError("QIANWEN_API_KEY is not set in environment variables.")
    
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")
    
    try:
        csv_content = csv_file_path.read_text(encoding="utf-8")
        logger.info(f"Read CSV file content from {csv_file_path}")
        
        completion = client.chat.completions.create(
            model=API_PROFILE.model,
            messages=[
                {
                    "role": "system",
                    "content": KBAR_ANALYSIS_PROMPT,
                },
                {
                    "role": "user",
                    "content": f"股票基本信息：{base_info}",
                },
                {
                    "role": "user",
                    "content": f"近期相关新闻：{recent_news}",
                },
                {
                    "role": "user",
                    "content": f"csv文件内容：\n\n{csv_content}",
                },
            ],
            stream=True,
            stream_options={
                "include_usage": False,
            }
        )
        md_content = ""
        received_length = 0
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content is not None:
                md_content += chunk.choices[0].delta.content
                received_length += len(chunk.choices[0].delta.content)
                print(f"\rReceived data length: {received_length:<10}", end="", flush=True)
        print()  # for newline after streaming
        return md_content
        
    except Exception as e:
        logger.error(f"Error during k-bar data analysis: {e}")
        return None