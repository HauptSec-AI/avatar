"""The Avatar agent: OpenAI Agents SDK, routed through OpenRouter, with two tools."""

import asyncio
from functools import lru_cache

import requests
from agents import Agent, OpenAIChatCompletionsModel, function_tool, set_tracing_disabled
from openai import AsyncOpenAI

from . import config, ratelimit
from .knowledge import build_instructions, find_faq, format_faq_answer

# Tracing requires an OpenAI API key/account we don't have when routing through
# OpenRouter, so disable it (the SDK's documented approach for other providers).
set_tracing_disabled(True)

_openrouter_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=config.OPENROUTER_API_KEY,
)


@function_tool
def faq_tool(question_number: int) -> str:
    """Retrieve the full, original answer to a frequently asked question by its number.

    Args:
        question_number: The FAQ number to look up.
    """
    faq = find_faq(question_number)
    if not faq:
        return "That question number was not found in the FAQ."
    return format_faq_answer(faq)


def send_pushover_notification(message: str) -> str:
    if not config.PUSHOVER_USER or not config.PUSHOVER_TOKEN:
        return "Pushover is not configured; the message was not sent."
    if not ratelimit.allow_push_notification():
        # Coarse GLOBAL budget, not per-conversation_id -- a script minting a fresh
        # conversation_id per request would otherwise dodge the per-conversation
        # chat rate limit and flood Pushover (see PUSH_TOOL_RATE_LIMIT).
        return "The human has already been notified several times recently; please try again later."
    response = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={"user": config.PUSHOVER_USER, "token": config.PUSHOVER_TOKEN, "message": message},
        timeout=10,
    )
    return f"Message pushed with status code {response.status_code}."


@function_tool
async def push_tool(message: str) -> str:
    """Send the given message to the human (your human twin) as a Pushover notification.

    Args:
        message: The message to send to the human operator.
    """
    return await asyncio.to_thread(send_pushover_notification, message)


@lru_cache(maxsize=1)
def get_agent() -> Agent:
    model = OpenAIChatCompletionsModel(model=config.MODEL, openai_client=_openrouter_client)
    return Agent(
        name="Avatar",
        instructions=build_instructions(),
        tools=[faq_tool, push_tool],
        model=model,
    )
