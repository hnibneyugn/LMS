"""/api/chat/{lesson_id} with a fake repo and a fake Socratic stream."""

import pytest
from fastapi.testclient import TestClient

from app.ai.chat import ChatError
from app.main import app
from app.routers import chat as chat_router
from tests.conftest import OTHER_USER_ID, USER_ID, auth_headers

client = TestClient(app)


class _FakeRepo:
    def __init__(self):
        self.lessons: list[dict] = []
        self.sessions: list[dict] = []  # {id, user_id, lesson_id, messages}
        self._next = 1

    def get_lesson(self, user_id, lesson_id):
        for row in self.lessons:
            if row["id"] == lesson_id and row["user_id"] == user_id:
                return {"id": row["id"], "content_md": row["content_md"]}
        return None

    def get_session(self, user_id, lesson_id):
        for s in self.sessions:
            if s["user_id"] == user_id and s["lesson_id"] == lesson_id:
                return {"id": s["id"], "messages": list(s["messages"])}
        return None

    def create_session(self, user_id, lesson_id):
        s = {
            "id": f"s{self._next}",
            "user_id": user_id,
            "lesson_id": lesson_id,
            "messages": [],
        }
        self._next += 1
        self.sessions.append(s)
        return {"id": s["id"], "messages": []}

    def update_messages(self, session_id, messages):
        for s in self.sessions:
            if s["id"] == session_id:
                s["messages"] = list(messages)


@pytest.fixture
def repo(monkeypatch):
    r = _FakeRepo()
    r.lessons = [{"id": "l1", "user_id": USER_ID, "content_md": "nội dung bài"}]
    monkeypatch.setattr(chat_router, "repo", r)
    return r


def _fake_stream_ok(content_md, history, message):
    yield "Bạn "
    yield "nghĩ sao?"


def test_post_streams_reply_and_persists_both_messages(repo, monkeypatch):
    monkeypatch.setattr(chat_router, "stream_socratic_reply", _fake_stream_ok)

    res = client.post("/api/chat/l1", json={"message": "Giải thích X"}, headers=auth_headers())

    assert res.status_code == 200
    assert res.text == "Bạn nghĩ sao?"
    saved = repo.get_session(USER_ID, "l1")["messages"]
    assert saved == [
        {"role": "user", "content": "Giải thích X"},
        {"role": "assistant", "content": "Bạn nghĩ sao?"},
    ]


def test_post_handles_create_session_race(repo, monkeypatch):
    # Simulate the unique-index race from migration 0008: get_session sees no
    # row yet, create_session loses the race (unique-violation because another
    # request already inserted), and the fallback re-read finds that row.
    repo.sessions = [
        {"id": "s-raced", "user_id": USER_ID, "lesson_id": "l1", "messages": []}
    ]
    real_get_session = repo.get_session
    calls = {"n": 0}

    def flaky_get_session(user_id, lesson_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # first look: the other writer hasn't committed yet
        return real_get_session(user_id, lesson_id)

    def raising_create_session(user_id, lesson_id):
        raise Exception("duplicate key value violates unique constraint")

    monkeypatch.setattr(repo, "get_session", flaky_get_session)
    monkeypatch.setattr(repo, "create_session", raising_create_session)
    monkeypatch.setattr(chat_router, "stream_socratic_reply", _fake_stream_ok)

    res = client.post("/api/chat/l1", json={"message": "Giải thích X"}, headers=auth_headers())

    assert res.status_code == 200
    assert res.text == "Bạn nghĩ sao?"
    saved = real_get_session(USER_ID, "l1")["messages"]
    assert saved == [
        {"role": "user", "content": "Giải thích X"},
        {"role": "assistant", "content": "Bạn nghĩ sao?"},
    ]


def test_post_empty_message_is_422(repo):
    res = client.post("/api/chat/l1", json={"message": "   "}, headers=auth_headers())
    assert res.status_code == 422


def test_post_on_another_users_lesson_is_404(repo):
    repo.lessons = [{"id": "l1", "user_id": OTHER_USER_ID, "content_md": "x"}]
    res = client.post("/api/chat/l1", json={"message": "hi"}, headers=auth_headers())
    assert res.status_code == 404


def test_post_saves_user_message_before_streaming(repo, monkeypatch):
    # AI fails on the very first chunk -> 502, and only the user message persisted.
    def boom(content_md, history, message):
        raise ChatError("Không trả lời được lúc này. Vui lòng thử lại.")
        yield  # make it a generator

    monkeypatch.setattr(chat_router, "stream_socratic_reply", boom)

    res = client.post("/api/chat/l1", json={"message": "Giải thích X"}, headers=auth_headers())

    assert res.status_code == 502
    saved = repo.get_session(USER_ID, "l1")["messages"]
    assert saved == [{"role": "user", "content": "Giải thích X"}]


def test_post_mid_stream_error_keeps_partial_reply(repo, monkeypatch):
    def mid(content_md, history, message):
        yield "phần đầu"
        raise ChatError("Không trả lời được lúc này. Vui lòng thử lại.")

    monkeypatch.setattr(chat_router, "stream_socratic_reply", mid)

    res = client.post("/api/chat/l1", json={"message": "Q"}, headers=auth_headers())

    assert res.status_code == 200
    assert res.text == "phần đầu"
    saved = repo.get_session(USER_ID, "l1")["messages"]
    assert saved == [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "phần đầu"},
    ]


