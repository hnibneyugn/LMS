"""One-off live end-to-end check of #5: Socratic chat stream + persistence + RLS.

Hits the real API (real Gemini) and real Supabase with the ADMIN account:
  * POST /api/chat/{lesson_id} streams a non-empty Vietnamese reply.
  * the saved conversation grows to 2 messages, then 4 after a second turn.
  * DELETE empties the conversation.
  * the anon key reads 0 rows from chat_sessions (RLS on).
  * whatever this script wrote is removed again.

Usage: PYTHONIOENCODING=utf-8 python scripts/verify_5.py
Requires the API on http://localhost:8000, GEMINI_API_KEY in backend/.env, and
SUPABASE_ANON_KEY in the environment (it lives in frontend/.env.local).
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


def _stream_post(url, headers, message):
    text = ""
    with httpx.stream(
        "POST", url, json={"message": message}, headers=headers, timeout=120
    ) as r:
        if r.status_code != 200:
            r.read()
            raise AssertionError(f"POST chat -> {r.status_code}: {r.text}")
        for piece in r.iter_text():
            text += piece
    return text


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
    detail = httpx.get(f"{API}/api/lessons/{slug}", headers=headers, timeout=30).json()
    lesson_id = detail["id"]
    print(f"target lesson: {lesson_id} ({slug})")

    reply = _stream_post(
        f"{API}/api/chat/{lesson_id}", headers, "Bài này nói về điều gì là quan trọng nhất?"
    )
    print(f"\nstreamed reply ({len(reply)} chars):\n  {reply[:300]}")
    assert reply.strip(), "reply must be non-empty"
    assert "?" in reply, "a Socratic reply should ask a guiding question"

    hist = httpx.get(f"{API}/api/chat/{lesson_id}", headers=headers, timeout=30).json()
    assert len(hist["messages"]) == 2, f"expected 2 messages, got {hist['messages']}"
    assert hist["messages"][0]["role"] == "user"
    assert hist["messages"][1]["role"] == "assistant"
    print("history after 1 turn: 2 messages (user + assistant) OK")

    _stream_post(f"{API}/api/chat/{lesson_id}", headers, "Vì sao bạn hỏi vậy?")
    hist2 = httpx.get(f"{API}/api/chat/{lesson_id}", headers=headers, timeout=30).json()
    assert len(hist2["messages"]) == 4, f"expected 4 messages, got {len(hist2['messages'])}"
    print("history after 2 turns: 4 messages OK (context carried)")

    cleared = httpx.request(
        "DELETE", f"{API}/api/chat/{lesson_id}", headers=headers, timeout=30
    ).json()
    assert cleared == {"messages": []}, cleared
    after = httpx.get(f"{API}/api/chat/{lesson_id}", headers=headers, timeout=30).json()
    assert after["messages"] == [], "DELETE must empty the conversation"
    print("DELETE cleared the conversation OK")

    anon = os.environ["SUPABASE_ANON_KEY"]
    rows = httpx.get(
        f"{base}/rest/v1/chat_sessions",
        params={"select": "*"},
        headers={"apikey": anon},
        timeout=30,
    ).json()
    print(f"anon key sees {len(rows)} chat_sessions rows (must be 0)")
    assert rows == [], "RLS is NOT protecting chat_sessions"

    # Clean up: remove the chat_sessions row this script created.
    httpx.request(
        "DELETE",
        f"{base}/rest/v1/chat_sessions",
        params={"lesson_id": f"eq.{lesson_id}"},
        headers=_db_headers(service_key),
        timeout=30,
    )
    print("cleaned up the chat_sessions row this script wrote")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
