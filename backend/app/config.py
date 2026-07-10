"""Environment configuration, loaded once from the project-root .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=True)

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.environ.get("MODEL", "openai/gpt-5.4-nano")
OWNER_NAME = os.environ.get("OWNER_NAME", "Avatar")
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
PUSHOVER_USER = os.environ.get("PUSHOVER_USER", "")
PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN", "")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SESSION_SECRET = os.environ.get("SESSION_SECRET") or f"avatar::{ADMIN_PASSWORD}"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

# Voice (SPEC-VOICE.md) -- all optional. The app runs fine without voice configured;
# the /api/voice/* routes return a clear error until these are set.
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_AGENT_ID = os.environ.get("ELEVENLABS_AGENT_ID", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_WEBHOOK_SECRET = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "")
VOICE_MAX_SESSION_SECONDS = int(os.environ.get("VOICE_MAX_SESSION_SECONDS", "600"))

KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

MAX_MESSAGE_CHARS = 20_000
TRUNCATION_NOTE = (
    "\n\n[...message truncated as it's too long; "
    "ask the visitor to send something more concise]"
)
RATE_LIMIT = "20/minute"
VOICE_SESSION_RATE_LIMIT = "5/minute"  # a voice session is far heavier than one chat message

ADMIN_SESSION_COOKIE = "avatar_admin_session"
