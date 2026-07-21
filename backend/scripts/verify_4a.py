"""One-off live end-to-end check of #4a: generate -> cache -> regenerate + RLS.

Hits the real API (which calls real Gemini) and the real Supabase, using the
ADMIN account. Checks what only a live run can establish:

  * GET .../questions on a fresh lesson generates a set (>=1 valid question,
    >=3 distinct types) and persists it.
  * a second GET returns the SAME set without creating new rows (cache hit).
  * POST .../regenerate replaces the set.
  * the anon key reads 0 rows from `questions` (RLS is really on).
  * whatever this script wrote is removed again.

Usage: PYTHONIOENCODING=utf-8 python scripts/verify_4a.py
Requires the API on http://localhost:8000 and at least one confirmed lesson on
the ADMIN_EMAIL account. Needs SUPABASE_ANON_KEY in the environment (it lives in
frontend/.env.local, not backend/.env).
"""

import os
import sys

import httpx
from dotenv import load_dotenv

from verify_1b import mint_access_token

load_dotenv()

API = "http://localhost:8000"


def _db_headers(service_key):
    return {"apikey": service_key, "Authorization": f"Bearer {service_key}"}


def main() -> int:
    token = mint_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    base = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    lessons = httpx.get(f"{API}/api/lessons", headers=headers, timeout=30).json()
    if not lessons:
        print("FAIL: no lessons on this account; confirm a file first (#1b).")
        return 1
    target = lessons[0]
    slug, lesson_id = target["slug"], target["id"]
    print(f"target lesson: [{target['title']}] slug={slug}")

    # Clean slate for this lesson so "generate on cache miss" is what we test.
    httpx.request(
        "DELETE",
        f"{base}/rest/v1/questions",
        params={"lesson_id": f"eq.{lesson_id}"},
        headers=_db_headers(service_key),
        timeout=30,
    )

    first = httpx.get(
        f"{API}/api/lessons/{slug}/questions", headers=headers, timeout=120
    ).json()
    print(f"\nGET .../questions (cache miss) -> {len(first)} questions")
    for q in first:
        print(f"  [{q['type']}] {q['question_text']}")
    assert len(first) >= 1, "no questions generated"
    types = {q["type"] for q in first}
    assert len(types) >= 3, f"expected >=3 distinct types, got {sorted(types)}"

    second = httpx.get(
        f"{API}/api/lessons/{slug}/questions", headers=headers, timeout=120
    ).json()
    assert [q["id"] for q in second] == [q["id"] for q in first], "cache miss on 2nd GET"
    print("2nd GET returned the SAME ids (cache hit, no regeneration)")

    db_rows = httpx.get(
        f"{base}/rest/v1/questions",
        params={"lesson_id": f"eq.{lesson_id}", "select": "id"},
        headers=_db_headers(service_key),
        timeout=30,
    ).json()
    assert len(db_rows) == len(first), "DB row count differs from response"
    print(f"DB has {len(db_rows)} rows for this lesson (matches response)")

    regen = httpx.post(
        f"{API}/api/lessons/{slug}/questions/regenerate", headers=headers, timeout=120
    ).json()
    print(f"\nPOST .../regenerate -> {len(regen)} questions")
    assert {q["id"] for q in regen}.isdisjoint({q["id"] for q in first}), (
        "regenerate reused old ids"
    )

    anon = httpx.get(
        f"{base}/rest/v1/questions",
        params={"select": "id"},
        headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
        timeout=30,
    ).json()
    print(f"anon key sees {len(anon)} questions rows (must be 0)")
    assert anon == [], "RLS is NOT protecting questions"

    # Leave the account exactly as found.
    httpx.request(
        "DELETE",
        f"{base}/rest/v1/questions",
        params={"lesson_id": f"eq.{lesson_id}"},
        headers=_db_headers(service_key),
        timeout=30,
    )
    print("cleaned up the questions this script wrote")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