def test_post_appends_to_existing_history(repo, monkeypatch):
    repo.sessions = [{
        "id": "s1", "user_id": USER_ID, "lesson_id": "l1",
        "messages": [
            {"role": "user", "content": "cũ"},
            {"role": "assistant", "content": "đáp cũ"},
        ],
    }]
    captured = {}

    def fake(content_md, history, message):
        captured["history"] = history
        yield "ok"

    monkeypatch.setattr(chat_router, "stream_socratic_reply", fake)

    client.post("/api/chat/l1", json={"message": "mới"}, headers=auth_headers())

    # history passed to the model is the OLD messages (not the new user turn).
    assert captured["history"] == [
        {"role": "user", "content": "cũ"},
        {"role": "assistant", "content": "đáp cũ"},
    ]
    assert len(repo.get_session(USER_ID, "l1")["messages"]) == 4


def test_get_history_no_session_is_empty(repo):
    res = client.get("/api/chat/l1", headers=auth_headers())
    assert res.status_code == 200
    assert res.json() == {"messages": []}


def test_get_history_returns_saved_messages(repo):
    repo.sessions = [{
        "id": "s1", "user_id": USER_ID, "lesson_id": "l1",
        "messages": [{"role": "user", "content": "hỏi"}],
    }]
    res = client.get("/api/chat/l1", headers=auth_headers())
    assert res.json() == {"messages": [{"role": "user", "content": "hỏi"}]}


def test_get_on_another_users_lesson_is_404(repo):
    repo.lessons = [{"id": "l1", "user_id": OTHER_USER_ID, "content_md": "x"}]
    assert client.get("/api/chat/l1", headers=auth_headers()).status_code == 404


def test_delete_clears_conversation(repo):
    repo.sessions = [{
        "id": "s1", "user_id": USER_ID, "lesson_id": "l1",
        "messages": [{"role": "user", "content": "hỏi"}],
    }]
    res = client.request("DELETE", "/api/chat/l1", headers=auth_headers())
    assert res.status_code == 200
    assert res.json() == {"messages": []}
    assert repo.get_session(USER_ID, "l1")["messages"] == []


def test_delete_on_another_users_lesson_is_404(repo):
    repo.lessons = [{"id": "l1", "user_id": OTHER_USER_ID, "content_md": "x"}]
    assert client.request("DELETE", "/api/chat/l1", headers=auth_headers()).status_code == 404


def test_requires_a_token(repo):
    assert client.get("/api/chat/l1").status_code == 401
    assert client.post("/api/chat/l1", json={"message": "hi"}).status_code == 401
