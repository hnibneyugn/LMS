"""_Repo query building for dashboard.py against a fake supabase client. The
explicit .eq('user_id', ...) filters are the only isolation past RLS, so a
dropped filter reds a test."""

import pytest

from app.routers import dashboard as dash
from tests.conftest import OTHER_USER_ID, USER_ID, FakeClient


@pytest.fixture
def stores(monkeypatch):
    tables = {
        "daily_activity": {},
        "lessons": {},
        "lesson_progress": {},
        "leaderboard_view": {},
    }
    client_ = FakeClient({}, tables=tables)
    monkeypatch.setattr(dash.db, "admin", lambda: client_)
    return tables


def test_list_daily_only_returns_own_rows(stores):
    stores["daily_activity"]["r1"] = {
        "id": "r1", "user_id": USER_ID, "activity_date": "2026-07-22",
        "questions_done_count": 3,
    }
    stores["daily_activity"]["r9"] = {
        "id": "r9", "user_id": OTHER_USER_ID, "activity_date": "2026-07-22",
        "questions_done_count": 9,
    }
    repo = dash._Repo()
    rows = repo.list_daily(USER_ID)
    assert len(rows) == 1
    assert rows[0]["questions_done_count"] == 3


def test_count_lessons_scoped_to_user(stores):
    stores["lessons"]["l1"] = {"id": "l1", "user_id": USER_ID}
    stores["lessons"]["l2"] = {"id": "l2", "user_id": USER_ID}
    stores["lessons"]["l9"] = {"id": "l9", "user_id": OTHER_USER_ID}
    repo = dash._Repo()
    assert repo.count_lessons(USER_ID) == 2
    assert repo.count_lessons(OTHER_USER_ID) == 1


def test_count_completed_lessons_filters_status_and_user(stores):
    stores["lesson_progress"]["p1"] = {
        "id": "p1", "user_id": USER_ID, "lesson_id": "l1", "status": "done",
    }
    stores["lesson_progress"]["p2"] = {
        "id": "p2", "user_id": USER_ID, "lesson_id": "l2", "status": "not_done",
    }
    stores["lesson_progress"]["p9"] = {
        "id": "p9", "user_id": OTHER_USER_ID, "lesson_id": "l1", "status": "done",
    }
    repo = dash._Repo()
    assert repo.count_completed_lessons(USER_ID) == 1


def test_leaderboard_reads_all_rows(stores):
    stores["leaderboard_view"]["u1"] = {
        "id": "u1", "user_id": USER_ID, "display_name": "A", "avatar_url": None,
        "active_days": 2, "lessons_completed": 1, "total_questions_done": 4,
    }
    stores["leaderboard_view"]["u2"] = {
        "id": "u2", "user_id": OTHER_USER_ID, "display_name": "B", "avatar_url": None,
        "active_days": 5, "lessons_completed": 3, "total_questions_done": 9,
    }
    repo = dash._Repo()
    assert len(repo.leaderboard()) == 2
