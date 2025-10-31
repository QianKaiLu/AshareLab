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

def analyze_kbar_data2(csv_file_path: Path, base_info: dict) -> Optional[str]:
    if not QIANWEN_API_KEY:
        raise ValueError("QIANWEN_API_KEY is not set in environment variables.")
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")

    try:
        # 上传文件
        file_object = client.files.create(
            file=csv_file_path, 
            purpose="file-extract"
        )
        logger.info(f"Uploaded file {csv_file_path} with file ID: {file_object.id}")

        # 构造消息
        messages = [
            {"role": "system", "content": KBAR_ANALYSIS_PROMPT},
            {"role": "system", "content": f"股票基本信息：{base_info}。"},
            {"role": "system", "content": f"fileid://{file_object.id}"},
            {"role": "user", "content": ""},  # 触发分析
        ]

        # 流式请求
        stream = client.chat.completions.create(
            model="qwen3-max",
            messages=messages,
            stream=True
        )

        full_response = ""
        total_chars = 0

        for chunk in stream:
            delta = chunk.choices[0].delta
            content = delta.content or ""
            full_response += content
            total_chars += len(content)

            # 实时打印累计接收的字符数（你也可以 print(content, end='', flush=True) 看内容）
            print(f"\rReceived: {total_chars} chars", end="", flush=True)

        print()  # 换行
        logger.info(f"Final analysis response:\n{full_response}")
        return full_response

    except Exception as e:
        logger.error(f"Error during k-bar data analysis: {e}")
        return None


def analyze_kbar_data(csv_file_path: Path, base_info: dict) -> Optional[str]:
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
                    "content": f"股票基本信息：{base_info}。",
                },
                {
                    "role": "system",
                    "content": f"fileid://{file_object.id}",
                },
                {
                    "role": "user",
                    "content": f"fileid://{file_object.id}",
                },
            ]
        )
        logger.info(f"Received analysis response from QianWen API: \n{completion.choices[0].message.content}")
        return completion.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Error during k-bar data analysis: {e}")
        return None