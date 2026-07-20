"""Set a password for an already-invited member.

Members are created by invite (magic link), so they have no password until
someone sets one. This does that through Supabase's admin API.

It refuses to create users: the account must already exist. That keeps the
invite-only rule intact -- this script is a convenience for people who are
already members, never a way in for anyone else.

Usage:
    python scripts/set_password.py <email>            # prompts, input hidden
    python scripts/set_password.py <email> <password> # non-interactive

Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the environment.
The service-role key bypasses everything -- never run this anywhere but your
own machine, and never paste the key into a shell that logs history.
"""

import getpass
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

MIN_PASSWORD_CHARS = 8


def find_user(base: str, headers: dict, email: str) -> dict | None:
    """Look the member up by email. Returns None if they were never invited."""
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

    email = sys.argv[1]
    base = os.environ["SUPABASE_URL"]
    headers = {
        "apikey": os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        "Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_ROLE_KEY']}",
    }

    user = find_user(base, headers, email)
    if user is None:
        print(f"Không tìm thấy thành viên với email {email}.")
        print("Người này chưa được mời — mời trước rồi mới đặt được mật khẩu.")
        return 1

    if len(sys.argv) >= 3:
        password = sys.argv[2]
    else:
        password = getpass.getpass("Mật khẩu mới: ")
        if password != getpass.getpass("Nhập lại: "):
            print("Hai lần nhập không khớp.")
            return 1

    if len(password) < MIN_PASSWORD_CHARS:
        print(f"Mật khẩu phải dài ít nhất {MIN_PASSWORD_CHARS} ký tự.")
        return 1

    res = httpx.put(
        f"{base}/auth/v1/admin/users/{user['id']}",
        headers=headers,
        json={
            "password": password,
            # Mark it set, or the login page would still corner them into
            # choosing a password the next time they use an email code.
            # Merged with whatever metadata they already carry.
            "user_metadata": {**(user.get("user_metadata") or {}), "password_set": True},
        },
        timeout=30,
    )
    if res.status_code != 200:
        print(f"Đặt mật khẩu thất bại: {res.status_code} {res.text[:300]}")
        return 1

    print(f"Đã đặt mật khẩu cho {email}. Đăng nhập được ngay, không cần mở mail.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
