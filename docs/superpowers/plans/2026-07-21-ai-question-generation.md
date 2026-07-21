# #4a — AI Question Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sinh 5 câu hỏi ôn tập tự luận bằng Gemini từ nội dung một bài học, riêng từng user, cache trong DB, hiển thị read-only dưới bài học.

**Architecture:** Backend thêm module `app/ai/` (client Gemini dùng chung + generator câu hỏi có structured output), bảng `questions` chuyển từ dùng-chung sang riêng-tư-từng-user (migration 0007 + RLS), hai endpoint mới trong `routers/lessons.py` (GET cache-or-generate, POST regenerate). Frontend thêm một section read-only ở trang bài học.

**Tech Stack:** Python + FastAPI, `google-genai` (Gemini `gemini-2.5-flash`), Supabase Postgres + RLS, React + Vite + TypeScript.

## Global Constraints

- Spec nguồn: `docs/superpowers/specs/2026-07-21-ai-question-generation-design.md`. Đọc trước khi bắt đầu.
- Model chat: **`gemini-2.5-flash`** (chốt cứng). Không dùng RAG cho #4a.
- Mọi chuỗi hiển thị cho user = **tiếng Việt**; code/tên biến/comment = **tiếng Anh**.
- `db.admin()` là service-role client **bypass RLS** — mọi truy vấn phải lọc `user_id` tường minh; bài của người khác → **404** (không 403).
- Graceful degradation: lỗi AI KHÔNG được làm sập pipeline — bọc try/catch, trả lỗi tiếng Việt, cho retry. Không nuốt lỗi âm thầm.
- `QUESTION_TYPES` trong `callout_types.py` là nguồn chân lý duy nhất của loại câu hỏi — đồng bộ với CHECK constraint `questions.type`.
- Backend verify: `pytest` từ `backend/` phải **xanh và output sạch** (không warning). Frontend: `npm run build` từ `frontend/` không lỗi TS.
- Secret qua env, không hardcode. Chỉ commit `.env.example`.
- Commit sau mỗi task.

## File Structure

**Tạo mới:**
- `supabase/migrations/0007_questions_per_user.sql` — thêm `user_id` + RLS riêng tư + unique index.
- `backend/app/ai/__init__.py` — package rỗng.
- `backend/app/ai/client.py` — Gemini client dùng chung + hằng `CHAT_MODEL`.
- `backend/app/ai/questions.py` — `generate_questions()` + `GeneratedQuestion` + `QuestionGenerationError`.
- `backend/tests/test_ai_questions.py` — test generator với client giả.
- `backend/tests/test_questions_api.py` — test endpoint với repo giả + generator giả.
- `backend/tests/test_questions_repo.py` — test `_QuestionRepo` query-building với client giả.
- `backend/scripts/verify_4a.py` — kiểm thật (Gemini + Supabase thật).
- `frontend/src/components/ReviewQuestions.tsx` — section câu hỏi read-only.

**Sửa:**
- `backend/app/config/callout_types.py` — bỏ `is_question_type`, thêm `QUESTION_TYPE_DESCRIPTIONS`.
- `backend/app/config/settings.py` — thêm `gemini_api_key()`.
- `backend/app/.env.example` — thêm `GEMINI_API_KEY`.
- `backend/requirements.txt` — thêm `google-genai`.
- `backend/app/routers/lessons.py` — `_QuestionRepo`, `QuestionOut`, 2 endpoint.
- `backend/tests/conftest.py` — `FakeTable` hỗ trợ `.delete()` + insert danh sách.
- `backend/tests/test_settings.py` — test `gemini_api_key()`.
- `frontend/src/lib/lessons.ts` — types + `getQuestions` + `regenerateQuestions` + nhãn loại.
- `frontend/src/pages/LessonDetail.tsx` — render `<ReviewQuestions>`.
- `check_list.md` — đánh dấu #4a xong.

---

### Task 1: Migration 0007 — questions per-user + RLS

**Files:**
- Create: `supabase/migrations/0007_questions_per_user.sql`

**Interfaces:**
- Produces: cột `questions.user_id uuid not null`; unique index `questions_user_lesson_order_idx` trên `(user_id, lesson_id, order_index)`; policy `questions_select_own`. Bảng `questions` giữ cột `type` + CHECK `in ('recall','scenario','compare','explain')`.

- [ ] **Step 1: Viết migration**

Create `supabase/migrations/0007_questions_per_user.sql`:

