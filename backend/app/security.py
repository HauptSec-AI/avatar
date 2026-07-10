"""Admin session cookie: signed with itsdangerous, guards all /admin/* APIs."""

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from . import config

SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

_serializer = URLSafeTimedSerializer(config.SESSION_SECRET, salt="avatar-admin-session")


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
