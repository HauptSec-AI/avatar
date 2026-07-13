"""Admin session cookie: signed with itsdangerous, guards all /admin/* APIs."""

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import config

SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
VOICE_SESSION_NONCE_MAX_AGE = 60 * 10  # 10 minutes -- covers mic prompt + WebRTC handshake

_serializer = URLSafeTimedSerializer(config.SESSION_SECRET, salt="avatar-admin-session")
_voice_session_serializer = URLSafeTimedSerializer(
    config.SESSION_SECRET, salt="avatar-voice-session-nonce"
)


def create_session_token() -> str:
    return _serializer.dumps({"admin": True})


def verify_session_token(token: str) -> bool:
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return bool(data.get("admin"))


def require_admin(request: Request) -> None:
    token = request.cookies.get(config.ADMIN_SESSION_COOKIE)
    if not token or not verify_session_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def mint_voice_session_nonce(conversation_id: str) -> str:
    """Proves the caller is the same browser that just minted a rate-limited
    /api/voice/session credential for this exact conversation_id. Required by
    /api/voice/session/started so an attacker can't bind an arbitrary victim's
    conversation_id to their own live ElevenLabs call (see SPEC-VOICE.md's
    session-mapping table)."""
    return _voice_session_serializer.dumps({"conversation_id": conversation_id})


def verify_voice_session_nonce(nonce: str, conversation_id: str) -> bool:
    try:
        data = _voice_session_serializer.loads(nonce, max_age=VOICE_SESSION_NONCE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return data.get("conversation_id") == conversation_id


def require_voice_tool_secret(request: Request) -> None:
    """Guards /api/voice/tools/*: these trigger real side effects (a Pushover push),
    so they're not left open to anyone who finds the URL. ELEVENLABS_WEBHOOK_SECRET
    doubles as this shared secret -- configure the same value as a custom auth header
    on both webhook tools in the ElevenLabs agent config (see sync_voice_agent.py)."""
    if not config.ELEVENLABS_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Voice not configured")
    expected = f"Bearer {config.ELEVENLABS_WEBHOOK_SECRET}"
    if request.headers.get("authorization") != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
