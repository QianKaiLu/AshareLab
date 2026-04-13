from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

from ai.ai_api_profile import ApiProfile, QWEN_MAX
from tools.log import get_analyze_logger

logger = get_analyze_logger()


@dataclass
class ChatConfig:
    stream: bool = True
    thinking: bool = False
    print_output: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class ChatResult:
    content: str = ""
    thinking_content: Optional[str] = None
    model: str = ""
    usage: Optional[dict] = None
    finish_reason: str = ""


def chat(
    prompt: str,
    contents: Optional[list[str]] = None,
    profile: Optional[ApiProfile] = None,
    config: Optional[ChatConfig] = None,
) -> ChatResult:
    """
    Unified AI chat interface.

    Args:
        prompt: System message text.
        contents: List of strings, each becomes an independent user message.
        profile: API provider config. Defaults to QWEN_MAX().
        config: Runtime options (stream, thinking, print, etc.). Defaults to ChatConfig().

    Returns:
        ChatResult with content, optional thinking_content, model, usage, finish_reason.
    """
    if profile is None:
        profile = QWEN_MAX()
    if config is None:
        config = ChatConfig()

    if not profile.api_key:
        raise ValueError(f"{profile.name} API_KEY is not set in environment variables.")

    client = OpenAI(api_key=profile.api_key, base_url=profile.base_url)

    messages = [{"role": "system", "content": prompt}]
    for item in (contents or []):
        messages.append({"role": "user", "content": item})

    extra_params: dict = {}
    if config.temperature is not None:
        extra_params["temperature"] = config.temperature
    if config.max_tokens is not None:
        extra_params["max_tokens"] = config.max_tokens

    if config.stream:
        return _chat_stream(client, profile, messages, config, extra_params)
    else:
        return _chat_sync(client, profile, messages, config, extra_params)


def _chat_sync(
    client: OpenAI,
    profile: ApiProfile,
    messages: list[dict],
    config: ChatConfig,
    extra_params: dict,
) -> ChatResult:
    response = client.chat.completions.create(
        model=profile.model,
        messages=messages,
        stream=False,
        **extra_params,
    )
    choice = response.choices[0]
    usage = None
    if response.usage:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    thinking_content = None
    if config.thinking:
        reasoning = getattr(choice.message, "reasoning_content", None)
        if reasoning:
            thinking_content = reasoning

    return ChatResult(
        content=choice.message.content or "",
        thinking_content=thinking_content,
        model=response.model,
        usage=usage,
        finish_reason=choice.finish_reason or "",
    )


def _chat_stream(
    client: OpenAI,
    profile: ApiProfile,
    messages: list[dict],
    config: ChatConfig,
    extra_params: dict,
) -> ChatResult:
    completion = client.chat.completions.create(
        model=profile.model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        **extra_params,
    )

    content = ""
    thinking_content = ""
    model = ""
    usage = None
    finish_reason = ""

    for chunk in completion:
        if chunk.model:
            model = chunk.model

        if chunk.usage:
            usage = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "total_tokens": chunk.usage.total_tokens,
            }

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta

        if delta.content:
            content += delta.content
            if config.print_output:
                logger.info(f"\rReceived data length: {len(content):<10}", end="", flush=True)

        if config.thinking:
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                thinking_content += reasoning

        if chunk.choices[0].finish_reason:
            finish_reason = chunk.choices[0].finish_reason

    if config.print_output:
        logger.info("")

    return ChatResult(
        content=content,
        thinking_content=thinking_content if thinking_content else None,
        model=model,
        usage=usage,
        finish_reason=finish_reason,
    )
