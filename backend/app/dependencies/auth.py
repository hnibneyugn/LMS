import os
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException, status


@dataclass
class CurrentUser:
    user_id: str
    email: str | None


def _decode(token: str) -> dict:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        # Missing config is a server error, not a client error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_JWT_SECRET is not configured",
        )
    try:
        return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
    except jwt.PyJWTError as err:
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
