import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from . import config

_serializer = URLSafeTimedSerializer(config.SECRET_KEY, salt="df-session")

SESSION_MAX_AGE_SECONDS = config.SESSION_TTL_DAYS * 24 * 60 * 60


def hash_password(raw_password: str) -> str:
    return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(raw_password.encode("utf-8"), password_hash.encode("utf-8"))


def create_session_token(user_id: str) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session_token(token: str) -> str | None:
    """Returns the user_id encoded in the token, or None if missing/expired/tampered."""
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return data.get("uid")
    except (BadSignature, SignatureExpired):
        return None