```sql
-- 0007_questions_per_user.sql
-- Repurpose `questions` from shared content to per-user private (D13):
-- AI generates a review-question set per user from a lesson's content.

alter table questions
  add column user_id uuid references auth.users(id) on delete cascade;

-- The table is empty in production (no questions were ever generated). Any
-- pre-existing row would be orphaned by this model change -- it has no owner --
-- so drop such rows before making user_id mandatory.
delete from questions where user_id is null;

alter table questions alter column user_id set not null;

-- One question set per (user, lesson); order_index is unique within it. Backs
-- the cache lookup and turns a concurrent double-generate into a unique
-- violation (handled in the router) instead of duplicated questions.
create unique index questions_user_lesson_order_idx
  on questions (user_id, lesson_id, order_index);

-- Replace the shared read policy with per-user RLS.
drop policy "questions_select" on questions;
create policy "questions_select_own" on questions
  for select using (auth.uid() = user_id);
```

- [ ] **Step 2: Apply lên Supabase thật**

Áp dụng migration bằng Supabase MCP (`apply_migration`, name `0007_questions_per_user`) hoặc dán SQL vào Supabase SQL Editor. Migration này là nguồn chân lý; production phải chạy nó.

- [ ] **Step 3: Verify cột + policy tồn tại**

Chạy trong Supabase SQL Editor (hoặc `execute_sql`):

```sql
select column_name, is_nullable from information_schema.columns
  where table_name = 'questions' and column_name = 'user_id';
select policyname from pg_policies where tablename = 'questions';
select indexname from pg_indexes where tablename = 'questions';
```

Expected: `user_id | NO`; policy `questions_select_own` (và KHÔNG còn `questions_select`); index `questions_user_lesson_order_idx` có mặt.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0007_questions_per_user.sql
git commit -m "feat(db): questions table per-user with RLS (migration 0007)"
```

---

### Task 2: AI config — enum descriptions, settings key, dependency

**Files:**
- Modify: `backend/app/config/callout_types.py`
- Modify: `backend/app/config/settings.py`
- Modify: `backend/app/.env.example`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_settings.py`

**Interfaces:**
- Produces: `callout_types.QUESTION_TYPES: list[str]` (giữ nguyên), `callout_types.QUESTION_TYPE_DESCRIPTIONS: dict[str, str]`; `settings.gemini_api_key() -> str`.
- Consumes: `settings._required` (đã có).

- [ ] **Step 1: Viết test cho `gemini_api_key`**

Thêm vào `backend/tests/test_settings.py`:

```python
def test_gemini_api_key_is_read_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-secret")
    assert settings.gemini_api_key() == "g-secret"


def test_missing_gemini_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        settings.gemini_api_key()
```

- [ ] **Step 2: Chạy test — phải fail**

Run: `cd backend && python -m pytest tests/test_settings.py -v`
Expected: FAIL — `AttributeError: module 'app.config.settings' has no attribute 'gemini_api_key'`.

- [ ] **Step 3: Thêm `gemini_api_key` vào settings**

Thêm vào cuối `backend/app/config/settings.py`:

```python
def gemini_api_key() -> str:
    return _required("GEMINI_API_KEY")
```

- [ ] **Step 4: Chạy test — phải pass**

Run: `cd backend && python -m pytest tests/test_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Repurpose `callout_types.py`**

Thay toàn bộ `backend/app/config/callout_types.py` bằng:

```python
"""Single source of truth for review question types.

Must stay in sync with the `type` CHECK constraint on the `questions` table
(supabase/migrations/0002_tables.sql). Questions are AI-generated per user from
the lesson content (sub-project #4a); this is the enum the model must choose
from when producing structured output, plus a Vietnamese description of each
type used to steer that choice inside the prompt.
"""

QUESTION_TYPES: list[str] = ["recall", "scenario", "compare", "explain"]

# Shown to the model so it picks a fitting type per question. Keys must match
# QUESTION_TYPES exactly.
QUESTION_TYPE_DESCRIPTIONS: dict[str, str] = {
    "recall": "Nhớ lại một sự kiện, định nghĩa hoặc chi tiết cụ thể trong bài.",
    "scenario": "Áp dụng kiến thức của bài vào một tình huống thực tế mới.",
    "compare": "So sánh hoặc đối chiếu hai khái niệm, cách tiếp cận trong bài.",
    "explain": "Giải thích nguyên nhân, cơ chế hoặc lý do đằng sau một ý trong bài.",
}
```

(Bỏ `is_question_type` — đã kiểm không nơi nào import.)

- [ ] **Step 6: Thêm dependency + env mẫu**

Thêm dòng vào cuối `backend/requirements.txt`:

```
google-genai>=1.0
```

Thêm vào `backend/app/.env.example` (mục AI):

```
# Google Gemini (AI question generation, grading, chat)
GEMINI_API_KEY=your-gemini-api-key
```

Cài đặt vào venv:

Run: `cd backend && pip install -r requirements.txt`
Expected: `google-genai` cài thành công.

- [ ] **Step 7: Chạy full test suite — vẫn xanh, sạch**

Run: `cd backend && python -m pytest -q`
Expected: PASS toàn bộ, không warning (`is_question_type` không có test riêng nên bỏ nó không làm đỏ gì).

- [ ] **Step 8: Commit**

```bash
git add backend/app/config/callout_types.py backend/app/config/settings.py backend/app/.env.example backend/requirements.txt backend/tests/test_settings.py
git commit -m "feat(ai): question-type enum descriptions, GEMINI_API_KEY, google-genai dep"
```

---

### Task 3: Gemini client module

**Files:**
- Create: `backend/app/ai/__init__.py`
- Create: `backend/app/ai/client.py`
- Test: `backend/tests/test_ai_questions.py` (tạo file, phần client)

**Interfaces:**
- Consumes: `settings.gemini_api_key()` (Task 2).
- Produces: `app.ai.client.get_client() -> genai.Client` (lru_cache 1); `app.ai.client.CHAT_MODEL = "gemini-2.5-flash"`.

- [ ] **Step 1: Viết test cho `get_client`**

Create `backend/tests/test_ai_questions.py`:

```python
"""AI question generation: client wiring + generator logic (no real network)."""

