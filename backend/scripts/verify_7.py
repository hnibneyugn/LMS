"""Live check of #7 admin invite endpoints against the real API + Supabase Auth.

Mints an ADMIN session, invites a throwaway email through /api/admin/invite,
confirms the user now exists with password_set=false, checks the duplicate 409
and that the member list includes it, then DELETES the throwaway user so the
project returns to its original state.

The non-admin 403 boundary is covered by pytest (test_admin_api.py) — minting a
second real non-admin Supabase session would need a second password-set account.

Usage: PYTHONIOENCODING=utf-8 python scripts/verify_7.py
Requires the API on http://localhost:8000 and SUPABASE_URL +
SUPABASE_SERVICE_ROLE_KEY + ADMIN_EMAIL in backend/.env.
"""

import os
import sys
import uuid

import httpx
from dotenv import load_dotenv

from verify_1b import mint_access_token

load_dotenv()

API = "http://localhost:8000"


def _svc_headers(service_key):
    return {"apikey": service_key, "Authorization": f"Bearer {service_key}"}


def _find_user(base, service_key, email):
    res = httpx.get(
        f"{base}/auth/v1/admin/users",
        headers=_svc_headers(service_key),
        params={"page": 1, "per_page": 200},
        timeout=30,
    )
    res.raise_for_status()
    for u in res.json().get("users", []):
        if (u.get("email") or "").lower() == email:
            return u
    return None


def main() -> int:
    token = mint_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    base = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    throwaway = f"verify7-{uuid.uuid4().hex[:8]}@example.com"
    created_id = None
    try:
        # Invite through the real endpoint.
        r = httpx.post(f"{API}/api/admin/invite", headers=headers,
                       json={"email": throwaway}, timeout=30)
        print("invite:", r.status_code, r.text)
        assert r.status_code == 201, r.text
        assert r.json()["password_set"] is False

        # Confirm via Admin API + capture id for cleanup.
        user = _find_user(base, service_key, throwaway)
        assert user is not None, "invited user should exist"
        created_id = user["id"]
        assert (user.get("user_metadata") or {}).get("password_set") is False

        # Duplicate invite -> 409.
        dup = httpx.post(f"{API}/api/admin/invite", headers=headers,
                         json={"email": throwaway}, timeout=30)
        print("duplicate:", dup.status_code)
        assert dup.status_code == 409, dup.text

        # Member list includes it.
        members = httpx.get(f"{API}/api/admin/members", headers=headers, timeout=30).json()
        emails = {m["email"] for m in members}
        assert throwaway in emails, "member list should include the invited email"

        print("\nALL CHECKS PASSED")
        return 0
    finally:
        # Clean up: delete the throwaway user so nothing is left behind.
        if created_id is None:
            user = _find_user(base, service_key, throwaway)
            created_id = user["id"] if user else None
        if created_id:
            httpx.request("DELETE", f"{base}/auth/v1/admin/users/{created_id}",
                          headers=_svc_headers(service_key), timeout=30)
            print(f"cleaned up throwaway user {throwaway}")


if __name__ == "__main__":
    sys.exit(main())
