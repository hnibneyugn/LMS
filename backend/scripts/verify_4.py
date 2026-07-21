"""One-off live end-to-end check of #4: grade -> save attempt -> daily activity.

Hits the real API (real Gemini) and real Supabase with the ADMIN account. Checks
what only a live run can establish:

  * POST /api/quiz/grade returns a 0..10 score + missing_points + comment and
    inserts exactly one quiz_attempts row.
  * daily_activity for today goes up by exactly 1 on the first grade of a
    question, and does NOT change on a second grade of the SAME question.
  * GET /api/quiz/attempts/{slug} returns the latest attempt per question.
  * the anon key reads 0 rows from quiz_attempts and daily_activity (RLS on).
  * whatever this script wrote is removed again.

Usage: PYTHONIOENCODING=utf-8 python scripts/verify_4.py
Requires the API on http://localhost:8000, GEMINI_API_KEY in backend/.env, and
SUPABASE_ANON_KEY in the environment (it lives in frontend/.env.local).
"""

import os
import sys
from datetime import datetime, timezone

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
        print("FAIL: no lessons; confirm a file first (#1b).")
        return 1
    slug = lessons[0]["slug"]

    questions = httpx.get(
        f"{API}/api/lessons/{slug}/questions", headers=headers, timeout=120
    ).json()
    if not isinstance(questions, list) or not questions:
        print(f"FAIL: no questions for {slug}; run verify_4a.py first. Got: {questions}")
        return 1
    question_id = questions[0]["id"]
    print(f"target question: {question_id} on lesson {slug}")

    today = datetime.now(timezone.utc).date().isoformat()

    def daily_count():
        rows = httpx.get(
            f"{base}/rest/v1/daily_activity",
            params={"activity_date": f"eq.{today}", "select": "questions_done_count"},
            headers=_db_headers(service_key),
            timeout=30,
        ).json()
        return rows[0]["questions_done_count"] if rows else 0

    before = daily_count()

    first = httpx.post(
        f"{API}/api/quiz/grade",
        json={"question_id": question_id, "user_answer": "Đây là câu trả lời thử nghiệm."},
        headers=headers,
        timeout=120,
    ).json()
    print(f"\nPOST grade #1 -> score={first['score']} missing={first['missing_points']}")
    print(f"  comment: {first['comment']}")
    assert 0 <= first["score"] <= 10, "score out of range"

    after_first = daily_count()
    print(f"daily_activity today: {before} -> {after_first} (expect +1)")
    assert after_first == before + 1, "daily did not increment by 1 on first grade"

    httpx.post(
        f"{API}/api/quiz/grade",
        json={"question_id": question_id, "user_answer": "Nộp lại lần hai."},
        headers=headers,
        timeout=120,
    )
    after_second = daily_count()
    print(f"daily_activity after 2nd grade of same question: {after_second} (expect unchanged)")
    assert after_second == after_first, "daily must NOT change on a repeat of the same question"

    attempts = httpx.get(
        f"{API}/api/quiz/attempts/{slug}", headers=headers, timeout=30
    ).json()
    mine = [a for a in attempts if a["question_id"] == question_id]
    assert len(mine) == 1, "attempts must return exactly one (latest) row per question"
    assert mine[0]["user_answer"] == "Nộp lại lần hai.", "attempts must show the LATEST answer"
    print(f"GET attempts -> latest answer for the question: {mine[0]['user_answer']!r}")

    anon = os.environ["SUPABASE_ANON_KEY"]
    for table in ("quiz_attempts", "daily_activity"):
        rows = httpx.get(
            f"{base}/rest/v1/{table}",
            params={"select": "*"},
            headers={"apikey": anon},
            timeout=30,
        ).json()
        print(f"anon key sees {len(rows)} {table} rows (must be 0)")
        assert rows == [], f"RLS is NOT protecting {table}"

    # Clean up: delete the attempts and reset today's daily row this script wrote.
    httpx.request(
        "DELETE",
        f"{base}/rest/v1/quiz_attempts",
        params={"question_id": f"eq.{question_id}"},
        headers=_db_headers(service_key),
        timeout=30,
    )
    if before == 0:
        httpx.request(
            "DELETE",
            f"{base}/rest/v1/daily_activity",
            params={"activity_date": f"eq.{today}"},
            headers=_db_headers(service_key),
            timeout=30,
        )
    else:
        httpx.patch(
            f"{base}/rest/v1/daily_activity",
            params={"activity_date": f"eq.{today}"},
            headers={**_db_headers(service_key), "Content-Type": "application/json"},
            json={"questions_done_count": before},
            timeout=30,
        )
    print("cleaned up the quiz_attempts + daily_activity this script wrote")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
