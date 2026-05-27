"""
Service-token authentication for /voice/internal/*.

The worker mints a short-lived JWT signed with VOICE_SERVICE_JWT_SECRET and
sends it as `Authorization: Bearer <token>`. We verify both the signature and
the scope claim — leaking the secret would still only unlock voice-internal,
not user-facing endpoints.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import verify_service_token

VOICE_INTERNAL_SCOPE = "voice:internal"

_security = HTTPBearer(auto_error=True)


def require_service_token(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """Verify a service token and return the decoded payload.

    Raises 401 on any failure. The endpoint can read `payload["company_id"]`
    when the token was minted with one (the worker scopes tokens to the tenant
    they're serving so the API can sanity-check path/body company_id matches).
    """
    payload = verify_service_token(credentials.credentials, required_scope=VOICE_INTERNAL_SCOPE)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired service token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
