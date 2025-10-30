from ai.config import QIANWEN_API_KEY, KBAR_ANALYSIS_PROMPT, KBAR_ANALYSIS_PROMPT_SHORT
from openai import OpenAI
from pathlib import Path
from typing import Optional
from tools.log import get_analyze_logger

logger = get_analyze_logger()

client = OpenAI(
    api_key=QIANWEN_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

def analyze_kbar_data(csv_file_path: Path) -> Optional[str]:
    if not QIANWEN_API_KEY:
        raise ValueError("QIANWEN_API_KEY is not set in environment variables.")
    
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")
    
    try:
        file_object = client.files.create(
            file=Path(csv_file_path),
            purpose="file-extract"
        )
        
        logger.info(f"Uploaded file {csv_file_path} with file ID: {file_object.id}")
        
        completion = client.chat.completions.create(
            model="qwen3-max",
            messages=[
                {
                    "role": "system",
                    "content": KBAR_ANALYSIS_PROMPT_SHORT,
                },
                {
                    "role": "system",
                    "content": f"fileid://{file_object.id}",
                },
                {
                    "role": "user",
                    "content": f"",
                },
            ]
        )
        logger.info(f"Received analysis response from QianWen API: \n{completion.choices[0].message.content}")
        return completion.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Error during k-bar data analysis: {e}")
        return None