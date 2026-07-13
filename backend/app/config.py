"""Environment configuration, loaded once from the project-root .env."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("avatar")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=True)


def _derive_secret(explicit: str, fallback: str, name: str, reason: str) -> str:
    """Returns `explicit` if set; otherwise falls back to `fallback` and logs a
    warning (once, at import time) so a silently-derived secret doesn't go
    unnoticed in production."""
    if explicit:
        return explicit
    logger.warning("%s is not set -- %s", name, reason)
    return fallback


OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.environ.get("MODEL", "openai/gpt-5.4-nano")
OWNER_NAME = os.environ.get("OWNER_NAME", "Avatar")
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
PUSHOVER_USER = os.environ.get("PUSHOVER_USER", "")
PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN", "")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SESSION_SECRET = _derive_secret(
    os.environ.get("SESSION_SECRET", ""),
    f"avatar::{ADMIN_PASSWORD}",
    "SESSION_SECRET",
    "deriving it from ADMIN_PASSWORD instead. Set an explicit value for production so "
    "rotating ADMIN_PASSWORD doesn't also invalidate every admin session.",
)
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

# Voice (SPEC-VOICE.md) -- all optional. The app runs fine without voice configured;
# the /api/voice/* routes return a clear error until these are set.
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_AGENT_ID = os.environ.get("ELEVENLABS_AGENT_ID", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
# Signs/verifies the post-call transcript webhook's HMAC signature -- ONLY that.
ELEVENLABS_WEBHOOK_SECRET = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "")
# Bearer token the two tool webhooks (faq_tool/push_tool) check -- a separate secret
# from the HMAC key above, so a leak of one doesn't compromise the other. Falls back
# to ELEVENLABS_WEBHOOK_SECRET (with a warning) only when voice is otherwise
# configured, so text-only deployments that never set either stay silent.
ELEVENLABS_TOOL_SECRET = os.environ.get("ELEVENLABS_TOOL_SECRET", "")
if not ELEVENLABS_TOOL_SECRET and ELEVENLABS_WEBHOOK_SECRET:
    ELEVENLABS_TOOL_SECRET = _derive_secret(
        "",
        ELEVENLABS_WEBHOOK_SECRET,
        "ELEVENLABS_TOOL_SECRET",
        "falling back to ELEVENLABS_WEBHOOK_SECRET for the voice tool webhooks' bearer "
        "auth too. Set a separate ELEVENLABS_TOOL_SECRET so the webhook HMAC key and the "
        "tool bearer token aren't the same value.",
    )
VOICE_MAX_SESSION_SECONDS = int(os.environ.get("VOICE_MAX_SESSION_SECONDS", "600"))
# ElevenLabs-managed LLM for voice, independent of MODEL/OPENROUTER_API_KEY (text chat).
# Custom LLM (routing voice through OpenRouter, like text) isn't allowed on agents using
# an Instant Voice Clone -- discovered via a live 400 from ElevenLabs' own API -- so voice
# uses one of ElevenLabs' managed models instead. Switch this if you have a Professional
# Voice Clone and want voice on OpenRouter too (see SPEC-VOICE.md).
ELEVENLABS_LLM = os.environ.get("ELEVENLABS_LLM", "gpt-4o-mini")

KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

MAX_MESSAGE_CHARS = 20_000
TRUNCATION_NOTE = (
    "\n\n[...message truncated as it's too long; "
    "ask the visitor to send something more concise]"
)
RATE_LIMIT = "20/minute"
VOICE_SESSION_RATE_LIMIT = "5/minute"  # a voice session is far heavier than one chat message
VOICE_SESSION_STARTED_RATE_LIMIT = "10/minute"  # generous -- the frontend fires this once per call
ADMIN_LOGIN_RATE_LIMIT = "10/minute"  # per client IP -- blocks rapid-fire password guessing
ADMIN_LOGIN_LOCKOUT_LIMIT = "5/15minute"  # per client IP, failures only -- blocks slow-drip guessing
# Coarse GLOBAL (not per-conversation_id) cap on push_tool notifications: a script
# minting a fresh conversation_id per request would otherwise dodge the 20/minute
# per-conversation chat limit and flood Pushover.
PUSH_TOOL_RATE_LIMIT = "10/hour"
MAX_MESSAGE_BODY_CHARS = 100_000  # hard cap on the raw field so an oversized body is
# rejected outright rather than silently buffered in full before the 20k clamp runs
MAX_REQUEST_BODY_BYTES = 2_000_000  # ~2MB global ceiling across every route (defense in
# depth for routes with no per-field max_length, e.g. the voice webhook's raw body)
VOICE_WEBHOOK_RATE_LIMIT = "30/minute"  # per client IP -- generous for legit ElevenLabs
# retries, caps an unauthenticated caller from hammering the signature check

ADMIN_SESSION_COOKIE = "avatar_admin_session"