import pytest

from app.ai import client as client_module


def test_get_client_uses_the_configured_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    captured = {}

    class FakeGenaiClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key

    monkeypatch.setattr(client_module.genai, "Client", FakeGenaiClient)
    client_module.get_client.cache_clear()

    client_module.get_client()

    assert captured["api_key"] == "test-key"
    client_module.get_client.cache_clear()


def test_chat_model_is_pinned():
    assert client_module.CHAT_MODEL == "gemini-2.5-flash"
```

- [ ] **Step 2: Chạy test — phải fail**

Run: `cd backend && python -m pytest tests/test_ai_questions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ai'`.

- [ ] **Step 3: Tạo package + client**

Create `backend/app/ai/__init__.py` (rỗng).

Create `backend/app/ai/client.py`:

```python
"""Google Gemini client, shared by every AI feature (question gen, grading, chat).

One lazily-built, cached client so the whole backend talks to Gemini the same
way. The model is pinned here so a change is one edit, not a scatter of literals.
"""

import functools

from google import genai

from app.config import settings

CHAT_MODEL = "gemini-2.5-flash"


@functools.lru_cache(maxsize=1)
def get_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key())
```

- [ ] **Step 4: Chạy test — phải pass**

Run: `cd backend && python -m pytest tests/test_ai_questions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/__init__.py backend/app/ai/client.py backend/tests/test_ai_questions.py
git commit -m "feat(ai): shared Gemini client module"
```

---

### Task 4: `generate_questions` — structured output + graceful degradation

**Files:**
- Create: `backend/app/ai/questions.py`
- Test: `backend/tests/test_ai_questions.py` (mở rộng)

**Interfaces:**
- Consumes: `app.ai.client.get_client`, `app.ai.client.CHAT_MODEL`; `callout_types.QUESTION_TYPES`, `callout_types.QUESTION_TYPE_DESCRIPTIONS`.
- Produces:
  - `GeneratedQuestion(BaseModel)` với `type: str`, `question_text: str`.
  - `QuestionGenerationError(Exception)` — mang thông báo tiếng Việt.
  - `generate_questions(content_md: str) -> list[GeneratedQuestion]` — raise `QuestionGenerationError` khi không sinh được.

- [ ] **Step 1: Viết test cho generator**

Thêm vào `backend/tests/test_ai_questions.py`:

```python
from app.ai import questions as questions_module
from app.ai.questions import (
    GeneratedQuestion,
    QuestionGenerationError,
    generate_questions,
)


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


def _patch_client(monkeypatch, models):
    monkeypatch.setattr(questions_module, "get_client", lambda: _FakeClient(models))


def test_generate_returns_validated_questions(monkeypatch):
    payload = (
        '[{"type": "recall", "question_text": "Câu 1?"},'
        ' {"type": "scenario", "question_text": "Câu 2?"}]'
    )
    _patch_client(monkeypatch, _FakeModels(_FakeResponse(payload)))

    result = generate_questions("nội dung bài học")

    assert result == [
        GeneratedQuestion(type="recall", question_text="Câu 1?"),
        GeneratedQuestion(type="scenario", question_text="Câu 2?"),
    ]


def test_generate_drops_items_with_unknown_type(monkeypatch):
    payload = (
        '[{"type": "recall", "question_text": "Giữ lại?"},'
        ' {"type": "bogus", "question_text": "Bỏ đi?"},'
        ' {"type": "explain", "question_text": "   "}]'
    )
    _patch_client(monkeypatch, _FakeModels(_FakeResponse(payload)))

    result = generate_questions("nội dung")

    # Unknown type dropped; blank text dropped; only the valid one survives.
    assert result == [GeneratedQuestion(type="recall", question_text="Giữ lại?")]


def test_generate_raises_when_nothing_valid_survives(monkeypatch):
    payload = '[{"type": "bogus", "question_text": "x"}]'
    _patch_client(monkeypatch, _FakeModels(_FakeResponse(payload)))

    with pytest.raises(QuestionGenerationError):
        generate_questions("nội dung")


def test_generate_raises_on_malformed_json(monkeypatch):
    _patch_client(monkeypatch, _FakeModels(_FakeResponse("not json")))

    with pytest.raises(QuestionGenerationError):
        generate_questions("nội dung")


def test_generate_raises_when_the_api_call_fails(monkeypatch):
    _patch_client(monkeypatch, _FakeModels(raise_exc=RuntimeError("quota")))

    with pytest.raises(QuestionGenerationError):
        generate_questions("nội dung")


def test_generate_rejects_empty_content_without_calling_the_model(monkeypatch):
    models = _FakeModels(_FakeResponse("[]"))
    _patch_client(monkeypatch, models)

    with pytest.raises(QuestionGenerationError):
        generate_questions("   ")

    assert models.calls == 0
```

