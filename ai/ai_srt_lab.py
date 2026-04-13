from pathlib import Path
from typing import Optional

from ai.ai_api_profile import DEEPSEEK_REASONER
from ai.chat_service import chat, ChatConfig
from ai.prompts.srt_prompts import ModeType, PROMPT_MAP
from tools.log import get_analyze_logger

logger = get_analyze_logger()


def summarize_srt(
    srt_file_path: Optional[Path] = None,
    srt_content: Optional[str] = None,
    mode: ModeType = "summary",
    extra_prompt: Optional[str] = None,
) -> Optional[str]:
    """
    Summarizes or converts SRT content using the specified AI model.

    Args:
        srt_file_path: Path to the .srt file. Required if srt_content is not provided.
        srt_content: Raw SRT content as a string. Takes precedence over srt_file_path.
        mode: Output mode (summary, xmind, key_points, etc.).
        extra_prompt: Additional instructions appended to the system prompt.

    Returns:
        Generated markdown content, or None on error.
    """
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
        raise ValueError("Either srt_file_path or srt_content must be provided.")

    system_prompt = PROMPT_MAP[mode]
    if extra_prompt:
        system_prompt = f"{system_prompt}\n\n附加要求：\n{extra_prompt}"

    try:
        result = chat(
            prompt=system_prompt,
            contents=[f"SRT 字幕内容：\n\n{srt_content}"],
            profile=DEEPSEEK_REASONER(),
            config=ChatConfig(print_output=True),
        )
        return result.content.strip() if result.content else None

    except Exception as e:
        logger.error(f"Error during SRT summarization: {e}")
        return None
