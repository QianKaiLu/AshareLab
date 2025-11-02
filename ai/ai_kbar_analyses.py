from ai.config import QIANWEN_API_KEY, KBAR_ANALYSIS_PROMPT
from openai import OpenAI
from pathlib import Path
from typing import Optional
from tools.log import get_analyze_logger
from jinja2 import Template

logger = get_analyze_logger()

client = OpenAI(
    api_key=QIANWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

with open(Path(__file__).parent / "kbar_analysis_prompt_short.jinja") as f:
    template = Template(f.read())
    co_name = "慢就是快实验室"
    author = "钱大头"
    KBAR_ANALYSIS_PROMPT_SHORT = template.render(co_name=co_name, author=author)
    KBAR_ANALYSIS_PROMPT = template.render(co_name="慢就是稳稳就是快实验室（Lazy-Lab）", author=author)


def analyze_kbar_data_openai(csv_file_path: Path, base_info: dict) -> Optional[str]:
    if not QIANWEN_API_KEY:
        raise ValueError("QIANWEN_API_KEY is not set in environment variables.")
    
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")
    
    try:
        csv_content = csv_file_path.read_text(encoding="utf-8")
        logger.info(f"Read CSV file content from {csv_file_path}")
        
        completion = client.chat.completions.create(
            model="qwen3-max",
            messages=[
                {
                    "role": "system",
                    "content": KBAR_ANALYSIS_PROMPT,
                },
                {
                    "role": "user",
                    "content": f"股票基本信息：{base_info}。",
                },
                {
                    "role": "user",
                    "content": f"csv文件内容：\n\n{csv_content}",
                },
            ]
        )
        logger.info(f"Received analysis response from QianWen API: \n{completion.choices[0].message.content}")
        return completion.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Error during k-bar data analysis: {e}")
        return None