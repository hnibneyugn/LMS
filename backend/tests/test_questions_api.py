"""GET/POST questions endpoints with a fake repo and a fake generator."""

import pytest
from fastapi.testclient import TestClient

from app.ai.questions import GeneratedQuestion, QuestionGenerationError
from app.main import app
from app.routers import lessons as lessons_router
from tests.conftest import OTHER_USER_ID, USER_ID, auth_headers

client = TestClient(app)


class _FakeLessonRepo:
    def __init__(self):
        self.lessons: list[dict] = []

    def get_lesson_by_slug(self, user_id, slug):
        for row in self.lessons:
            if row["user_id"] == user_id and row["slug"] == slug:
                return dict(row)
        return None


class _FakeQuestionRepo:
    def __init__(self):
        self.rows: list[dict] = []
        self.inserted: list[list[dict]] = []
        self.deleted: list[tuple] = []

    def list_questions(self, user_id, lesson_id):
        return [
            dict(r)
            for r in self.rows
            if r["user_id"] == user_id and r["lesson_id"] == lesson_id
        ]

    def insert_questions(self, rows):
        self.inserted.append([dict(r) for r in rows])
        self.rows.extend(dict(r) for r in rows)

    def delete_questions(self, user_id, lesson_id):
        self.deleted.append((user_id, lesson_id))
        self.rows = [
            r
            for r in self.rows
            if not (r["user_id"] == user_id and r["lesson_id"] == lesson_id)
        ]


def _lesson(slug="gt-0", user_id=USER_ID, content="nội dung bài", lesson_id="l1"):
    return {
        "id": lesson_id,
        "user_id": user_id,
        "slug": slug,
        "title": "Chương 1",
        "content_md": content,
    }


@pytest.fixture
def fakes(monkeypatch):
    lrepo = _FakeLessonRepo()
    qrepo = _FakeQuestionRepo()
    monkeypatch.setattr(lessons_router, "repo", lrepo)
    monkeypatch.setattr(lessons_router, "question_repo", qrepo)
    calls = {"count": 0}

    def fake_generate(content_md):
        calls["count"] += 1
        return [
            GeneratedQuestion(type="recall", question_text="Câu 1?"),
            GeneratedQuestion(type="scenario", question_text="Câu 2?"),
        ]

    monkeypatch.setattr(lessons_router, "generate_questions", fake_generate)
    return lrepo, qrepo, calls


def test_get_generates_and_persists_on_a_cache_miss(fakes):
    lrepo, qrepo, calls = fakes
    lrepo.lessons = [_lesson()]

    res = client.get("/api/lessons/gt-0/questions", headers=auth_headers())

    assert res.status_code == 200
    body = res.json()
    assert [q["question_text"] for q in body] == ["Câu 1?", "Câu 2?"]
    assert [q["order_index"] for q in body] == [0, 1]
    assert all(q["id"] for q in body)
    assert calls["count"] == 1
    assert len(qrepo.inserted) == 1


def test_get_returns_cached_questions_without_calling_the_model(fakes):
    lrepo, qrepo, calls = fakes
    lrepo.lessons = [_lesson()]
    qrepo.rows = [
        {
            "id": "q1",
            "user_id": USER_ID,
            "lesson_id": "l1",
            "type": "recall",
            "question_text": "Đã có sẵn?",
            "order_index": 0,
        }
    ]

    res = client.get("/api/lessons/gt-0/questions", headers=auth_headers())

    assert res.status_code == 200
    assert [q["question_text"] for q in res.json()] == ["Đã có sẵn?"]
    assert calls["count"] == 0
    assert qrepo.inserted == []


def test_get_on_another_users_lesson_is_404(fakes):
    lrepo, _, _ = fakes
    lrepo.lessons = [_lesson(user_id=OTHER_USER_ID)]

    res = client.get("/api/lessons/gt-0/questions", headers=auth_headers())

    assert res.status_code == 404


def test_get_returns_502_when_generation_fails(fakes, monkeypatch):
    lrepo, _, _ = fakes
    lrepo.lessons = [_lesson()]

    def boom(content_md):
        raise QuestionGenerationError("Không sinh được câu hỏi lúc này. Vui lòng thử lại.")

    monkeypatch.setattr(lessons_router, "generate_questions", boom)

    res = client.get("/api/lessons/gt-0/questions", headers=auth_headers())

    assert res.status_code == 502
    assert "câu hỏi" in res.json()["detail"].lower()


def test_regenerate_deletes_old_then_writes_new(fakes):
    lrepo, qrepo, calls = fakes
    lrepo.lessons = [_lesson()]
    qrepo.rows = [
        {
            "id": "old",
            "user_id": USER_ID,
            "lesson_id": "l1",
            "type": "recall",
            "question_text": "Câu cũ?",
            "order_index": 0,
        }
    ]

    res = client.post("/api/lessons/gt-0/questions/regenerate", headers=auth_headers())

    assert res.status_code == 200
    assert (USER_ID, "l1") in qrepo.deleted
    assert [q["question_text"] for q in res.json()] == ["Câu 1?", "Câu 2?"]
    assert calls["count"] == 1


def test_regenerate_keeps_old_set_when_generation_fails(fakes, monkeypatch):
    lrepo, qrepo, _ = fakes
    lrepo.lessons = [_lesson()]
    qrepo.rows = [
        {
            "id": "old",
            "user_id": USER_ID,
            "lesson_id": "l1",
            "type": "recall",
            "question_text": "Câu cũ?",
            "order_index": 0,
        }
    ]

    def boom(content_md):
        raise QuestionGenerationError("lỗi")

    monkeypatch.setattr(lessons_router, "generate_questions", boom)

    res = client.post("/api/lessons/gt-0/questions/regenerate", headers=auth_headers())

    assert res.status_code == 502
    # Old set must NOT be deleted when generation fails first.
    assert qrepo.deleted == []
    assert qrepo.rows[0]["question_text"] == "Câu cũ?"


def test_get_on_empty_content_is_422_without_calling_the_model(fakes):
    lrepo, qrepo, calls = fakes
    lrepo.lessons = [_lesson(content="   ")]

    res = client.get("/api/lessons/gt-0/questions", headers=auth_headers())

    assert res.status_code == 422
    # A lesson with no real text must never reach the model or the DB.
    assert calls["count"] == 0
    assert qrepo.inserted == []


def test_regenerate_on_empty_content_is_422_without_calling_the_model(fakes):
    lrepo, qrepo, calls = fakes
    lrepo.lessons = [_lesson(content="   ")]

    res = client.post("/api/lessons/gt-0/questions/regenerate", headers=auth_headers())

    assert res.status_code == 422
    assert calls["count"] == 0
    # Nothing generated means nothing deleted -- the old set (if any) is safe.
    assert qrepo.deleted == []


def test_questions_require_a_token(fakes):
    assert client.get("/api/lessons/gt-0/questions").status_code == 401
    assert client.post("/api/lessons/gt-0/questions/regenerate").status_code == 401
