"""_Repo query building for quiz.py against a fake supabase client.

db.admin() is a service-role client that bypasses RLS, so the explicit
`.eq("user_id", ...)` filters here are the ONLY thing isolating one user's
attempts/questions from another's. Running the REAL _Repo means a dropped
filter reds a test.
"""

import pytest

from app.routers import quiz as quiz_router
from tests.conftest import OTHER_USER_ID, USER_ID, FakeClient


@pytest.fixture
def stores(monkeypatch):
    tables = {"questions": {}, "lessons": {}, "quiz_attempts": {}, "daily_activity": {}}
    client_ = FakeClient({}, tables=tables)
    monkeypatch.setattr(quiz_router.db, "admin", lambda: client_)
    return tables


def test_get_question_does_not_return_another_users_row(stores):
    stores["questions"]["q1"] = {
        "id": "q1", "user_id": USER_ID, "lesson_id": "l1",
        "question_text": "Câu?", "type": "recall",
    }
    repo = quiz_router._Repo()

    assert repo.get_question(USER_ID, "q1")["lesson_id"] == "l1"
    assert repo.get_question(OTHER_USER_ID, "q1") is None


def test_get_lesson_content_scoped_to_user(stores):
    stores["lessons"]["l1"] = {"id": "l1", "user_id": USER_ID, "content_md": "abc"}
    repo = quiz_router._Repo()

    assert repo.get_lesson_content(USER_ID, "l1")["content_md"] == "abc"
    assert repo.get_lesson_content(OTHER_USER_ID, "l1") is None


def test_list_question_attempts_only_returns_own(stores):
    stores["quiz_attempts"]["a1"] = {
        "id": "a1", "user_id": USER_ID, "question_id": "q1",
        "user_answer": "x", "ai_score": 5, "ai_feedback": {}, "created_at": "t1",
    }
    stores["quiz_attempts"]["a9"] = {
        "id": "a9", "user_id": OTHER_USER_ID, "question_id": "q1",
        "user_answer": "y", "ai_score": 9, "ai_feedback": {}, "created_at": "t2",
    }
    repo = quiz_router._Repo()

    rows = repo.list_question_attempts(USER_ID, "q1")
    assert {r["id"] for r in rows} == {"a1"}


def test_daily_get_and_upsert_key_on_user_and_date(stores):
    repo = quiz_router._Repo()
    repo.upsert_daily(
        {"user_id": USER_ID, "activity_date": "2026-07-21", "questions_done_count": 1}
    )
    repo.upsert_daily(
        {"user_id": USER_ID, "activity_date": "2026-07-21", "questions_done_count": 2}
    )

    # Second upsert replaces, not adds a second row.
    assert len(stores["daily_activity"]) == 1
    assert repo.get_daily(USER_ID, "2026-07-21")["questions_done_count"] == 2
    assert repo.get_daily(OTHER_USER_ID, "2026-07-21") is None


def test_upsert_daily_keys_on_user_and_date_not_date_alone(stores):
    # Two users, same date -> two separate rows. If upsert_daily's on_conflict
    # dropped user_id (keyed on activity_date alone), the second upsert would
    # overwrite the first and this would collapse to one row.
    repo = quiz_router._Repo()
    repo.upsert_daily(
        {"user_id": USER_ID, "activity_date": "2026-07-21", "questions_done_count": 1}
    )
    repo.upsert_daily(
        {"user_id": OTHER_USER_ID, "activity_date": "2026-07-21", "questions_done_count": 5}
    )

    assert len(stores["daily_activity"]) == 2
    assert repo.get_daily(USER_ID, "2026-07-21")["questions_done_count"] == 1
    assert repo.get_daily(OTHER_USER_ID, "2026-07-21")["questions_done_count"] == 5