- [ ] **Step 2: Chạy test — phải fail**

Run: `cd backend && python -m pytest tests/test_ai_questions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ai.questions'`.

- [ ] **Step 3: Viết `questions.py`**

Create `backend/app/ai/questions.py`:

```python
"""Generate review questions for one lesson via Gemini structured output (#4a).

No RAG: a lesson is small enough to put whole in the prompt (D13). Any failure
(network, quota, malformed output) raises QuestionGenerationError carrying a
Vietnamese message -- it never returns junk and never crashes the request.
"""

import json
import logging

from pydantic import BaseModel

from app.ai.client import CHAT_MODEL, get_client
from app.config.callout_types import QUESTION_TYPE_DESCRIPTIONS, QUESTION_TYPES

logger = logging.getLogger(__name__)

QUESTION_COUNT = 5
_FAILURE_MESSAGE = "Không sinh được câu hỏi lúc này. Vui lòng thử lại."


class GeneratedQuestion(BaseModel):
    type: str
    question_text: str


class QuestionGenerationError(Exception):
    """Model call or its output could not yield usable questions.

    Its message is Vietnamese and safe to surface to the user.
    """


# JSON Schema handed to Gemini so `type` is constrained to the enum and every
# item carries both fields. Kept as a plain dict (not a Pydantic type) so the
# `enum` maps straight onto QUESTION_TYPES, the single source of truth.
_RESPONSE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": QUESTION_TYPES},
            "question_text": {"type": "string"},
        },
        "required": ["type", "question_text"],
    },
}


def _build_prompt(content_md: str) -> str:
    types_block = "\n".join(
        f"- {name}: {desc}" for name, desc in QUESTION_TYPE_DESCRIPTIONS.items()
    )
    return (
        "Bạn là trợ giảng. Chỉ dựa trên nội dung bài học dưới đây, hãy soạn "
        f"{QUESTION_COUNT} câu hỏi ôn tập tự luận (không phải trắc nghiệm) bằng "
        "tiếng Việt để kiểm tra mức độ hiểu bài của người học.\n\n"
        "Mỗi câu hỏi chọn một loại phù hợp trong các loại sau:\n"
        f"{types_block}\n\n"
        "Yêu cầu: phủ ít nhất 3 trong 4 loại trên; câu hỏi bám sát nội dung, "
        "không hỏi những điều bài không đề cập.\n\n"
        "----- NỘI DUNG BÀI HỌC -----\n"
        f"{content_md}"
    )


def _validate(raw: object) -> list[GeneratedQuestion]:
    """Keep only well-formed items: a known type and non-empty text.

    Diversity ("cover >=3 types") is asked of the model in the prompt but NOT
    enforced here -- a soft requirement must not turn a usable set into a hard
    failure. The hard floor is checked by the caller: at least one item survives.
    """
    if not isinstance(raw, list):
        return []
    valid: list[GeneratedQuestion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        qtype = item.get("type")
        text = item.get("question_text")
        if qtype in QUESTION_TYPES and isinstance(text, str) and text.strip():
            valid.append(GeneratedQuestion(type=qtype, question_text=text.strip()))
    return valid


def generate_questions(content_md: str) -> list[GeneratedQuestion]:
    if not content_md or not content_md.strip():
        raise QuestionGenerationError("Bài học không có nội dung để sinh câu hỏi.")

    try:
        response = get_client().models.generate_content(
            model=CHAT_MODEL,
            contents=_build_prompt(content_md),
            config={
                "response_mime_type": "application/json",
                "response_schema": _RESPONSE_SCHEMA,
            },
        )
        raw = json.loads(response.text)
    except Exception as exc:  # network, quota, malformed JSON, missing .text
        logger.exception("Gemini question generation failed")
        raise QuestionGenerationError(_FAILURE_MESSAGE) from exc

    questions = _validate(raw)
    if not questions:
        raise QuestionGenerationError(_FAILURE_MESSAGE)
    return questions
```

