"""Dashboard endpoints with a fake repo (no DB, no clock dependence for the
leaderboard; /me still uses the real vn_today, so its assertions avoid exact
dates and check structure + counts)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import dashboard as dash
from tests.conftest import OTHER_USER_ID, USER_ID, auth_headers

client = TestClient(app)


class _FakeRepo:
    def __init__(self):
        self.daily: list[dict] = []
        self.total = 0
        self.completed = 0
        self.rows: list[dict] = []

    def list_daily(self, user_id):
        return [dict(r) for r in self.daily]

    def count_lessons(self, user_id):
        return self.total

    def count_completed_lessons(self, user_id):
        return self.completed

    def leaderboard(self):
        return [dict(r) for r in self.rows]


@pytest.fixture
def repo(monkeypatch):
    r = _FakeRepo()
    monkeypatch.setattr(dash, "repo", r)
    return r


def test_me_returns_full_shape(repo):
    repo.total = 4
    repo.completed = 1
    res = client.get("/api/dashboard/me", headers=auth_headers())
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {
        "current_streak", "longest_streak", "weekly_questions",
        "lessons_completed", "lessons_total", "completion_pct",
    }
    assert len(body["weekly_questions"]) == 7
    assert body["lessons_total"] == 4
    assert body["lessons_completed"] == 1
    assert body["completion_pct"] == 25


def test_me_requires_a_token(repo):
    assert client.get("/api/dashboard/me").status_code == 401


def test_leaderboard_sorted_by_active_days_and_flags_me(repo):
    repo.rows = [
        {"user_id": OTHER_USER_ID, "display_name": "An", "avatar_url": None,
         "active_days": 2, "lessons_completed": 1, "total_questions_done": 4},
        {"user_id": USER_ID, "display_name": "Tôi", "avatar_url": None,
         "active_days": 5, "lessons_completed": 3, "total_questions_done": 9},
    ]
    res = client.get("/api/dashboard/leaderboard", headers=auth_headers())
    assert res.status_code == 200
    body = res.json()
    # Sorted by active_days desc -> USER_ID first, flagged is_me.
    assert body[0]["user_id"] == USER_ID
    assert body[0]["is_me"] is True
    assert body[1]["is_me"] is False


def test_leaderboard_requires_a_token(repo):
    assert client.get("/api/dashboard/leaderboard").status_code == 401
