from ai.config import QIANWEN_API_KEY
from openai import OpenAI
from pathlib import Path
from typing import Optional, Literal
from tools.log import get_analyze_logger
from ai.ai_api_profile import ApiProfile, QWEN_MAX, DEEPSEEK_REASONER
from ai.prompts.srt_prompts import ModeType, PROMPT_MAP

logger = get_analyze_logger()

API_PROFILE: ApiProfile = DEEPSEEK_REASONER()

client = OpenAI(
    api_key=API_PROFILE.api_key,
    base_url=API_PROFILE.base_url,
)

def summarize_srt(
    srt_file_path: Optional[Path] = None,
    srt_content: Optional[str] = None,
    mode: ModeType = "summary",
    extra_prompt: Optional[str] = None,
) -> Optional[str]:
    """
    Summarizes or converts SRT content to a mind map using the specified AI model.

    Args:
        srt_file_path (Optional[Path]): Path to the .srt file. Required if srt_content is not provided.
        srt_content (Optional[str]): Raw SRT content as a string. Takes precedence over srt_file_path.
        mode (Literal["summary", "xmind"]): Output mode. "summary" for detailed notes, "xmind" for outline.
        extra_prompt (Optional[str]): Additional instructions appended to the system prompt.

    Returns:
        Optional[str]: Generated markdown content, or None on error.
    """
    if not API_PROFILE.api_key:
        raise ValueError(f"{API_PROFILE.name} API_KEY is not set in environment variables.")

    if srt_content is not None:
        logger.info("Using provided srt_content string.")
    elif srt_file_path is not None:
        if not srt_file_path.exists():
            raise FileNotFoundError(f"SRT file not found: {srt_file_path}")
        try:
            srt_content = srt_file_path.read_text(encoding="utf-8")
            logger.info(f"Read SRT file content from {srt_file_path}")
        except Exception as e:
            logger.error(f"Failed to read SRT file: {e}")
            return None
    else:
        logger.error("Either srt_file_path or srt_content must be provided.")
        raise ValueError("Either srt_file_path or srt_content must be provided.")

    base_prompt = PROMPT_MAP[mode]

    system_prompt = base_prompt
    if extra_prompt:
        system_prompt = f"{base_prompt}\n\n附加要求：\n{extra_prompt}"

    try:
        completion = client.chat.completions.create(
            model=API_PROFILE.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"SRT 字幕内容：\n\n{srt_content}"},
            ],
            stream=True,
            stream_options={"include_usage": False}
        )

        output = ""
        received_length = 0
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                output += content
                received_length += len(content)
                print(f"\rReceived data length: {received_length:<10}", end="", flush=True)
        print()
        return output.strip()

    except Exception as e:
        logger.error(f"Error during SRT summarization: {e}")
        return None
