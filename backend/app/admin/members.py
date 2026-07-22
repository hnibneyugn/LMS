"""Supabase Admin API calls for member invites (#7).

Kept out of the router so the router stays thin. Mirrors the proven payload in
scripts/invite_user.py: create the auth user with no password, email_confirm
true, and password_set false so the login page forces them to set one.

Uses the service-role key (bypasses RLS) — backend only.
"""

import httpx

from app.config import settings


class AlreadyMemberError(Exception):
    """Email is already a member — surfaced to the caller as a 409."""


class InviteError(Exception):
    """Supabase/Admin API failed — surfaced as a 502 (graceful degradation)."""


def _base_and_headers() -> tuple[str, dict]:
    base = settings.supabase_url()
    key = settings.supabase_service_role_key()
    return base, {"apikey": key, "Authorization": f"Bearer {key}"}


def _summarize(user: dict) -> dict:
    """Only the fields the UI needs — never leak ids/tokens."""
    meta = user.get("user_metadata") or {}
    return {
        "email": (user.get("email") or "").lower(),
        "password_set": bool(meta.get("password_set", False)),
        "created_at": user.get("created_at"),
    }


def _fetch_users() -> list[dict]:
    base, headers = _base_and_headers()
    res = httpx.get(
        f"{base}/auth/v1/admin/users",
        headers=headers,
        params={"page": 1, "per_page": 200},
        timeout=30,
    )
    res.raise_for_status()
    return res.json().get("users", [])


def list_members() -> list[dict]:
    return [_summarize(u) for u in _fetch_users()]


def find_member(email: str) -> dict | None:
    wanted = email.strip().lower()
    return next(
        (u for u in _fetch_users() if (u.get("email") or "").lower() == wanted), None
    )


def invite_member(email: str) -> dict:
    email = email.strip().lower()
    try:
        existing = find_member(email)
    except httpx.HTTPError as err:
        raise InviteError("Không mời được lúc này, thử lại sau.") from err
    if existing is not None:
        raise AlreadyMemberError(f"{email} đã là thành viên rồi.")

    base, headers = _base_and_headers()
    try:
        res = httpx.post(
            f"{base}/auth/v1/admin/users",
            headers=headers,
            json={
                "email": email,
                "email_confirm": True,
                "user_metadata": {"password_set": False},
            },
            timeout=30,
        )
    except httpx.HTTPError as err:
        raise InviteError("Không mời được lúc này, thử lại sau.") from err
    if res.status_code not in (200, 201):
        raise InviteError("Không mời được lúc này, thử lại sau.")
    return _summarize(res.json())
