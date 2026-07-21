"""_QuestionRepo query building against a fake supabase client.

db.admin() is a service-role client that bypasses RLS, so the explicit
`.eq("user_id", ...)` filters here are the ONLY thing isolating one user's
questions from another's. These tests run the REAL repo so a dropped filter
fails here even though the router tests (fake repo) would not catch it.
"""

import pytest

from app.routers import lessons as lessons_router
from tests.conftest import OTHER_USER_ID, USER_ID, FakeClient


@pytest.fixture
def questions_store(monkeypatch):
    store: dict = {}
    client_ = FakeClient(store, tables={"questions": store})
    monkeypatch.setattr(lessons_router.db, "admin", lambda: client_)
    return store


def _q(qid, user_id, lesson_id, order_index):
    return {
        "id": qid,
        "user_id": user_id,
        "lesson_id": lesson_id,
        "type": "recall",
        "question_text": f"Câu {order_index}?",
        "order_index": order_index,
    }


def test_list_questions_returns_only_own_rows(questions_store):
    questions_store["q1"] = _q("q1", USER_ID, "l1", 0)
    questions_store["q2"] = _q("q2", USER_ID, "l1", 1)
    questions_store["q9"] = _q("q9", OTHER_USER_ID, "l1", 0)

    repo = lessons_router._QuestionRepo()
    rows = repo.list_questions(USER_ID, "l1")

    assert {r["id"] for r in rows} == {"q1", "q2"}


def test_list_questions_filters_by_lesson(questions_store):
    questions_store["q1"] = _q("q1", USER_ID, "l1", 0)
    questions_store["q2"] = _q("q2", USER_ID, "l2", 0)

    repo = lessons_router._QuestionRepo()
    rows = repo.list_questions(USER_ID, "l1")

    assert [r["id"] for r in rows] == ["q1"]


def test_insert_then_delete_scopes_to_user_and_lesson(questions_store):
    repo = lessons_router._QuestionRepo()
    repo.insert_questions([_q("q1", USER_ID, "l1", 0), _q("q2", USER_ID, "l1", 1)])
    questions_store["q9"] = _q("q9", OTHER_USER_ID, "l1", 0)

    repo.delete_questions(USER_ID, "l1")

    # Own rows for l1 gone; the other user's row untouched.
    assert "q1" not in questions_store and "q2" not in questions_store
    assert "q9" in questions_store