- [ ] **Step 4: Chạy test — phải pass**

Run: `cd backend && python -m pytest tests/test_ai_questions.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/questions.py backend/tests/test_ai_questions.py
git commit -m "feat(ai): generate_questions with structured output + graceful degradation"
```

---

### Task 5: Questions repo + API endpoints

**Files:**
- Modify: `backend/app/routers/lessons.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_questions_api.py` (create)
- Test: `backend/tests/test_questions_repo.py` (create)

**Interfaces:**
- Consumes: `repo.get_lesson_by_slug(user_id, slug) -> dict | None` (đã có, trả cả `id` và `content_md`); `generate_questions` + `QuestionGenerationError` (Task 4).
- Produces:
  - `QuestionOut(BaseModel)`: `id: str`, `type: str`, `question_text: str`, `order_index: int`.
  - `_QuestionRepo` với `list_questions(user_id, lesson_id) -> list[dict]`, `insert_questions(rows: list[dict]) -> None`, `delete_questions(user_id, lesson_id) -> None`; instance module-level `question_repo`.
  - `GET /api/lessons/{slug}/questions` và `POST /api/lessons/{slug}/questions/regenerate`, cả hai `response_model=list[QuestionOut]`.

- [ ] **Step 1: Mở rộng `FakeTable` hỗ trợ delete + insert danh sách**

Trong `backend/tests/conftest.py`, thêm `.delete()` và cho `insert`/`execute` xử lý danh sách rows.

Trong `FakeTable.__init__`, sau dòng `self._insert_values = None` thêm:

```python
        self._delete = False
```

Thêm method (cạnh `update`):

```python
    def delete(self):
        self._delete = True
        return self
```

Trong `FakeTable.execute`, thay nhánh insert hiện tại:

```python
        if self._insert_values is not None:
            self._store[self._insert_values["id"]] = dict(self._insert_values)
            return type("Res", (), {"data": [dict(self._insert_values)]})()
```

bằng (xử lý cả một dict lẫn một list rows):

```python
        if self._insert_values is not None:
            rows = (
                self._insert_values
                if isinstance(self._insert_values, list)
                else [self._insert_values]
            )
            for row in rows:
                self._store[row["id"]] = dict(row)
            return type("Res", (), {"data": [dict(r) for r in rows]})()
```

Ngay trước nhánh `if self._update_values is not None:` thêm nhánh delete:

```python
        if self._delete:
            matches = self._matches()
            for row in matches:
                self._store.pop(row["id"], None)
            return type("Res", (), {"data": [dict(r) for r in matches]})()
```

- [ ] **Step 2: Viết test cho `_QuestionRepo`**

Create `backend/tests/test_questions_repo.py`:

```python
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
```

- [ ] **Step 3: Chạy test — phải fail**

Run: `cd backend && python -m pytest tests/test_questions_repo.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_QuestionRepo'`.

- [ ] **Step 4: Thêm `_QuestionRepo`, `QuestionOut`, endpoints vào `lessons.py`**

Ở đầu `backend/app/routers/lessons.py`, thêm import `uuid` và các import AI (cạnh các import hiện có):

```python
import uuid
```

```python
from app.ai.questions import QuestionGenerationError, generate_questions
```

Thêm model (cạnh `ProgressOut`):

```python
class QuestionOut(BaseModel):
    id: str
    type: str
    question_text: str
    order_index: int
```

Thêm lớp repo + instance (sau `repo = _Repo()`):

```python
class _QuestionRepo:
    """Data layer for per-user review questions.

    Service-role client (bypasses RLS), so every query filters user_id
    explicitly -- see _Repo for the same discipline.
    """

    def list_questions(self, user_id: str, lesson_id: str) -> list[dict]:
        result = (
            db.admin()
            .table("questions")
            .select("id, type, question_text, order_index")
            .eq("user_id", user_id)
            .eq("lesson_id", lesson_id)
            .order("order_index")
            .execute()
        )
        return result.data or []

    def insert_questions(self, rows: list[dict]) -> None:
        db.admin().table("questions").insert(rows).execute()

    def delete_questions(self, user_id: str, lesson_id: str) -> None:
        db.admin().table("questions").delete().eq("user_id", user_id).eq(
            "lesson_id", lesson_id
        ).execute()


question_repo = _QuestionRepo()
```

Thêm helper + hai endpoint (cuối file):

