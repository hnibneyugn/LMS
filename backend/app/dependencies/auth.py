import functools
import os
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings


@dataclass
class CurrentUser:
    user_id: str
    email: str | None


@functools.lru_cache(maxsize=None)
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    # Cached per URL so the underlying signing-key cache (and the HTTP
    # fetches it saves us from repeating) survives across requests.
    return jwt.PyJWKClient(jwks_url)


def _get_signing_key(token: str):
    """Look up the public signing key for `token` from the project's JWKS.

    Kept as a standalone function (rather than inlined in `_decode`) so tests
    can monkeypatch it to return a locally generated public key, avoiding any
    network call to a real JWKS endpoint.
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    if not supabase_url:
        # Missing config is a server error, not a client error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_URL is not configured",
        )
    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    client = _jwks_client(jwks_url)
    return client.get_signing_key_from_jwt(token).key


def _decode(token: str) -> dict:
    try:
        signing_key = _get_signing_key(token)
        return jwt.decode(
            token, signing_key, algorithms=["ES256"], audience="authenticated"
        )
    except HTTPException:
        # Server misconfig (missing SUPABASE_URL) — propagate as-is, not a 401.
        raise
    except (jwt.PyJWTError, jwt.PyJWKClientError) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from err


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    token = authorization.removeprefix("Bearer ").strip()
    payload = _decode(token)
    return CurrentUser(user_id=payload["sub"], email=payload.get("email"))


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Allow only the configured ADMIN_EMAIL. The real authorization boundary
    for every /api/admin/* route — never trust the frontend for this."""
    admin = settings.admin_email().strip().lower()
    if not user.email or user.email.strip().lower() != admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ admin mới được phép."
        )
    return user
