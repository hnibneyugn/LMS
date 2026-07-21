"""POST /api/quiz/grade with a fake repo and a fake grader."""

import pytest
from fastapi.testclient import TestClient

from app.ai.grading import GradeResult, GradingError
from app.main import app
from app.routers import quiz as quiz_router
from tests.conftest import OTHER_USER_ID, USER_ID, auth_headers

client = TestClient(app)


class _FakeRepo:
    def __init__(self):
        self.questions: list[dict] = []
        self.lessons: list[dict] = []
        self.attempts: list[dict] = []
        self.daily: dict[tuple, dict] = {}
        self.inserted: list[dict] = []

    def get_question(self, user_id, question_id):
        for q in self.questions:
            if q["id"] == question_id and q["user_id"] == user_id:
                return dict(q)
        return None

    def get_lesson_content(self, user_id, lesson_id):
        for row in self.lessons:
            if row["id"] == lesson_id and row["user_id"] == user_id:
                return {"content_md": row["content_md"]}
        return None

    def list_question_attempts(self, user_id, question_id):
        return [
            dict(a)
            for a in self.attempts
            if a["user_id"] == user_id and a["question_id"] == question_id
        ]

    def insert_attempt(self, row):
        self.inserted.append(dict(row))
        self.attempts.append(dict(row))

    def get_daily(self, user_id, activity_date):
        return self.daily.get((user_id, activity_date))

    def upsert_daily(self, values):
        self.daily[(values["user_id"], values["activity_date"])] = dict(values)

    def get_lesson_by_slug(self, user_id, slug):
        for row in self.lessons:
            if row.get("slug") == slug and row["user_id"] == user_id:
                return {"id": row["id"]}
        return None

    def list_lesson_question_ids(self, user_id, lesson_id):
        return [
            q["id"]
            for q in self.questions
            if q["user_id"] == user_id and q["lesson_id"] == lesson_id
        ]


def _question(qid="q1", user_id=USER_ID, lesson_id="l1"):
    return {
        "id": qid, "user_id": user_id, "lesson_id": lesson_id,
        "question_text": "Câu hỏi?", "type": "recall",
    }


@pytest.fixture
def fakes(monkeypatch):
    repo = _FakeRepo()
    repo.questions = [_question()]
    repo.lessons = [{"id": "l1", "user_id": USER_ID, "content_md": "nội dung"}]
    monkeypatch.setattr(quiz_router, "repo", repo)

    calls = {"count": 0}

    def fake_grade(content_md, question_text, question_type, user_answer):
        calls["count"] += 1
        return GradeResult(score=8.0, missing_points=["Thiếu X"], comment="Tốt.")

    monkeypatch.setattr(quiz_router, "grade_answer", fake_grade)
    return repo, calls


def test_grade_saves_attempt_and_returns_result(fakes):
    repo, calls = fakes

    res = client.post(
        "/api/quiz/grade",
        json={"question_id": "q1", "user_answer": "trả lời của tôi"},
        headers=auth_headers(),
    )

    assert res.status_code == 200
    body = res.json()
    assert body["score"] == 8.0
    assert body["missing_points"] == ["Thiếu X"]
    assert body["comment"] == "Tốt."
    assert body["created_at"]
    assert calls["count"] == 1
    # One attempt persisted, with the trimmed answer and feedback shape.
    assert len(repo.inserted) == 1
    saved = repo.inserted[0]
    assert saved["user_id"] == USER_ID
    assert saved["ai_score"] == 8.0
    assert saved["ai_feedback"] == {"missing_points": ["Thiếu X"], "comment": "Tốt."}


def test_grade_increments_daily_only_on_first_attempt_of_the_day(fakes):
    repo, _ = fakes

    client.post(
        "/api/quiz/grade",
        json={"question_id": "q1", "user_answer": "lần 1"},
        headers=auth_headers(),
    )
    # After the first grade, exactly one daily row with count 1.
    assert len(repo.daily) == 1
    assert next(iter(repo.daily.values()))["questions_done_count"] == 1

    # Second attempt of the SAME question the same day must not bump the count.
    client.post(
        "/api/quiz/grade",
        json={"question_id": "q1", "user_answer": "lần 2"},
        headers=auth_headers(),
    )
    assert next(iter(repo.daily.values()))["questions_done_count"] == 1
    assert len(repo.inserted) == 2  # but the attempt itself is still recorded


def test_grade_on_another_users_question_is_404(fakes):
    repo, _ = fakes
    repo.questions = [_question(user_id=OTHER_USER_ID)]

    res = client.post(
        "/api/quiz/grade",
        json={"question_id": "q1", "user_answer": "x"},
        headers=auth_headers(),
    )
    assert res.status_code == 404


def test_grade_empty_answer_is_422_without_calling_the_model(fakes):
    repo, calls = fakes

    res = client.post(
        "/api/quiz/grade",
        json={"question_id": "q1", "user_answer": "   "},
        headers=auth_headers(),
    )
    assert res.status_code == 422
    assert calls["count"] == 0
    assert repo.inserted == []


def test_grade_returns_502_when_grading_fails(fakes, monkeypatch):
    repo, _ = fakes

    def boom(*args):
        raise GradingError("Không chấm được bài lúc này. Vui lòng thử lại.")

    monkeypatch.setattr(quiz_router, "grade_answer", boom)

    res = client.post(
        "/api/quiz/grade",
        json={"question_id": "q1", "user_answer": "x"},
        headers=auth_headers(),
    )
    assert res.status_code == 502
    # Nothing persisted on an AI failure.
    assert repo.inserted == []
    assert repo.daily == {}


def test_grade_requires_a_token(fakes):
    res = client.post("/api/quiz/grade", json={"question_id": "q1", "user_answer": "x"})
    assert res.status_code == 401


def test_attempts_returns_latest_per_question(fakes):
    repo, _ = fakes
    repo.lessons = [
        {"id": "l1", "user_id": USER_ID, "content_md": "nd", "slug": "gt-0"}
    ]
    repo.questions = [_question("q1"), _question("q2")]
    repo.attempts = [
        {
            "id": "a1", "user_id": USER_ID, "question_id": "q1", "user_answer": "cũ",
            "ai_score": 4.0, "ai_feedback": {"missing_points": ["A"], "comment": "c1"},
            "created_at": "2026-07-21T01:00:00+00:00",
        },
        {
            "id": "a2", "user_id": USER_ID, "question_id": "q1", "user_answer": "mới",
            "ai_score": 9.0, "ai_feedback": {"missing_points": [], "comment": "c2"},
            "created_at": "2026-07-21T02:00:00+00:00",
        },
    ]

    res = client.get("/api/quiz/attempts/gt-0", headers=auth_headers())

    assert res.status_code == 200
    body = res.json()
    # q1 -> its latest attempt only; q2 -> no attempt, absent.
    assert len(body) == 1
    assert body[0]["question_id"] == "q1"
    assert body[0]["user_answer"] == "mới"
    assert body[0]["score"] == 9.0
    assert body[0]["missing_points"] == []
    assert body[0]["comment"] == "c2"


def test_attempts_on_another_users_lesson_is_404(fakes):
    repo, _ = fakes
    repo.lessons = [{"id": "l1", "user_id": OTHER_USER_ID, "content_md": "x", "slug": "gt-0"}]

    res = client.get("/api/quiz/attempts/gt-0", headers=auth_headers())
    assert res.status_code == 404


def test_attempts_requires_a_token(fakes):
    assert client.get("/api/quiz/attempts/gt-0").status_code == 401
