"""In-memory moving-window rate limit: 20 chat messages/minute per conversation_id.

In-memory is sufficient (see SPEC): OpenRouter caps overall spend, and a browser's
requests all land on one process.
"""

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from . import config

_storage = MemoryStorage()
_limiter = MovingWindowRateLimiter(_storage)
_rate = parse(config.RATE_LIMIT)
_voice_rate = parse(config.VOICE_SESSION_RATE_LIMIT)


def allow_chat_message(conversation_id: str) -> bool:
    return _limiter.hit(_rate, "chat", conversation_id)


def allow_voice_session(conversation_id: str) -> bool:
    return _limiter.hit(_voice_rate, "voice", conversation_id)
