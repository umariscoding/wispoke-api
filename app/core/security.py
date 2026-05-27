"""
Security utilities — password hashing (bcrypt) and JWT token management.

This is shared infrastructure used by multiple features.
"""

import jwt as _jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from passlib.context import CryptContext

from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return _pwd_context.hash(password)


# ---------------------------------------------------------------------------
# JWT — config
# ---------------------------------------------------------------------------

_SECRET = settings.jwt_secret_key
_ALGORITHM = settings.jwt_algorithm
_ACCESS_TTL = settings.access_token_expire_minutes
_REFRESH_TTL = settings.refresh_token_expire_days


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# JWT — token creation
# ---------------------------------------------------------------------------

def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": _now() + (expires_delta or timedelta(minutes=_ACCESS_TTL)), "type": "access"})
    return _jwt.encode(to_encode, _SECRET, algorithm=_ALGORITHM)


def create_refresh_token(data: Dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": _now() + timedelta(days=_REFRESH_TTL), "type": "refresh"})
    return _jwt.encode(to_encode, _SECRET, algorithm=_ALGORITHM)


def create_company_tokens(company_id: str, email: str) -> Dict[str, str]:
    payload = {"sub": company_id, "email": email, "user_type": "company"}
    return {"access_token": create_access_token(payload), "refresh_token": create_refresh_token(payload), "token_type": "bearer"}


def create_user_tokens(user_id: str, company_id: str, email: Optional[str] = None) -> Dict[str, str]:
    payload = {"sub": user_id, "company_id": company_id, "email": email, "user_type": "user"}
    return {"access_token": create_access_token(payload), "refresh_token": create_refresh_token(payload), "token_type": "bearer"}


def create_guest_tokens(session_id: str, company_id: str) -> Dict[str, str]:
    payload = {"sub": session_id, "company_id": company_id, "user_type": "guest"}
    return {"access_token": create_access_token(payload), "refresh_token": create_refresh_token(payload), "token_type": "bearer"}


# ---------------------------------------------------------------------------
# JWT — verification / decoding
# ---------------------------------------------------------------------------

def verify_token(token: str) -> Optional[Dict]:
    try:
        return _jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except _jwt.PyJWTError:
        return None


def decode_token(token: str) -> Optional[Dict]:
    try:
        return _jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except _jwt.PyJWTError:
        return None


def refresh_access_token(refresh_token: str) -> Optional[str]:
    payload = verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return None
    user_type = payload.get("user_type")
    if user_type == "company":
        new_data = {"sub": payload["sub"], "email": payload.get("email"), "user_type": user_type}
    else:
        new_data = {"sub": payload["sub"], "company_id": payload.get("company_id"), "email": payload.get("email"), "user_type": user_type}
    return create_access_token(new_data)


# ---------------------------------------------------------------------------
# JWT — user info extraction
# ---------------------------------------------------------------------------

def get_current_user_info(token: str) -> Optional[Dict]:
    payload = decode_token(token)
    if not payload:
        return None
    user_type = payload.get("user_type")
    if user_type == "company":
        return {"company_id": payload["sub"], "email": payload.get("email"), "user_type": user_type}
    if user_type in ("user", "guest"):
        return {"user_id": payload["sub"], "company_id": payload.get("company_id"), "email": payload.get("email"), "user_type": user_type}
    return None


def is_company_token(token: str) -> bool:
    p = decode_token(token)
    return p is not None and p.get("user_type") == "company"


def is_user_token(token: str) -> bool:
    p = decode_token(token)
    return p is not None and p.get("user_type") == "user"


def is_guest_token(token: str) -> bool:
    p = decode_token(token)
    return p is not None and p.get("user_type") == "guest"


# ---------------------------------------------------------------------------
# Service-to-service tokens (voice worker → API)
#
# Kept on a *separate* secret from user tokens so leaking one doesn't
# compromise the other and so we can rotate them independently. The worker
# mints these short-lived (default 5 min) and attaches to every callback
# into /voice/internal/*.
# ---------------------------------------------------------------------------

_SERVICE_TOKEN_TYPE = "service"  # value of `type` claim


def _service_secret() -> str:
    secret = settings.voice_service_jwt_secret
    if not secret:
        # Fail loudly — silently falling back to the user JWT secret would
        # collapse the security boundary the two-secret design exists to enforce.
        raise RuntimeError(
            "VOICE_SERVICE_JWT_SECRET is not configured. Generate one with "
            "`python -c \"import secrets; print(secrets.token_hex(32))\"` "
            "and set it in your .env file."
        )
    return secret


def create_service_token(
    *,
    scope: str,
    company_id: Optional[str] = None,
    ttl_minutes: int = 5,
) -> str:
    """Mint a service token for worker → API callbacks.

    `scope` narrows what the token can do (e.g. "voice:internal"). Verification
    rejects tokens with a mismatched scope so a token minted for one purpose
    can't be replayed against an endpoint it wasn't intended for.
    """
    payload: Dict = {
        "type": _SERVICE_TOKEN_TYPE,
        "scope": scope,
        "exp": _now() + timedelta(minutes=ttl_minutes),
    }
    if company_id is not None:
        payload["company_id"] = company_id
    return _jwt.encode(payload, _service_secret(), algorithm=_ALGORITHM)


def verify_service_token(token: str, *, required_scope: str) -> Optional[Dict]:
    """Decode and validate a service token.

    Returns the payload on success, None on any failure (bad signature,
    expired, wrong scope, wrong type). Callers should treat None as 401.
    """
    try:
        payload = _jwt.decode(token, _service_secret(), algorithms=[_ALGORITHM])
    except _jwt.PyJWTError:
        return None
    if payload.get("type") != _SERVICE_TOKEN_TYPE:
        return None
    if payload.get("scope") != required_scope:
        return None
    return payload
