# #4 — AI Grading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chấm câu trả lời tự luận bằng Gemini (điểm 0–10 + ý còn thiếu + nhận xét), lưu `quiz_attempts` và tăng `daily_activity` (mỗi câu 1 lần/ngày), hiển thị inline ở section câu hỏi.

**Architecture:** Thêm module `app/ai/grading.py` (tái dùng `app/ai/client.py`), router mới `app/routers/quiz.py` (`POST /api/quiz/grade`, `GET /api/quiz/attempts/{slug}`), và mở rộng `ReviewQuestions.tsx` với ô trả lời + kết quả chấm. Không migration (bảng đã có). Không RAG.

**Tech Stack:** Python + FastAPI, `google-genai` (Gemini `gemini-3.5-flash`), Supabase Postgres + RLS, React + Vite + TypeScript.

## Global Constraints

- Spec nguồn: `docs/superpowers/specs/2026-07-21-ai-grading-design.md`. Đọc trước khi bắt đầu.
- Model chat: **`gemini-3.5-flash`** (hằng `CHAT_MODEL` ở `app/ai/client.py` — đã có). Không RAG.
- Mọi chuỗi hiển thị cho user = **tiếng Việt**; code/tên biến/comment = **tiếng Anh**.
- `db.admin()` là service-role client **bypass RLS** — mọi truy vấn phải lọc `user_id` tường minh; câu/bài của người khác → **404** (không 403).
- Graceful degradation: lỗi AI KHÔNG làm sập pipeline — try/catch, trả lỗi tiếng Việt (502), cho retry, KHÔNG ghi gì khi lỗi. Không nuốt lỗi.
- `quiz_attempts` là **lịch sử bất biến** (chỉ insert; không update/delete). id mint ở backend bằng `uuid.uuid4()` (như `files.py`/#4a).
- `daily_activity` tăng **mỗi câu 1 lần/ngày** (theo ngày UTC): chỉ +1 khi đây là attempt đầu tiên của câu đó trong hôm nay.
- Backend verify: `pytest` từ `backend/` phải **xanh và output sạch** (không warning). Frontend: `npm run build` từ `frontend/` không lỗi TS. Lint frontend dùng `npx oxlint <files>` (không `npm run lint`).
- Secret qua env, không hardcode. Commit sau mỗi task.

## File Structure

**Tạo mới:**
- `backend/app/ai/grading.py` — `grade_answer()` + `GradeResult` + `GradingError`.
- `backend/app/routers/quiz.py` — `_Repo`, models, 2 endpoint.
- `backend/tests/test_grading.py` — test generator chấm với client giả.
- `backend/tests/test_quiz_api.py` — test endpoint với repo giả + grader giả.
- `backend/tests/test_quiz_repo.py` — test `_Repo` query-building với client giả.
- `backend/scripts/verify_4.py` — kiểm thật.
- `frontend/src/lib/quiz.ts` — types + `gradeAnswer` + `getAttempts`.

**Sửa:**
- `backend/app/main.py` — include `quiz.router`.
- `frontend/src/components/ReviewQuestions.tsx` — ô trả lời + submit + kết quả + prefill.
- `check_list.md` — đánh dấu #4 xong.

**Không cần** conftest thay đổi: mọi truy vấn dùng `eq`/`maybe_single`/`insert`/`upsert` mà `FakeTable` đã hỗ trợ (không dùng `.in_()`/`.gte()`).

---

### Task 1: AI grading module

**Files:**
- Create: `backend/app/ai/grading.py`
- Test: `backend/tests/test_grading.py`

**Interfaces:**
- Consumes: `app.ai.client.get_client`, `app.ai.client.CHAT_MODEL` (đã có từ #4a).
- Produces:
  - `GradeResult(BaseModel)`: `score: float`, `missing_points: list[str]`, `comment: str`.
  - `GradingError(Exception)` — thông báo tiếng Việt.
  - `grade_answer(content_md: str, question_text: str, question_type: str, user_answer: str) -> GradeResult` — raise `GradingError` khi không chấm được.

- [ ] **Step 1: Viết test**

Create `backend/tests/test_grading.py`:

```python
"""AI grading: grade_answer logic against a fake Gemini client (no network)."""

import pytest

from app.ai import grading as grading_module
from app.ai.grading import GradeResult, GradingError, grade_answer


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise = raise_exc
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return self._response


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _patch(monkeypatch, models):
    monkeypatch.setattr(grading_module, "get_client", lambda: _FakeClient(models))


def test_grade_returns_validated_result(monkeypatch):
    payload = '{"score": 7.5, "missing_points": ["Thiếu ví dụ"], "comment": "Khá tốt."}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    result = grade_answer("nội dung", "Câu hỏi?", "recall", "câu trả lời")

    assert result == GradeResult(
        score=7.5, missing_points=["Thiếu ví dụ"], comment="Khá tốt."
    )


def test_grade_clamps_score_into_range(monkeypatch):
    payload = '{"score": 42, "missing_points": [], "comment": "ok"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    assert grade_answer("nd", "q", "recall", "a").score == 10.0

    payload2 = '{"score": -3, "missing_points": [], "comment": "ok"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload2)))

    assert grade_answer("nd", "q", "recall", "a").score == 0.0


def test_grade_drops_blank_missing_points(monkeypatch):
    payload = '{"score": 5, "missing_points": ["Ý A", "  ", ""], "comment": "c"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    assert grade_answer("nd", "q", "recall", "a").missing_points == ["Ý A"]


def test_grade_raises_when_score_is_not_a_number(monkeypatch):
    payload = '{"score": "bảy", "missing_points": [], "comment": "c"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "a")


def test_grade_raises_when_missing_points_is_not_a_list(monkeypatch):
    payload = '{"score": 5, "missing_points": "Ý A", "comment": "c"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "a")


def test_grade_raises_on_malformed_json(monkeypatch):
    _patch(monkeypatch, _FakeModels(_FakeResponse("not json")))

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "a")


def test_grade_raises_when_api_call_fails(monkeypatch):
    _patch(monkeypatch, _FakeModels(raise_exc=RuntimeError("quota")))

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "a")


def test_grade_rejects_empty_answer_without_calling_the_model(monkeypatch):
    models = _FakeModels(_FakeResponse("{}"))
    _patch(monkeypatch, models)

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "   ")

    assert models.calls == 0
```

- [ ] **Step 2: Chạy test — phải fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_grading.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ai.grading'`.

- [ ] **Step 3: Viết `grading.py`**

Create `backend/app/ai/grading.py`:

```python
"""Grade one free-text answer to a review question via Gemini structured output (#4).

No RAG: grades using the whole lesson content + question + answer (D8/D13). Any
failure (network, quota, malformed output) raises GradingError with a Vietnamese
message -- it never returns junk and never crashes the request.
"""

import json
import logging

from pydantic import BaseModel

from app.ai.client import CHAT_MODEL, get_client

logger = logging.getLogger(__name__)

_FAILURE_MESSAGE = "Không chấm được bài lúc này. Vui lòng thử lại."


class GradeResult(BaseModel):
    score: float
    missing_points: list[str]
    comment: str


class GradingError(Exception):
    """Grade call or its output could not yield a usable result.

    Its message is Vietnamese and safe to surface to the user.
    """


_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "missing_points": {"type": "array", "items": {"type": "string"}},
        "comment": {"type": "string"},
    },
    "required": ["score", "missing_points", "comment"],
}


def _build_prompt(
    content_md: str, question_text: str, question_type: str, user_answer: str
) -> str:
    return (
        "Bạn là giám khảo chấm bài tự luận. Chỉ dựa trên nội dung bài học dưới đây, "
        "hãy chấm câu trả lời của người học theo thang điểm 0–10.\n\n"
        "Trả về:\n"
        "- score: điểm số từ 0 đến 10 (được dùng số thập phân), phản ánh mức độ đúng "
        "và đầy đủ so với nội dung bài.\n"
        "- missing_points: danh sách các ý quan trọng trong bài mà câu trả lời còn "
        "thiếu hoặc sai (để mảng rỗng nếu đã đầy đủ).\n"
        "- comment: một nhận xét ngắn gọn, mang tính xây dựng, bằng tiếng Việt.\n\n"
        "Chấm công bằng, bám sát nội dung bài; không trừ điểm vì những gì bài không đề cập.\n\n"
        f"----- NỘI DUNG BÀI HỌC -----\n{content_md}\n\n"
        f"----- CÂU HỎI (loại: {question_type}) -----\n{question_text}\n\n"
        f"----- CÂU TRẢ LỜI CỦA NGƯỜI HỌC -----\n{user_answer}"
    )


def _validate(raw: object) -> GradeResult:
    """Coerce the model's JSON into a GradeResult or raise GradingError.

    score is clamped into [0, 10] (an out-of-range number is corrected, not
    rejected). missing_points must be a list of strings; blank entries are
    dropped. comment must be a string.
    """
    if not isinstance(raw, dict):
        raise GradingError(_FAILURE_MESSAGE)

    score = raw.get("score")
    missing = raw.get("missing_points")
    comment = raw.get("comment")

    # bool is an int subclass -- exclude it so `True` is not read as score 1.
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise GradingError(_FAILURE_MESSAGE)
    if not isinstance(missing, list) or not all(isinstance(m, str) for m in missing):
        raise GradingError(_FAILURE_MESSAGE)
    if not isinstance(comment, str):
        raise GradingError(_FAILURE_MESSAGE)

    clamped = max(0.0, min(10.0, float(score)))
    return GradeResult(
        score=clamped,
        missing_points=[m.strip() for m in missing if m.strip()],
        comment=comment,
    )


def grade_answer(
    content_md: str, question_text: str, question_type: str, user_answer: str
) -> GradeResult:
    if not user_answer or not user_answer.strip():
        raise GradingError("Câu trả lời không được để trống.")

    try:
        response = get_client().models.generate_content(
            model=CHAT_MODEL,
            contents=_build_prompt(
                content_md, question_text, question_type, user_answer
            ),
            config={
                "response_mime_type": "application/json",
                "response_schema": _RESPONSE_SCHEMA,
            },
        )
        raw = json.loads(response.text)
    except Exception as exc:  # network, quota, malformed JSON, missing .text
        logger.exception("Gemini grading failed")
        raise GradingError(_FAILURE_MESSAGE) from exc

    return _validate(raw)
```

- [ ] **Step 4: Chạy test — phải pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_grading.py -v`
Expected: PASS toàn bộ (8 test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/grading.py backend/tests/test_grading.py
git commit -m "feat(ai): grade_answer with structured output + graceful degradation"
```

---

### Task 2: Quiz repo + `POST /api/quiz/grade`

**Files:**
- Create: `backend/app/routers/quiz.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_quiz_api.py` (create), `backend/tests/test_quiz_repo.py` (create)

**Interfaces:**
- Consumes: `grade_answer` + `GradingError` (Task 1).
- Produces:
  - `GradeRequest(BaseModel)`: `question_id: str`, `user_answer: str` (Field `max_length=5000`).
  - `GradeOut(BaseModel)`: `score: float`, `missing_points: list[str]`, `comment: str`, `created_at: str`.
  - `_Repo` với: `get_question(user_id, question_id)`, `get_lesson_content(user_id, lesson_id)`, `list_question_attempts(user_id, question_id)`, `insert_attempt(row)`, `get_daily(user_id, activity_date)`, `upsert_daily(values)`. Module-level instance `repo`.
  - `POST /api/quiz/grade` → `response_model=GradeOut`.

- [ ] **Step 1: Viết test cho `_Repo`**

Create `backend/tests/test_quiz_repo.py`:

```python
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
```

- [ ] **Step 2: Chạy test — phải fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_quiz_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.quiz'`.

- [ ] **Step 3: Viết `quiz.py` (repo + grade endpoint)**

Create `backend/app/routers/quiz.py`:

```python
"""Grading free-text answers to review questions (#4).

quiz_attempts is immutable history (insert only). daily_activity increments
once per question per UTC day. db.admin() bypasses RLS, so every query filters
user_id explicitly and another user's question/lesson is 404, never 403.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import db
from app.ai.grading import GradingError, grade_answer
from app.dependencies.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/quiz", tags=["quiz"])

QUESTION_NOT_FOUND = "Không tìm thấy câu hỏi."
LESSON_NOT_FOUND = "Không tìm thấy bài học."
EMPTY_ANSWER = "Câu trả lời không được để trống."


class GradeRequest(BaseModel):
    question_id: str
    # max_length guards a pathological payload; the emptiness check is in the
    # handler so the message can be Vietnamese (Pydantic's would not be).
    user_answer: str = Field(max_length=5000)


class GradeOut(BaseModel):
    score: float
    missing_points: list[str]
    comment: str
    created_at: str


class AttemptOut(BaseModel):
    question_id: str
    user_answer: str
    score: float
    missing_points: list[str]
    comment: str
    created_at: str


class _Repo:
    """Thin data layer on the service-role client. Every query filters user_id."""

    def get_question(self, user_id: str, question_id: str) -> dict | None:
        result = (
            db.admin()
            .table("questions")
            .select("id, lesson_id, question_text, type")
            .eq("id", question_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_lesson_content(self, user_id: str, lesson_id: str) -> dict | None:
        result = (
            db.admin()
            .table("lessons")
            .select("content_md")
            .eq("id", lesson_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_lesson_by_slug(self, user_id: str, slug: str) -> dict | None:
        result = (
            db.admin()
            .table("lessons")
            .select("id")
            .eq("user_id", user_id)
            .eq("slug", slug)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def list_lesson_question_ids(self, user_id: str, lesson_id: str) -> list[str]:
        result = (
            db.admin()
            .table("questions")
            .select("id")
            .eq("user_id", user_id)
            .eq("lesson_id", lesson_id)
            .execute()
        )
        return [row["id"] for row in (result.data or [])]

    def list_question_attempts(self, user_id: str, question_id: str) -> list[dict]:
        result = (
            db.admin()
            .table("quiz_attempts")
            .select("*")
            .eq("user_id", user_id)
            .eq("question_id", question_id)
            .execute()
        )
        return result.data or []

    def insert_attempt(self, row: dict) -> None:
        db.admin().table("quiz_attempts").insert(row).execute()

    def get_daily(self, user_id: str, activity_date: str) -> dict | None:
        result = (
            db.admin()
            .table("daily_activity")
            .select("questions_done_count")
            .eq("user_id", user_id)
            .eq("activity_date", activity_date)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def upsert_daily(self, values: dict) -> None:
        db.admin().table("daily_activity").upsert(
            values, on_conflict="user_id,activity_date"
        ).execute()


repo = _Repo()


def _attempt_date(attempt: dict):
    """UTC date of an attempt's created_at (ISO string with offset)."""
    return datetime.fromisoformat(attempt["created_at"]).astimezone(timezone.utc).date()


@router.post("/grade", response_model=GradeOut)
def grade(body: GradeRequest, user: CurrentUser = Depends(get_current_user)):
    answer = body.user_answer.strip()
    if not answer:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, EMPTY_ANSWER)

    question = repo.get_question(user.user_id, body.question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, QUESTION_NOT_FOUND)

    lesson = repo.get_lesson_content(user.user_id, question["lesson_id"])
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, LESSON_NOT_FOUND)

    try:
        result = grade_answer(
            lesson["content_md"], question["question_text"], question["type"], answer
        )
    except GradingError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    # Count attempts BEFORE inserting -- otherwise the new row makes the count
    # >=1 and questions_done_count would never increment.
    today = datetime.now(timezone.utc).date()
    prior = repo.list_question_attempts(user.user_id, body.question_id)
    first_today = not any(_attempt_date(a) == today for a in prior)

    created_at = datetime.now(timezone.utc).isoformat()
    repo.insert_attempt(
        {
            "id": str(uuid.uuid4()),
            "user_id": user.user_id,
            "question_id": body.question_id,
            "user_answer": answer,
            "ai_score": result.score,
            "ai_feedback": {
                "missing_points": result.missing_points,
                "comment": result.comment,
            },
            "created_at": created_at,
        }
    )

    if first_today:
        date_str = today.isoformat()
        existing = repo.get_daily(user.user_id, date_str)
        count = (existing["questions_done_count"] if existing else 0) + 1
        repo.upsert_daily(
            {
                "user_id": user.user_id,
                "activity_date": date_str,
                "questions_done_count": count,
            }
        )

    return GradeOut(
        score=result.score,
        missing_points=result.missing_points,
        comment=result.comment,
        created_at=created_at,
    )
```

- [ ] **Step 4: Đăng ký router trong `main.py`**

Trong `backend/app/main.py`, thêm `quiz` vào import các router và include nó.

Đổi dòng import:

```python
from app.routers import files, health, lessons, me
```

thành:

```python
from app.routers import files, health, lessons, me, quiz
```

Và thêm sau `app.include_router(lessons.router)`:

```python
app.include_router(quiz.router)
```

- [ ] **Step 5: Chạy repo test — phải pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_quiz_repo.py -v`
Expected: PASS.

- [ ] **Step 6: Viết test cho endpoint**

Create `backend/tests/test_quiz_api.py`:

```python
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
```

- [ ] **Step 7: Chạy endpoint test — phải pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_quiz_api.py -v`
Expected: PASS.

- [ ] **Step 8: Full suite — xanh, sạch**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS toàn bộ, không warning.

- [ ] **Step 9: Commit**

```bash
git add backend/app/routers/quiz.py backend/app/main.py backend/tests/test_quiz_api.py backend/tests/test_quiz_repo.py
git commit -m "feat(api): POST /api/quiz/grade (grade, save attempt, daily activity)"
```

---

### Task 3: `GET /api/quiz/attempts/{lesson_slug}`

**Files:**
- Modify: `backend/app/routers/quiz.py`
- Test: `backend/tests/test_quiz_api.py` (mở rộng), `backend/tests/test_quiz_repo.py` (mở rộng)

**Interfaces:**
- Consumes: `_Repo.get_lesson_by_slug`, `_Repo.list_lesson_question_ids`, `_Repo.list_question_attempts` (đã có ở Task 2); `AttemptOut` (đã có ở Task 2).
- Produces: `GET /api/quiz/attempts/{lesson_slug}` → `response_model=list[AttemptOut]`, mới-nhất-mỗi-câu.

- [ ] **Step 1: Viết test repo cho `list_lesson_question_ids` + `get_lesson_by_slug`**

Thêm vào `backend/tests/test_quiz_repo.py`:

```python
def test_list_lesson_question_ids_scoped_to_user_and_lesson(stores):
    stores["questions"]["q1"] = {"id": "q1", "user_id": USER_ID, "lesson_id": "l1"}
    stores["questions"]["q2"] = {"id": "q2", "user_id": USER_ID, "lesson_id": "l2"}
    stores["questions"]["q9"] = {"id": "q9", "user_id": OTHER_USER_ID, "lesson_id": "l1"}
    repo = quiz_router._Repo()

    assert repo.list_lesson_question_ids(USER_ID, "l1") == ["q1"]


def test_get_lesson_by_slug_scoped_to_user(stores):
    stores["lessons"]["l1"] = {"id": "l1", "user_id": USER_ID, "slug": "gt-0"}
    repo = quiz_router._Repo()

    assert repo.get_lesson_by_slug(USER_ID, "gt-0")["id"] == "l1"
    assert repo.get_lesson_by_slug(OTHER_USER_ID, "gt-0") is None
```

- [ ] **Step 2: Viết test cho endpoint attempts**

Thêm vào `backend/tests/test_quiz_api.py`:

```python
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
```

Cập nhật `_FakeRepo` trong `test_quiz_api.py` — thêm hai method nó chưa có:

```python
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
```

(Thêm chúng vào class `_FakeRepo` cạnh các method khác. Các lesson dict trong test cũ không có `slug`/`content_md` đủ dùng — test attempts tự set lại `repo.lessons`.)

- [ ] **Step 3: Chạy test — phải fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_quiz_api.py::test_attempts_returns_latest_per_question -v`
Expected: FAIL — 404 hoặc route không tồn tại (`405`/`404`) vì endpoint chưa có.

- [ ] **Step 4: Viết endpoint attempts**

Thêm vào cuối `backend/app/routers/quiz.py`:

```python
@router.get("/attempts/{lesson_slug}", response_model=list[AttemptOut])
def attempts(lesson_slug: str, user: CurrentUser = Depends(get_current_user)):
    lesson = repo.get_lesson_by_slug(user.user_id, lesson_slug)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, LESSON_NOT_FOUND)

    out: list[dict] = []
    for question_id in repo.list_lesson_question_ids(user.user_id, lesson["id"]):
        rows = repo.list_question_attempts(user.user_id, question_id)
        if not rows:
            continue
        # created_at is a UTC ISO string (offset +00:00), so lexicographic max
        # is chronological max -- the latest attempt.
        latest = max(rows, key=lambda r: r["created_at"])
        feedback = latest.get("ai_feedback") or {}
        out.append(
            {
                "question_id": question_id,
                "user_answer": latest["user_answer"],
                "score": latest["ai_score"],
                "missing_points": feedback.get("missing_points", []),
                "comment": feedback.get("comment", ""),
                "created_at": latest["created_at"],
            }
        )
    return out
```

- [ ] **Step 5: Chạy test — phải pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_quiz_api.py tests/test_quiz_repo.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 6: Full suite — xanh, sạch**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS toàn bộ, không warning.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/quiz.py backend/tests/test_quiz_api.py backend/tests/test_quiz_repo.py
git commit -m "feat(api): GET /api/quiz/attempts/{slug} (latest attempt per question)"
```

---

### Task 4: Frontend quiz lib

**Files:**
- Create: `frontend/src/lib/quiz.ts`

**Interfaces:**
- Consumes: `apiFetch` (đã có).
- Produces: `GradeResult`, `Attempt`, `gradeAnswer(questionId, answer)`, `getAttempts(slug)`.

- [ ] **Step 1: Viết lib**

Create `frontend/src/lib/quiz.ts`:

```typescript
import { apiFetch } from "@/lib/api"

export interface GradeResult {
  score: number
  missing_points: string[]
  comment: string
  created_at: string
}

/** Latest graded attempt for one question of a lesson. */
export interface Attempt {
  question_id: string
  user_answer: string
  score: number
  missing_points: string[]
  comment: string
  created_at: string
}

export function gradeAnswer(
  questionId: string,
  answer: string,
): Promise<GradeResult> {
  return apiFetch("/api/quiz/grade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_id: questionId, user_answer: answer }),
  })
}

export function getAttempts(slug: string): Promise<Attempt[]> {
  return apiFetch(`/api/quiz/attempts/${encodeURIComponent(slug)}`)
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run build`
Expected: build thành công, không lỗi TS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/quiz.ts
git commit -m "feat(frontend): quiz API client (grade, attempts)"
```

---

### Task 5: Frontend answer + grade UI

**Files:**
- Modify: `frontend/src/components/ReviewQuestions.tsx`

**Interfaces:**
- Consumes: `gradeAnswer`, `getAttempts`, `Attempt`, `GradeResult` (Task 4); existing `getQuestions`/`regenerateQuestions`/`QUESTION_TYPE_LABELS`/`ReviewQuestion` and `errorMessage`.

- [ ] **Step 1: Thay toàn bộ `ReviewQuestions.tsx`**

Bài toán: mỗi câu có trạng thái riêng (đáp án đang gõ, kết quả chấm/đã nộp, đang chấm, lỗi). Khi tải câu hỏi thì tải kèm attempts để prefill. Thay toàn bộ file `frontend/src/components/ReviewQuestions.tsx` bằng:

```tsx
import { useState } from "react"
import { errorMessage } from "@/lib/files"
import {
  getQuestions,
  regenerateQuestions,
  QUESTION_TYPE_LABELS,
  type ReviewQuestion,
} from "@/lib/lessons"
import { gradeAnswer, getAttempts, type Attempt } from "@/lib/quiz"

/** Per-question result shown after grading (or loaded from a past attempt). */
interface Result {
  score: number
  missing_points: string[]
  comment: string
}

/**
 * Review questions for one lesson, with inline grading (#4). Generation is
 * lazy (first click). For each question the learner types an answer and submits
 * it; the AI score + feedback + missing points show inline. Past attempts are
 * loaded on open so a graded question stays graded across reloads.
 */
export function ReviewQuestions({ slug }: { slug: string }) {
  const [questions, setQuestions] = useState<ReviewQuestion[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Per-question UI state, keyed by question id.
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [results, setResults] = useState<Record<string, Result>>({})
  const [grading, setGrading] = useState<Record<string, boolean>>({})
  const [rowError, setRowError] = useState<Record<string, string>>({})

  async function loadQuestions(regenerate: boolean) {
    setLoading(true)
    setError(null)
    try {
      const data = regenerate
        ? await regenerateQuestions(slug)
        : await getQuestions(slug)
      setQuestions(data)
      // Regenerated questions are brand new -- drop any prior answers/results.
      if (regenerate) {
        setAnswers({})
        setResults({})
        setRowError({})
      } else {
        const attempts = await getAttempts(slug)
        const loaded: Record<string, Result> = {}
        for (const a of attempts) {
          loaded[a.question_id] = {
            score: a.score,
            missing_points: a.missing_points,
            comment: a.comment,
          }
        }
        setResults(loaded)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  async function submit(questionId: string) {
    const answer = (answers[questionId] ?? "").trim()
    if (!answer || grading[questionId]) return
    setGrading((g) => ({ ...g, [questionId]: true }))
    setRowError((e) => ({ ...e, [questionId]: "" }))
    try {
      const result = await gradeAnswer(questionId, answer)
      setResults((r) => ({
        ...r,
        [questionId]: {
          score: result.score,
          missing_points: result.missing_points,
          comment: result.comment,
        },
      }))
    } catch (err) {
      setRowError((e) => ({ ...e, [questionId]: errorMessage(err) }))
    } finally {
      setGrading((g) => ({ ...g, [questionId]: false }))
    }
  }

  function retry(questionId: string) {
    // Clear the shown result so the textarea returns; the answer is kept so the
    // learner can edit rather than retype.
    setResults((r) => {
      const next = { ...r }
      delete next[questionId]
      return next
    })
  }

  return (
    <section className="space-y-4 border-t pt-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">Câu hỏi ôn tập</h2>
        {questions && !loading && (
          <button
            type="button"
            onClick={() => void loadQuestions(true)}
            className="text-sm text-gray-500 underline"
          >
            Sinh lại
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading && <p className="text-sm text-gray-500">Đang tải…</p>}

      {!loading && questions === null && (
        <button
          type="button"
          onClick={() => void loadQuestions(false)}
          className="rounded-md border px-4 py-2 text-sm hover:bg-gray-50"
        >
          Sinh câu hỏi ôn tập
        </button>
      )}

      {!loading && questions !== null && (
        <ol className="space-y-6">
          {questions.map((q) => {
            const result = results[q.id]
            return (
              <li key={q.id} className="space-y-2">
                <div className="space-y-1">
                  <span className="inline-block rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                    {QUESTION_TYPE_LABELS[q.type]}
                  </span>
                  <p className="text-sm font-medium">{q.question_text}</p>
                </div>

                {result ? (
                  <div className="space-y-2 rounded-md border bg-gray-50 p-3">
                    <p className="text-sm font-semibold">Điểm: {result.score}/10</p>
                    {result.comment && (
                      <p className="text-sm">{result.comment}</p>
                    )}
                    {result.missing_points.length > 0 && (
                      <div className="text-sm">
                        <p className="font-medium">Ý còn thiếu:</p>
                        <ul className="list-disc pl-5">
                          {result.missing_points.map((m, i) => (
                            <li key={i}>{m}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => retry(q.id)}
                      className="text-sm text-gray-500 underline"
                    >
                      Làm lại
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <textarea
                      value={answers[q.id] ?? ""}
                      onChange={(e) =>
                        setAnswers((a) => ({ ...a, [q.id]: e.target.value }))
                      }
                      disabled={grading[q.id]}
                      rows={3}
                      className="w-full rounded-md border p-2 text-sm"
                      placeholder="Nhập câu trả lời của bạn…"
                    />
                    {rowError[q.id] && (
                      <p className="text-sm text-red-600">{rowError[q.id]}</p>
                    )}
                    <button
                      type="button"
                      onClick={() => void submit(q.id)}
                      disabled={grading[q.id] || !(answers[q.id] ?? "").trim()}
                      className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
                    >
                      {grading[q.id] ? "Đang chấm…" : "Nộp bài"}
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
```

- [ ] **Step 2: Typecheck + lint**

Run: `cd frontend && npm run build`
Expected: build thành công, không lỗi TS.

Run: `cd frontend && npx oxlint src/components/ReviewQuestions.tsx src/lib/quiz.ts`
Expected: no warnings/errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ReviewQuestions.tsx
git commit -m "feat(frontend): inline answer + AI grading in review questions"
```

---

### Task 6: Live verification + checklist

**Files:**
- Create: `backend/scripts/verify_4.py`
- Modify: `check_list.md`

**Interfaces:**
- Consumes: `mint_access_token` từ `backend/scripts/verify_1b.py`; API trên `http://localhost:8000`; env `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `GEMINI_API_KEY`. Cần ≥1 bài có câu hỏi đã sinh (chạy `verify_4a.py` trước nếu chưa có).

- [ ] **Step 1: Viết script verify**

Create `backend/scripts/verify_4.py`:

```python
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
```

- [ ] **Step 2: Chạy verify thật**

Đảm bảo backend chạy (`cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`) với `GEMINI_API_KEY` trong `backend/.env`, và `SUPABASE_ANON_KEY` trong môi trường. Rồi:

Run: `cd backend && SUPABASE_ANON_KEY=<từ frontend/.env.local VITE_SUPABASE_ANON_KEY> PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/verify_4.py`
Expected: in điểm + feedback, `daily +1` rồi `unchanged`, attempts latest, RLS 0/0, `ALL CHECKS PASSED`.

- [ ] **Step 3: Full backend suite lần cuối**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS toàn bộ, output sạch.

- [ ] **Step 4: Kiểm trình duyệt thủ công**

Với backend + `npm run dev`: mở một bài, sinh câu hỏi, nhập câu trả lời một câu → "Nộp bài" → hiện điểm/nhận xét/ý thiếu; F5 → câu đó vẫn hiện kết quả; "Làm lại" → mở lại ô nhập; tắt backend rồi nộp → báo lỗi tiếng Việt.

- [ ] **Step 5: Cập nhật checklist**

Trong `check_list.md`, mục `### #4 — AI chấm điểm`: đánh dấu `[x]` hai gạch đầu dòng đầu, thêm heading "✅ XONG (2026-07-21)" + khối "Verify thật" với bằng chứng thật (theo khuôn #4a), và ghi `POST /api/quiz/grade` + `GET /api/quiz/attempts/{slug}`.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/verify_4.py check_list.md
git commit -m "test(4): live verification script + mark #4 done"
```

---

## Self-Review

**Spec coverage:**
- §3 data model (no migration; reuse quiz_attempts + daily_activity) → Tasks 2, 3. ✔
- §4 grading module (structured output, score clamp, missing_points list, graceful degradation) → Task 1. ✔
- §5 POST grade (404/422/502, count-before-insert, daily first-of-day, GradeOut) → Task 2. ✔
- §5 GET attempts (latest per question, 404) → Task 3. ✔
- §6 frontend (answer box, submit, result, prefill from attempts, làm lại) → Tasks 4, 5. ✔
- §7 testing (grader/repo fakes + repo isolation + real verify_4) → Tasks 1, 2, 3, 6. ✔
- §9 debt (UTC date; non-atomic daily count) → carried in code comments (`_attempt_date` UTC; count-before-insert comment). ✔

**Placeholder scan:** No TBD/TODO; every code step shows full content. ✔

**Type consistency:** `GradeResult{score,missing_points,comment}` (Task 1) matches grader fakes + `GradeOut` (Task 2) + frontend `GradeResult` (Task 4). `AttemptOut{question_id,user_answer,score,missing_points,comment,created_at}` (Task 2) matches the attempts endpoint (Task 3) + frontend `Attempt` (Task 4). `_Repo` method names identical across router (Task 2/3), `test_quiz_repo.py`, and `_FakeRepo` (Task 2/3). `ai_feedback` shape `{missing_points, comment}` consistent between insert (Task 2) and attempts read (Task 3). ✔

**Note:** `_FakeRepo` in Task 2 lacks `get_lesson_by_slug`/`list_lesson_question_ids`; Task 3 Step 2 adds them before the attempts endpoint tests use them — ordered correctly.
