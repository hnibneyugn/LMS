"""Live check of #6 dashboard endpoints against the real API + Supabase.

Seeds one daily_activity row for the ADMIN user (VN today), asserts /me reflects
it (streak >= 1, 7-day chart, completion math) and /leaderboard flags the user,
then removes the seeded row.

Usage: PYTHONIOENCODING=utf-8 python scripts/verify_6.py
Requires the API on http://localhost:8000 and SUPABASE_ANON_KEY in the env
(it lives in frontend/.env.local); SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in backend/.env.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from verify_1b import mint_access_token

load_dotenv()

API = "http://localhost:8000"
VN_TZ = timezone(timedelta(hours=7))


def _svc_headers(service_key):
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }


def main() -> int:
    token = mint_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    base = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    # Resolve the admin user_id from /api/me.
    me_auth = httpx.get(f"{API}/api/me", headers=headers, timeout=30).json()
    user_id = me_auth["user_id"] if "user_id" in me_auth else me_auth["sub"]
    today = datetime.now(VN_TZ).date().isoformat()

    # Snapshot any existing daily_activity row for VN today so we can restore it
    # exactly (the account may be mid-use); we upsert a known value, then restore.
    existing = httpx.get(
        f"{base}/rest/v1/daily_activity",
        params={
            "select": "questions_done_count",
            "user_id": f"eq.{user_id}",
            "activity_date": f"eq.{today}",
        },
        headers=_svc_headers(service_key),
        timeout=30,
    ).json()
    prior_count = existing[0]["questions_done_count"] if existing else None

    # Seed one daily_activity row for VN today.
    seeded = httpx.post(
        f"{base}/rest/v1/daily_activity",
        headers=_svc_headers(service_key),
        json={"user_id": user_id, "activity_date": today, "questions_done_count": 3},
        timeout=30,
    )
    assert seeded.status_code in (200, 201), seeded.text

    me = httpx.get(f"{API}/api/dashboard/me", headers=headers, timeout=30).json()
    print("me:", me)
    assert me["current_streak"] >= 1, "today was seeded, streak must be >= 1"
    assert len(me["weekly_questions"]) == 7
    assert me["weekly_questions"][-1]["date"] == today
    assert me["weekly_questions"][-1]["count"] >= 3
    assert 0 <= me["completion_pct"] <= 100

    board = httpx.get(f"{API}/api/dashboard/leaderboard", headers=headers, timeout=30).json()
    mine = [r for r in board if r["is_me"]]
    print(f"leaderboard rows: {len(board)}; my row: {mine}")
    assert len(mine) == 1, "exactly one row should be flagged is_me"
    assert mine[0]["active_days"] >= 1

    # Restore prior state: either put back the original count, or delete the row
    # this script created.
    if prior_count is None:
        httpx.request(
            "DELETE",
            f"{base}/rest/v1/daily_activity",
            params={"user_id": f"eq.{user_id}", "activity_date": f"eq.{today}"},
            headers=_svc_headers(service_key),
            timeout=30,
        )
        print("cleaned up the seeded daily_activity row")
    else:
        httpx.post(
            f"{base}/rest/v1/daily_activity",
            headers=_svc_headers(service_key),
            json={
                "user_id": user_id,
                "activity_date": today,
                "questions_done_count": prior_count,
            },
            timeout=30,
        )
        print(f"restored prior daily_activity count ({prior_count})")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
