"""Invite a new member.

Creates the auth account with NO password. The member then signs in with the
code emailed to them and is required to set a password on the way in (the
login page enforces that via the `password_set` flag this script clears).

Keeping invites here rather than in the app is deliberate for now: the group
is under ten people, and an admin-only invite page is its own sub-project
(#7). This is the smallest thing that lets someone else log in.

Usage:
    python scripts/invite_user.py <email>

Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the environment. The
service-role key bypasses every policy -- run this only on your own machine.
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()


def find_user(base: str, headers: dict, email: str) -> dict | None:
    res = httpx.get(
        f"{base}/auth/v1/admin/users",
        headers=headers,
        params={"page": 1, "per_page": 200},
        timeout=30,
    )
    res.raise_for_status()
    wanted = email.strip().lower()
    for user in res.json().get("users", []):
        if (user.get("email") or "").lower() == wanted:
            return user
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    email = sys.argv[1].strip().lower()
    base = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    if find_user(base, headers, email) is not None:
        print(f"{email} đã là thành viên rồi — không tạo lại.")
        return 1

    res = httpx.post(
        f"{base}/auth/v1/admin/users",
        headers=headers,
        json={
            "email": email,
            # Confirmed up front: the invite IS the vouching step, and leaving
            # it unconfirmed only adds a second email round trip before they
            # can request their first login code.
            "email_confirm": True,
            # No password field at all. The member sets their own on first
            # login; nobody -- including whoever runs this -- ever knows it.
            "user_metadata": {"password_set": False},
        },
        timeout=30,
    )
    if res.status_code not in (200, 201):
        print(f"Mời thất bại: {res.status_code} {res.text[:300]}")
        return 1

    print(f"Đã mời {email}.")
    print("Bảo họ vào trang đăng nhập, bấm 'Chưa có mật khẩu? Gửi mã qua email',")
    print("nhập mã trong hộp thư, rồi đặt mật khẩu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
