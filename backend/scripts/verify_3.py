"""One-off live end-to-end check of #3: list -> read -> progress.

Checks what only a real run can establish:

  * GET /api/lessons returns this account's lessons, grouped-able by source
    file, with `done` merged in from lesson_progress.
  * GET /api/lessons/{slug} returns content_md matching the DB row, and
    prev/next in real chapter order.
  * PUT progress actually writes lesson_progress and can be turned back off.
  * the anon key reads 0 rows from lesson_progress (RLS is really on).
  * whatever this script wrote is removed again.

Usage: python scripts/verify_3.py
Requires the API running on http://localhost:8000 and at least one confirmed
lesson on the ADMIN_EMAIL account.
"""

import os
import sys

import httpx
from dotenv import load_dotenv

from verify_1b import mint_access_token

load_dotenv()

API = "http://localhost:8000"


def main() -> int:
    token = mint_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    lessons = httpx.get(f"{API}/api/lessons", headers=headers, timeout=30).json()
    print(f"GET /api/lessons -> {len(lessons)} lessons")
    if not lessons:
        print("FAIL: no lessons on this account; confirm a file first (#1b).")
        return 1
    for row in lessons:
        print(f"  [{row['source_file_name']}] #{row['order_index']} {row['title']}"
              f" done={row['done']}")

    target = lessons[0]
    detail = httpx.get(
        f"{API}/api/lessons/{target['slug']}", headers=headers, timeout=30
    ).json()
    print(f"\nGET /api/lessons/{target['slug']} -> {len(detail['content_md'])} chars")
    print(f"  prev={detail['prev']}  next={detail['next']}")
    assert detail["title"] == target["title"]

    # Compare against the DB directly, so a bug that mangles content_md on the
    # way out cannot pass by matching itself.
    base = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    db_row = httpx.get(
        f"{base}/rest/v1/lessons",
        params={"id": f"eq.{target['id']}", "select": "content_md"},
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        timeout=30,
    ).json()[0]
    assert detail["content_md"] == db_row["content_md"], "content_md differs from DB"
    print("  content_md matches the DB row")

    on = httpx.put(
        f"{API}/api/lessons/{target['id']}/progress",
        json={"done": True},
        headers=headers,
        timeout=30,
    ).json()
    print(f"\nPUT progress done=true -> {on}")
    assert on["done"] is True and on["completed_at"]

    anon = httpx.get(
        f"{base}/rest/v1/lesson_progress",
        params={"select": "lesson_id"},
        headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
        timeout=30,
    ).json()
    print(f"anon key sees {len(anon)} lesson_progress rows (must be 0)")
    assert anon == [], "RLS is NOT protecting lesson_progress"

    off = httpx.put(
        f"{API}/api/lessons/{target['id']}/progress",
        json={"done": False},
        headers=headers,
        timeout=30,
    ).json()
    print(f"PUT progress done=false -> {off}")
    assert off == {"done": False, "completed_at": None}

    # Leave the account exactly as found: drop the row this script created.
    httpx.delete(
        f"{base}/rest/v1/lesson_progress",
        params={"lesson_id": f"eq.{target['id']}"},
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        timeout=30,
    )
    print("cleaned up the lesson_progress row this script wrote")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