```python
def _build_question_rows(
    user_id: str, lesson_id: str, generated: list
) -> list[dict]:
    """Generated questions -> rows to insert, ids minted here (like files.py)
    so the response never has to round-trip the DB to learn them."""
    return [
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "lesson_id": lesson_id,
            "type": q.type,
            "question_text": q.question_text,
            "order_index": index,
        }
        for index, q in enumerate(generated)
    ]


@router.get("/{slug}/questions", response_model=list[QuestionOut])
def get_questions(slug: str, user: CurrentUser = Depends(get_current_user)):
    lesson = repo.get_lesson_by_slug(user.user_id, slug)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    existing = question_repo.list_questions(user.user_id, lesson["id"])
    if existing:
        return existing

    content = lesson.get("content_md") or ""
    if not content.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Bài học không có nội dung để sinh câu hỏi.",
        )

    try:
        generated = generate_questions(content)
    except QuestionGenerationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    rows = _build_question_rows(user.user_id, lesson["id"], generated)
    try:
        question_repo.insert_questions(rows)
    except Exception:
        # Lost a race with a concurrent first-open (unique index collision) or
        # a transient write error. If the other writer's rows landed, return
        # those instead of double-generating; otherwise surface the failure.
        raced = question_repo.list_questions(user.user_id, lesson["id"])
        if raced:
            return raced
        raise
    return rows


@router.post("/{slug}/questions/regenerate", response_model=list[QuestionOut])
def regenerate_questions(slug: str, user: CurrentUser = Depends(get_current_user)):
    lesson = repo.get_lesson_by_slug(user.user_id, slug)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    content = lesson.get("content_md") or ""
    if not content.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Bài học không có nội dung để sinh câu hỏi.",
        )

    # Generate BEFORE deleting: if the model fails, the old set is still there.
    try:
        generated = generate_questions(content)
    except QuestionGenerationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    question_repo.delete_questions(user.user_id, lesson["id"])
    rows = _build_question_rows(user.user_id, lesson["id"], generated)
    question_repo.insert_questions(rows)
    return rows
```

- [ ] **Step 5: Viết test cho endpoints**

Create `backend/tests/test_questions_api.py`:

```python
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


def test_questions_require_a_token(fakes):
    assert client.get("/api/lessons/gt-0/questions").status_code == 401
    assert client.post("/api/lessons/gt-0/questions/regenerate").status_code == 401
```

- [ ] **Step 6: Chạy test — phải pass**

Run: `cd backend && python -m pytest tests/test_questions_api.py tests/test_questions_repo.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 7: Full suite — xanh, sạch**

Run: `cd backend && python -m pytest -q`
Expected: PASS toàn bộ (gồm các test cũ — conftest sửa phải tương thích ngược), không warning.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/lessons.py backend/tests/conftest.py backend/tests/test_questions_api.py backend/tests/test_questions_repo.py
git commit -m "feat(api): per-user question generation endpoints (get cache-or-generate, regenerate)"
```

---

### Task 6: Frontend lib — questions client

**Files:**
- Modify: `frontend/src/lib/lessons.ts`

**Interfaces:**
- Consumes: `apiFetch` (đã có).
- Produces: `QuestionType`, `ReviewQuestion`, `getQuestions(slug)`, `regenerateQuestions(slug)`, `QUESTION_TYPE_LABELS`.

- [ ] **Step 1: Thêm types + hàm gọi API**

Thêm vào cuối `frontend/src/lib/lessons.ts`:

```typescript
export type QuestionType = "recall" | "scenario" | "compare" | "explain"

export interface ReviewQuestion {
  id: string
  type: QuestionType
  question_text: string
  order_index: number
}

/** Vietnamese badge label per question type. */
export const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  recall: "Ghi nhớ",
  scenario: "Tình huống",
  compare: "So sánh",
  explain: "Giải thích",
}

/** Cached-or-generate: the backend generates on first call, then serves from DB. */
export function getQuestions(slug: string): Promise<ReviewQuestion[]> {
  return apiFetch(`/api/lessons/${encodeURIComponent(slug)}/questions`)
}

export function regenerateQuestions(slug: string): Promise<ReviewQuestion[]> {
  return apiFetch(
    `/api/lessons/${encodeURIComponent(slug)}/questions/regenerate`,
    { method: "POST" },
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run build`
Expected: build thành công, không lỗi TS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/lessons.ts
git commit -m "feat(frontend): questions API client (get, regenerate, type labels)"
```

---

### Task 7: Frontend — read-only questions section

**Files:**
- Create: `frontend/src/components/ReviewQuestions.tsx`
- Modify: `frontend/src/pages/LessonDetail.tsx`

**Interfaces:**
- Consumes: `getQuestions`, `regenerateQuestions`, `ReviewQuestion`, `QUESTION_TYPE_LABELS` (Task 6); `errorMessage` (`@/lib/files`).
- Produces: component `ReviewQuestions({ slug }: { slug: string })`.

- [ ] **Step 1: Viết component**

Create `frontend/src/components/ReviewQuestions.tsx`:

```tsx
import { useState } from "react"
import { errorMessage } from "@/lib/files"
import {
  getQuestions,
  regenerateQuestions,
  QUESTION_TYPE_LABELS,
  type ReviewQuestion,
} from "@/lib/lessons"

