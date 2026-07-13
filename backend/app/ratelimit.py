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
_admin_login_rate = parse(config.ADMIN_LOGIN_RATE_LIMIT)
_admin_login_lockout_rate = parse(config.ADMIN_LOGIN_LOCKOUT_LIMIT)


def allow_chat_message(conversation_id: str) -> bool:
    return _limiter.hit(_rate, "chat", conversation_id)


def allow_voice_session(conversation_id: str) -> bool:
    return _limiter.hit(_voice_rate, "voice", conversation_id)


def allow_admin_login_attempt(client_ip: str) -> bool:
    """Gate checked before the password comparison. The fast window is hit on every
    attempt (blocks rapid-fire guessing); the lockout window is only tested here --
    it's only incremented by record_admin_login_failure, so correct guesses never
    count against it, but repeated failures lock out further attempts (even with the
    right password) until the window rolls off or reset_admin_login_lockout runs."""
    return _limiter.hit(_admin_login_rate, "admin_login", client_ip) and _limiter.test(
        _admin_login_lockout_rate, "admin_login_lockout", client_ip
    )


def record_admin_login_failure(client_ip: str) -> None:
    _limiter.hit(_admin_login_lockout_rate, "admin_login_lockout", client_ip)


def reset_admin_login_lockout(client_ip: str) -> None:
    _limiter.clear(_admin_login_lockout_rate, "admin_login_lockout", client_ip)