/**
 * Read-only review questions for one lesson. Generation is lazy: nothing is
 * fetched until the user asks (first click), matching the backend's
 * cache-or-generate contract. Answering + grading is #4, not here.
 */
export function ReviewQuestions({ slug }: { slug: string }) {
  const [questions, setQuestions] = useState<ReviewQuestion[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load(regenerate: boolean) {
    setLoading(true)
    setError(null)
    try {
      const data = regenerate
        ? await regenerateQuestions(slug)
        : await getQuestions(slug)
      setQuestions(data)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-4 border-t pt-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">Câu hỏi ôn tập</h2>
        {questions && !loading && (
          <button
            type="button"
            onClick={() => void load(true)}
            className="text-sm text-gray-500 underline"
          >
            Sinh lại
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading && (
        <p className="text-sm text-gray-500">Đang sinh câu hỏi…</p>
      )}

      {!loading && questions === null && (
        <button
          type="button"
          onClick={() => void load(false)}
          className="rounded-md border px-4 py-2 text-sm hover:bg-gray-50"
        >
          Sinh câu hỏi ôn tập
        </button>
      )}

      {!loading && questions !== null && (
        <ol className="space-y-3">
          {questions.map((q) => (
            <li key={q.id} className="space-y-1">
              <span className="inline-block rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {QUESTION_TYPE_LABELS[q.type]}
              </span>
              <p className="text-sm">{q.question_text}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
```

- [ ] **Step 2: Render trong LessonDetail**

Trong `frontend/src/pages/LessonDetail.tsx`:

Thêm import (cạnh các import hiện có):

```tsx
import { ReviewQuestions } from "@/components/ReviewQuestions"
```

Ngay sau `</article>` (dòng đóng thẻ article, trước `<nav ...>`), chèn:

```tsx
      {slug && <ReviewQuestions slug={slug} />}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run build`
Expected: build thành công, không lỗi TS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ReviewQuestions.tsx frontend/src/pages/LessonDetail.tsx
git commit -m "feat(frontend): read-only review questions section on lesson page"
```

---

### Task 8: Live verification + checklist

**Files:**
- Create: `backend/scripts/verify_4a.py`
- Modify: `check_list.md`

**Interfaces:**
- Consumes: `mint_access_token` từ `backend/scripts/verify_1b.py` (đã có, dùng lại như `verify_3.py`); API chạy ở `http://localhost:8000`; env `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `GEMINI_API_KEY`.

- [ ] **Step 1: Viết script verify thật**

Create `backend/scripts/verify_4a.py`:

```python
"""One-off live end-to-end check of #4a: generate -> cache -> regenerate + RLS.

Hits the real API (which calls real Gemini) and the real Supabase, using the
ADMIN account. Checks what only a live run can establish:

  * GET .../questions on a fresh lesson generates a set (>=1 valid question,
    >=3 distinct types) and persists it.
  * a second GET returns the SAME set without creating new rows (cache hit).
  * POST .../regenerate replaces the set.
  * the anon key reads 0 rows from `questions` (RLS is really on).
  * whatever this script wrote is removed again.

Usage: PYTHONIOENCODING=utf-8 python scripts/verify_4a.py
Requires the API on http://localhost:8000 and at least one confirmed lesson on
the ADMIN_EMAIL account. Needs SUPABASE_ANON_KEY in the environment (it lives in
frontend/.env.local, not backend/.env).
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


def main() -> int:
    token = mint_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    base = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    lessons = httpx.get(f"{API}/api/lessons", headers=headers, timeout=30).json()
    if not lessons:
        print("FAIL: no lessons on this account; confirm a file first (#1b).")
        return 1
    target = lessons[0]
    slug, lesson_id = target["slug"], target["id"]
    print(f"target lesson: [{target['title']}] slug={slug}")

    # Clean slate for this lesson so "generate on cache miss" is what we test.
    httpx.request(
        "DELETE",
        f"{base}/rest/v1/questions",
        params={"lesson_id": f"eq.{lesson_id}"},
        headers=_db_headers(service_key),
        timeout=30,
    )

    first = httpx.get(
        f"{API}/api/lessons/{slug}/questions", headers=headers, timeout=120
    ).json()
    print(f"\nGET .../questions (cache miss) -> {len(first)} questions")
    for q in first:
        print(f"  [{q['type']}] {q['question_text']}")
    assert len(first) >= 1, "no questions generated"
    types = {q["type"] for q in first}
    assert len(types) >= 3, f"expected >=3 distinct types, got {sorted(types)}"

    second = httpx.get(
        f"{API}/api/lessons/{slug}/questions", headers=headers, timeout=120
    ).json()
    assert [q["id"] for q in second] == [q["id"] for q in first], "cache miss on 2nd GET"
    print("2nd GET returned the SAME ids (cache hit, no regeneration)")

    db_rows = httpx.get(
        f"{base}/rest/v1/questions",
        params={"lesson_id": f"eq.{lesson_id}", "select": "id"},
        headers=_db_headers(service_key),
        timeout=30,
    ).json()
    assert len(db_rows) == len(first), "DB row count differs from response"
    print(f"DB has {len(db_rows)} rows for this lesson (matches response)")

    regen = httpx.post(
        f"{API}/api/lessons/{slug}/questions/regenerate", headers=headers, timeout=120
    ).json()
    print(f"\nPOST .../regenerate -> {len(regen)} questions")
    assert {q["id"] for q in regen}.isdisjoint({q["id"] for q in first}), (
        "regenerate reused old ids"
    )

    anon = httpx.get(
        f"{base}/rest/v1/questions",
        params={"select": "id"},
        headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
        timeout=30,
    ).json()
    print(f"anon key sees {len(anon)} questions rows (must be 0)")
    assert anon == [], "RLS is NOT protecting questions"

    # Leave the account exactly as found.
    httpx.request(
        "DELETE",
        f"{base}/rest/v1/questions",
        params={"lesson_id": f"eq.{lesson_id}"},
        headers=_db_headers(service_key),
        timeout=30,
    )
    print("cleaned up the questions this script wrote")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Chạy verify thật**

Đảm bảo backend đang chạy (`cd backend && python -m uvicorn app.main:app --port 8000`) và `SUPABASE_ANON_KEY` có trong môi trường. Rồi:

Run: `cd backend && PYTHONIOENCODING=utf-8 python scripts/verify_4a.py`
Expected: in ra các câu hỏi, `ALL CHECKS PASSED`. Nếu fail vì Gemini trả <3 loại một cách bất thường, chạy lại một lần; nếu vẫn xảy ra, xem lại prompt (`_build_prompt`).

- [ ] **Step 3: Chạy full backend suite lần cuối**

Run: `cd backend && python -m pytest -q`
Expected: PASS toàn bộ, output sạch.

- [ ] **Step 4: Kiểm trình duyệt thủ công**

Với backend + `npm run dev` chạy: mở một bài ở `/lessons/:slug`, bấm "Sinh câu hỏi ôn tập" → hiện spinner rồi 5 câu kèm badge loại; F5 → bấm lại hiện ngay từ cache; bấm "Sinh lại" → bộ mới; tắt backend rồi bấm → báo lỗi tiếng Việt.

- [ ] **Step 5: Cập nhật checklist**

Trong `check_list.md`, đổi mục `### #4a` — đánh dấu `[x]` cho ba gạch đầu dòng đã làm, ghi chú nhánh + ngày (2026-07-21), và ghi migration là `0007` (không phải 0006), theo đúng khuôn các sub-project đã xong (#1a/#3).

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/verify_4a.py check_list.md
git commit -m "test(4a): live verification script + mark #4a done"
```

---

## Self-Review

**Spec coverage:**
- §2 Data model (user_id + RLS + unique index) → Task 1. ✔
- §4.1 client + settings + dep → Tasks 2, 3. ✔
- §4.2 generate_questions (schema, prompt, diversity-in-prompt, graceful degradation, soft/hard constraints) → Task 4. ✔
- §5 callout_types repurpose (drop is_question_type, add descriptions) → Task 2. ✔
- §6 endpoints (GET cache-or-generate, POST regenerate, 404, 502, empty-content guard, dedupe race) → Task 5. ✔
- §7 frontend read-only section → Tasks 6, 7. ✔
- §8 testing (pytest fakes + real verify_4a + RLS check) → Tasks 4, 5, 8. ✔
- §10 debt note (regenerate cascade; delete-then-insert non-atomic — here generate-before-delete removes the strand risk) → carried in code comments. ✔

**Placeholder scan:** No TBD/TODO; every code step shows full content. ✔

**Type consistency:** `QuestionOut{id,type,question_text,order_index}` matches `_build_question_rows` keys and `ReviewQuestion` (frontend). `generate_questions -> list[GeneratedQuestion]`, `.type`/`.question_text` used consistently in Task 5. `_QuestionRepo` method names (`list_questions`/`insert_questions`/`delete_questions`) identical across router, repo test, and api test fakes. `get_client`/`CHAT_MODEL` consistent Tasks 3–4. ✔

**Note on migration number:** spec §3 and this plan use `0007` (checklist's "0006" predates #1a, which already took 0006).
