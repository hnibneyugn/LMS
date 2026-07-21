# Socratic Chatbot (#5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mỗi bài học có một trợ giảng AI Socratic thuần trong panel trượt từ phải; hội thoại lưu bền vững một cuộc / (user, bài), reply stream về theo token.

**Architecture:** Ba lớp tách bạch như các sub-project trước: `ai/chat.py` (chỉ Gemini + prompt, trả iterator chunk) ← `routers/chat.py` (verify sở hữu bài, load/lưu `chat_sessions`, ghép stream) ← `ChatPanel.tsx` (UI, gọi qua `lib/chat.ts`). Streaming qua FastAPI `StreamingResponse`; lỗi AI up-front → 502, lỗi giữa stream → dừng êm nhưng vẫn lưu phần đã nhận.

**Tech Stack:** Python + FastAPI, google-genai (`generate_content_stream`, model `gemini-3.1-flash-lite`), Supabase (service-role client + RLS), React + Vite + TypeScript, `react-markdown` + `remark-gfm`.

## Global Constraints

- Model chat = `gemini-3.1-flash-lite`, gọi qua `app.ai.client.get_client()` / `CHAT_MODEL` (dùng chung — không hardcode literal khác).
- Chuỗi hiển thị cho user = **tiếng Việt**; code/tên biến/comment = **tiếng Anh**.
- Cách ly dữ liệu: `_Repo` dùng service-role client (bypass RLS) → **mọi query lọc `user_id` tường minh**; bài của người khác → **404** (không 403).
- Graceful degradation: AI lỗi KHÔNG làm sập request; luôn try/except, thông báo tiếng Việt, không nuốt lỗi (`logger.exception`).
- Không thêm dependency mới (backend hay frontend).
- Backend verify: `pytest` từ `backend/` xanh và **output sạch** (không warning). Frontend: `npm run build` + `oxlint` sạch.
- Mọi route riêng tư dùng `Depends(get_current_user)`.
- Endpoint keyed by `lesson_id` (UUID), không phải slug.

---

### Task 1: Migration 0008 — unique index trên `chat_sessions`

**Files:**
- Create: `supabase/migrations/0008_chat_sessions_unique.sql`

**Interfaces:**
- Produces: ràng buộc "một `chat_sessions` / (user_id, lesson_id)" mà load-or-create ở Task 3 dựa vào.

- [ ] **Step 1: Viết file migration**

`supabase/migrations/0008_chat_sessions_unique.sql`:

```sql
-- 0008_chat_sessions_unique.sql
-- One persistent Socratic chat per (user, lesson) — see #5 D-chat-3.
-- The table (0002) has only `id` as PK, so two concurrent first-messages could
-- create two rows. This unique index makes load-or-create race-safe.
create unique index if not exists chat_sessions_user_lesson_idx
  on chat_sessions (user_id, lesson_id);
```

- [ ] **Step 2: Apply lên Supabase thật**

Dùng MCP `mcp__supabase__apply_migration` với name `chat_sessions_unique` và nội dung SQL trên (hoặc `supabase db push` nếu chạy CLI). Bảng đang rỗng nên không có xung đột dữ liệu.

- [ ] **Step 3: Verify index tồn tại**

Chạy qua `mcp__supabase__execute_sql`:

```sql
select indexname from pg_indexes
where tablename = 'chat_sessions' and indexname = 'chat_sessions_user_lesson_idx';
```

Expected: đúng 1 dòng `chat_sessions_user_lesson_idx`.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0008_chat_sessions_unique.sql
git commit -m "feat(5): migration 0008 — unique (user_id, lesson_id) on chat_sessions"
```

---

### Task 2: `app/ai/chat.py` — Socratic streaming module

**Files:**
- Create: `backend/app/ai/chat.py`
- Test: `backend/tests/test_chat.py`

**Interfaces:**
- Consumes: `app.ai.client.get_client`, `app.ai.client.CHAT_MODEL`.
- Produces:
  - `ChatError(Exception)` — message tiếng Việt, an toàn để show.
  - `stream_socratic_reply(content_md: str, history: list[dict], user_message: str) -> Iterator[str]` — yield từng chunk text; mọi lỗi Gemini → `raise ChatError`. `history` là list `{"role": "user"|"assistant", "content": str}` (KHÔNG gồm `user_message`).
  - `_build_system_prompt(content_md: str) -> str` (dùng nội bộ + test).

- [ ] **Step 1: Viết test thất bại** — `backend/tests/test_chat.py`

```python
"""Socratic chat module against a fake Gemini stream client (no network)."""

import pytest

from app.ai import chat as chat_module
from app.ai.chat import ChatError, _build_system_prompt, stream_socratic_reply


class _Chunk:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, chunks=None, raise_exc=None):
        self._chunks = chunks or []
        self._raise = raise_exc
        self.calls = 0
        self.last_kwargs = None

    def generate_content_stream(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._raise is not None:
            raise self._raise
        for c in self._chunks:
            yield _Chunk(c)


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _patch(monkeypatch, models):
    monkeypatch.setattr(chat_module, "get_client", lambda: _FakeClient(models))


def test_system_prompt_embeds_content_and_forbids_direct_answers():
    prompt = _build_system_prompt("NỘI DUNG BÀI ABC")
    assert "NỘI DUNG BÀI ABC" in prompt
    # Socratic: must instruct not to give the answer directly.
    assert "không" in prompt.lower() and "đáp án" in prompt.lower()


def test_stream_yields_each_chunk(monkeypatch):
    models = _FakeModels(chunks=["Bạn nghĩ ", "sao về X?"])
    _patch(monkeypatch, models)

    out = list(stream_socratic_reply("nội dung", [], "câu hỏi"))

    assert out == ["Bạn nghĩ ", "sao về X?"]
    assert models.calls == 1


def test_stream_maps_history_roles_to_gemini_contents(monkeypatch):
    models = _FakeModels(chunks=["ok"])
    _patch(monkeypatch, models)

    history = [
        {"role": "user", "content": "trước"},
        {"role": "assistant", "content": "đáp trước"},
    ]
    list(stream_socratic_reply("nd", history, "mới"))

    contents = models.last_kwargs["contents"]
    roles = [c["role"] for c in contents]
    # assistant -> "model"; the new user message is appended last as "user".
    assert roles == ["user", "model", "user"]
    assert contents[-1]["parts"][0]["text"] == "mới"


def test_stream_raises_chaterror_when_api_fails(monkeypatch):
    _patch(monkeypatch, _FakeModels(raise_exc=RuntimeError("quota")))

    with pytest.raises(ChatError):
        list(stream_socratic_reply("nd", [], "câu hỏi"))


def test_stream_rejects_empty_message(monkeypatch):
    models = _FakeModels(chunks=["x"])
    _patch(monkeypatch, models)

    with pytest.raises(ChatError):
        list(stream_socratic_reply("nd", [], "   "))
    assert models.calls == 0
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd backend && python -m pytest tests/test_chat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ai.chat'`.

- [ ] **Step 3: Viết implementation** — `backend/app/ai/chat.py`

```python
"""Socratic tutor chat for one lesson via Gemini streaming (#5).

No RAG: the whole lesson content goes in the system instruction (D13). The
tutor is strictly Socratic -- it never gives the answer directly, only guiding
questions. Any Gemini failure raises ChatError carrying a Vietnamese message;
it never yields junk and never crashes the request.
"""

import logging
from collections.abc import Iterator

from app.ai.client import CHAT_MODEL, get_client

logger = logging.getLogger(__name__)

_FAILURE_MESSAGE = "Không trả lời được lúc này. Vui lòng thử lại."
_EMPTY_MESSAGE = "Tin nhắn không được để trống."


class ChatError(Exception):
    """Chat call or its stream could not yield a usable reply.

    Its message is Vietnamese and safe to surface to the user.
    """


def _build_system_prompt(content_md: str) -> str:
    return (
        "Bạn là gia sư theo phương pháp Socratic cho một bài học. Chỉ dựa trên "
        "nội dung bài học dưới đây, hãy giúp người học tự hiểu bài.\n\n"
        "QUY TẮC BẮT BUỘC:\n"
        "- TUYỆT ĐỐI KHÔNG đưa ra đáp án hay lời giải trực tiếp. Thay vào đó, đặt "
        "1–2 câu hỏi gợi mở dẫn dắt người học tự rút ra câu trả lời.\n"
        "- Ghi nhận phần người học nói đúng; với chỗ chưa đúng hoặc còn thiếu, chỉ "
        "ra bằng câu hỏi để họ suy nghĩ thêm, đừng nói thẳng kết quả.\n"
        "- Nếu người học hỏi điều ngoài phạm vi bài, lịch sự kéo họ về nội dung bài.\n"
        "- Trả lời ngắn gọn, thân thiện, bằng tiếng Việt.\n\n"
        "----- NỘI DUNG BÀI HỌC -----\n"
        f"{content_md}"
    )


def _to_contents(history: list[dict], user_message: str) -> list[dict]:
    """Saved history + the new message -> google-genai `contents`.

    Roles map user->user, assistant->model. The new message is the final user
    turn.
    """
    role_map = {"user": "user", "assistant": "model"}
    contents = [
        {"role": role_map.get(m["role"], "user"), "parts": [{"text": m["content"]}]}
        for m in history
    ]
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    return contents


def stream_socratic_reply(
    content_md: str, history: list[dict], user_message: str
) -> Iterator[str]:
    if not user_message or not user_message.strip():
        raise ChatError(_EMPTY_MESSAGE)

    try:
        stream = get_client().models.generate_content_stream(
            model=CHAT_MODEL,
            contents=_to_contents(history, user_message),
            config={"system_instruction": _build_system_prompt(content_md)},
        )
        for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text
    except ChatError:
        raise
    except Exception as exc:  # network, quota, malformed stream
        logger.exception("Gemini chat streaming failed")
        raise ChatError(_FAILURE_MESSAGE) from exc
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_chat.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/chat.py backend/tests/test_chat.py
git commit -m "feat(5): Socratic streaming chat module (ai/chat.py)"
```

---

### Task 3: `app/routers/chat.py` — endpoints + wire into `main.py`

**Files:**
- Create: `backend/app/routers/chat.py`
- Modify: `backend/app/main.py` (import + include_router)
- Test: `backend/tests/test_chat_api.py`

**Interfaces:**
- Consumes: `app.ai.chat.stream_socratic_reply`, `app.ai.chat.ChatError`, `app.db.admin`, `app.dependencies.auth.get_current_user`.
- Produces (module-level names tests monkeypatch): `repo` (`_Repo` instance), `stream_socratic_reply` (imported name in `chat_router`), router mounted at `/api/chat`.
- Endpoints:
  - `POST /api/chat/{lesson_id}` body `{message}` → `StreamingResponse` (`text/plain; charset=utf-8`).
  - `GET /api/chat/{lesson_id}` → `{messages: [{role, content}, ...]}`.
  - `DELETE /api/chat/{lesson_id}` → `{messages: []}`.

- [ ] **Step 1: Viết test thất bại** — `backend/tests/test_chat_api.py`

```python
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
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd backend && python -m pytest tests/test_chat_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.chat'`.

- [ ] **Step 3: Viết router** — `backend/app/routers/chat.py`

```python
"""Socratic chatbot for one lesson (#5).

One chat_sessions row per (user, lesson): a persistent conversation. db.admin()
bypasses RLS, so every query filters user_id explicitly and another user's
lesson is 404, never 403. The reply streams token-by-token; the user message is
saved BEFORE streaming (so it survives a stream failure) and the assistant
message is appended once the stream finishes.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import db
from app.ai.chat import ChatError, stream_socratic_reply
from app.dependencies.auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

LESSON_NOT_FOUND = "Không tìm thấy bài học."
EMPTY_MESSAGE = "Tin nhắn không được để trống."


class ChatRequest(BaseModel):
    message: str = Field(max_length=4000)


class MessageOut(BaseModel):
    role: str
    content: str


class HistoryOut(BaseModel):
    messages: list[MessageOut]


class _Repo:
    """Thin data layer on the service-role client. Every query filters user_id."""

    def get_lesson(self, user_id: str, lesson_id: str) -> dict | None:
        result = (
            db.admin()
            .table("lessons")
            .select("id, content_md")
            .eq("id", lesson_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_session(self, user_id: str, lesson_id: str) -> dict | None:
        result = (
            db.admin()
            .table("chat_sessions")
            .select("id, messages")
            .eq("user_id", user_id)
            .eq("lesson_id", lesson_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def create_session(self, user_id: str, lesson_id: str) -> dict:
        result = (
            db.admin()
            .table("chat_sessions")
            .insert({"user_id": user_id, "lesson_id": lesson_id, "messages": []})
            .execute()
        )
        row = result.data[0]
        return {"id": row["id"], "messages": []}

    def update_messages(self, session_id: str, messages: list[dict]) -> None:
        # The table has no on-update trigger, so stamp updated_at here. A Python
        # ISO string is a real timestamptz literal; the string "now()" would be
        # inserted verbatim by PostgREST and rejected.
        db.admin().table("chat_sessions").update(
            {"messages": messages, "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", session_id).execute()


repo = _Repo()


def _require_lesson(user_id: str, lesson_id: str) -> dict:
    lesson = repo.get_lesson(user_id, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, LESSON_NOT_FOUND)
    return lesson


@router.post("/{lesson_id}")
def chat(
    lesson_id: str,
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    message = body.message.strip()
    if not message:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, EMPTY_MESSAGE)

    lesson = _require_lesson(user.user_id, lesson_id)

    session = repo.get_session(user.user_id, lesson_id)
    if session is None:
        session = repo.create_session(user.user_id, lesson_id)
    history = session["messages"]
    session_id = session["id"]
    user_msg = {"role": "user", "content": message}

    # Save the user message NOW so a stream failure never loses the question.
    repo.update_messages(session_id, history + [user_msg])

    gen = stream_socratic_reply(lesson["content_md"], history, message)

    # Pull the first chunk eagerly: an up-front failure (quota, network) becomes
    # a clean 502 before the response body starts.
    try:
        first = next(gen)
    except ChatError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    except StopIteration:
        first = ""

    def body_stream():
        parts = [first]
        if first:
            yield first
        try:
            for chunk in gen:
                parts.append(chunk)
                yield chunk
        except ChatError:
            # Mid-stream failure: the body already started, so we cannot change
            # the status. Stop quietly; the partial reply is still saved below.
            logger.exception("Gemini chat stream failed mid-way")
        text = "".join(parts).strip()
        if text:
            repo.update_messages(
                session_id,
                history + [user_msg, {"role": "assistant", "content": text}],
            )

    return StreamingResponse(body_stream(), media_type="text/plain; charset=utf-8")


@router.get("/{lesson_id}", response_model=HistoryOut)
def history(lesson_id: str, user: CurrentUser = Depends(get_current_user)):
    _require_lesson(user.user_id, lesson_id)
    session = repo.get_session(user.user_id, lesson_id)
    return {"messages": session["messages"] if session else []}


@router.delete("/{lesson_id}", response_model=HistoryOut)
def clear(lesson_id: str, user: CurrentUser = Depends(get_current_user)):
    _require_lesson(user.user_id, lesson_id)
    session = repo.get_session(user.user_id, lesson_id)
    if session is not None:
        repo.update_messages(session["id"], [])
    return {"messages": []}
```

- [ ] **Step 4: Wire vào `main.py`**

Modify `backend/app/main.py`:
- Dòng import: đổi `from app.routers import files, health, lessons, me, quiz` →
  `from app.routers import chat, files, health, lessons, me, quiz`.
- Sau `app.include_router(quiz.router)` thêm: `app.include_router(chat.router)`.

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_chat_api.py -v`
Expected: 12 passed.

- [ ] **Step 6: Chạy TOÀN BỘ suite, output sạch**

Run: `cd backend && python -m pytest`
Expected: tất cả pass (219 cũ + 5 + 12 = 236), không warning.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/chat.py backend/app/main.py backend/tests/test_chat_api.py
git commit -m "feat(5): /api/chat endpoints — stream reply, persist, history, clear"
```

---

### Task 4: Frontend `apiStream` + `lib/chat.ts`

**Files:**
- Modify: `frontend/src/lib/api.ts` (thêm `apiStream`)
- Create: `frontend/src/lib/chat.ts`

**Interfaces:**
- Consumes: `supabase`, `ApiError`, `BASE` (đã có trong `api.ts`); `apiFetch`.
- Produces:
  - `apiStream(path: string, options?: RequestInit): Promise<Response>` — trả `Response` thô (ok-checked, Bearer gắn sẵn).
  - `ChatMessage { role: "user" | "assistant"; content: string }`
  - `getChatHistory(lessonId): Promise<ChatMessage[]>`
  - `clearChat(lessonId): Promise<void>`
  - `streamChat(lessonId, message, onChunk): Promise<void>`

> Frontend không có unit-test harness (verify = `npm run build` + `oxlint`), nên các task frontend không TDD; gate là build/lint sạch.

- [ ] **Step 1: Thêm `apiStream` vào `frontend/src/lib/api.ts`**

Ngay dưới `apiFetch`, thêm:

```ts
/**
 * Like apiFetch but returns the raw Response so the caller can read a stream.
 * apiFetch always does res.json(), which consumes the body — useless for the
 * token-by-token chat reply. Same Bearer + Vietnamese network-error handling.
 */
export async function apiStream(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error("Chưa đăng nhập")

  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...options,
      headers: { ...(options.headers ?? {}), Authorization: `Bearer ${token}` },
    })
  } catch (err) {
    console.error("apiStream network failure", path, err)
    throw new ApiError(
      "Không kết nối được máy chủ. Kiểm tra kết nối mạng rồi thử lại.",
      0,
    )
  }

  if (!res.ok) {
    let detail = `Yêu cầu thất bại (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === "string") detail = body.detail
    } catch {
      // Body was not JSON -- keep the fallback.
    }
    throw new ApiError(detail, res.status)
  }
  return res
}
```

- [ ] **Step 2: Viết `frontend/src/lib/chat.ts`**

```ts
import { apiFetch, apiStream } from "@/lib/api"

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

/** Saved conversation for one lesson (empty array if none yet). */
export async function getChatHistory(lessonId: string): Promise<ChatMessage[]> {
  const data = await apiFetch(`/api/chat/${encodeURIComponent(lessonId)}`)
  return (data?.messages ?? []) as ChatMessage[]
}

/** Reset the conversation (server keeps the row, empties messages). */
export async function clearChat(lessonId: string): Promise<void> {
  await apiFetch(`/api/chat/${encodeURIComponent(lessonId)}`, { method: "DELETE" })
}

/**
 * Send a message and stream the Socratic reply. `onChunk` fires for each decoded
 * piece of text as it arrives; resolve when the stream ends.
 */
export async function streamChat(
  lessonId: string,
  message: string,
  onChunk: (text: string) => void,
): Promise<void> {
  const res = await apiStream(`/api/chat/${encodeURIComponent(lessonId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  })

  const reader = res.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    const text = decoder.decode(value, { stream: true })
    if (text) onChunk(text)
  }
  const tail = decoder.decode()
  if (tail) onChunk(tail)
}
```

- [ ] **Step 3: Build + lint sạch**

Run: `cd frontend && npm run build && npx oxlint`
Expected: build không lỗi TS, oxlint không cảnh báo.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/chat.ts
git commit -m "feat(5): apiStream helper + chat api client (lib/chat.ts)"
```

---

### Task 5: `ChatPanel.tsx` + wire vào `LessonDetail`

**Files:**
- Create: `frontend/src/components/ChatPanel.tsx`
- Modify: `frontend/src/pages/LessonDetail.tsx`

**Interfaces:**
- Consumes: `getChatHistory`, `clearChat`, `streamChat`, `ChatMessage` từ `@/lib/chat`; `errorMessage` từ `@/lib/files`; `ReactMarkdown` + `remarkGfm`.
- Produces: `ChatPanel({ lessonId, open, onClose })` component.

- [ ] **Step 1: Viết `frontend/src/components/ChatPanel.tsx`**

```tsx
import { useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { errorMessage } from "@/lib/files"
import {
  clearChat,
  getChatHistory,
  streamChat,
  type ChatMessage,
} from "@/lib/chat"

/**
 * Socratic chat for one lesson (#5). A panel that slides in from the right over
 * the lesson page. Loads the saved conversation on first open; each send streams
 * the reply token-by-token. Never blocks reading -- close returns to the lesson.
 */
export function ChatPanel({
  lessonId,
  open,
  onClose,
}: {
  lessonId: string
  open: boolean
  onClose: () => void
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Load the saved conversation the first time the panel opens.
  useEffect(() => {
    if (!open || loaded) return
    let cancelled = false
    getChatHistory(lessonId)
      .then((history) => {
        if (!cancelled) setMessages(history)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [open, loaded, lessonId])

  // Keep the newest message in view as it streams.
  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight)
  }, [messages])

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setInput("")
    setError(null)
    setSending(true)
    // Show the user turn + an empty assistant turn that the stream fills in.
    setMessages((m) => [
      ...m,
      { role: "user", content: text },
      { role: "assistant", content: "" },
    ])
    try {
      await streamChat(lessonId, text, (chunk) => {
        setMessages((m) => {
          const next = [...m]
          const last = next[next.length - 1]
          next[next.length - 1] = { ...last, content: last.content + chunk }
          return next
        })
      })
    } catch (err) {
      // Drop the empty assistant turn and surface the Vietnamese error.
      setMessages((m) => {
        const next = [...m]
        if (next.length && next[next.length - 1].role === "assistant" && !next[next.length - 1].content) {
          next.pop()
        }
        return next
      })
      setError(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  async function reset() {
    if (sending) return
    if (!window.confirm("Xóa toàn bộ hội thoại của bài này?")) return
    setError(null)
    try {
      await clearChat(lessonId)
      setMessages([])
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <>
      {/* Backdrop: click to close. */}
      <div
        className={`fixed inset-0 z-40 bg-black/20 transition-opacity ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
      />
      <aside
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l bg-white shadow-xl transition-transform ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        aria-hidden={!open}
      >
        <header className="flex items-center justify-between border-b p-4">
          <h2 className="text-sm font-semibold">Hỏi đáp Socratic</h2>
          <div className="flex items-center gap-3 text-sm">
            <button type="button" onClick={() => void reset()} className="text-gray-500 underline">
              Xóa hội thoại
            </button>
            <button type="button" onClick={onClose} aria-label="Đóng" className="text-gray-500">
              ✕
            </button>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 && (
            <p className="text-sm text-gray-500">
              Hỏi về nội dung bài; trợ giảng sẽ gợi mở bằng câu hỏi thay vì đưa đáp án.
            </p>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
            >
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                  m.role === "user" ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-800"
                }`}
              >
                {m.role === "assistant" ? (
                  <div className="prose prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {m.content || "…"}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <span className="whitespace-pre-wrap">{m.content}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {error && <p className="px-4 pb-2 text-sm text-red-600">{error}</p>}

        <div className="flex gap-2 border-t p-4">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            disabled={sending}
            rows={2}
            className="flex-1 resize-none rounded-md border p-2 text-sm"
            placeholder="Nhập câu hỏi… (Enter để gửi)"
          />
          <button
            type="button"
            onClick={() => void send()}
            disabled={sending || !input.trim()}
            className="self-end rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            {sending ? "…" : "Gửi"}
          </button>
        </div>
      </aside>
    </>
  )
}
```

- [ ] **Step 2: Wire vào `frontend/src/pages/LessonDetail.tsx`**

- Thêm import: `import { ChatPanel } from "@/components/ChatPanel"`.
- Thêm state cạnh các `useState` khác: `const [chatOpen, setChatOpen] = useState(false)`.
- Trong khối header, cạnh `<label>…Đã học</label>`, thêm nút mở (đặt trong cùng `div.flex` chứa checkbox — bọc checkbox + nút trong một `div.flex.items-center.gap-3` nếu cần):

```tsx
<button
  type="button"
  onClick={() => setChatOpen(true)}
  className="shrink-0 rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50"
>
  Hỏi đáp Socratic
</button>
```

- Trước thẻ đóng `</div>` ngoài cùng của `return`, thêm:

```tsx
<ChatPanel lessonId={lesson.id} open={chatOpen} onClose={() => setChatOpen(false)} />
```

- [ ] **Step 3: Build + lint sạch**

Run: `cd frontend && npm run build && npx oxlint`
Expected: build không lỗi TS, oxlint không cảnh báo.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ChatPanel.tsx frontend/src/pages/LessonDetail.tsx
git commit -m "feat(5): ChatPanel slide-in + open button on lesson page"
```

---

### Task 6: `verify_5.py` — live end-to-end + cập nhật checklist

**Files:**
- Create: `backend/scripts/verify_5.py`
- Modify: `check_list.md` (đánh dấu #5 xong + bằng chứng)

**Interfaces:**
- Consumes: `verify_1b.mint_access_token`, real API on `http://localhost:8000`, `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_ANON_KEY`, `GEMINI_API_KEY` trong `backend/.env`.

- [ ] **Step 1: Viết `backend/scripts/verify_5.py`**

```python
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
```

- [ ] **Step 2: Chạy verify thật**

Đảm bảo backend đang chạy (`uvicorn`) và `SUPABASE_ANON_KEY` trong env.
Run: `cd backend && PYTHONIOENCODING=utf-8 SUPABASE_ANON_KEY=$(grep VITE_SUPABASE_ANON_KEY ../frontend/.env.local | cut -d= -f2) python scripts/verify_5.py`
Expected: `ALL CHECKS PASSED`.

- [ ] **Step 3: (Thủ công) Kiểm trình duyệt**

Mở một bài ở `/lessons/:slug`, bấm "Hỏi đáp Socratic": panel trượt ra; gửi câu hỏi → reply stream dần; F5 rồi mở lại panel → hội thoại còn; "Xóa hội thoại" → trống. Ghi lại kết quả.

- [ ] **Step 4: Cập nhật `check_list.md`**

Trong mục `### #5 — Socratic Chatbot`: đổi `- [ ]` thành `- [x]`, thêm dòng trạng thái "✅ XONG (2026-07-21, nhánh `feature/socratic-chatbot`)", liệt kê bằng chứng verify thật (số message, RLS 0 dòng, dọn sạch) theo khuôn các mục #3/#4.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/verify_5.py check_list.md
git commit -m "test(5): live end-to-end verify_5 + mark #5 done in checklist"
```

---

## Self-Review

**Spec coverage:**
- Migration 0008 (D-chat-5) → Task 1. ✓
- `ai/chat.py` Socratic thuần + streaming + ChatError → Task 2. ✓
- `routers/chat.py` POST(stream)/GET/DELETE, keyed lesson_id, user-msg-before-stream, 502 up-front, mid-stream save, wire main.py → Task 3. ✓
- `apiStream` + `lib/chat.ts` → Task 4. ✓
- `ChatPanel` slide-in + LessonDetail button (D-chat-2), markdown reply, "Xóa hội thoại" (D-chat-3) → Task 5. ✓
- Tests `test_chat.py` + `test_chat_api.py`; `verify_5.py` với RLS + cleanup → Task 2/3/6. ✓
- Error table (422/404/502/mid-stream/network/401) → phủ trong test Task 3 + xử lý router. ✓

**Placeholder scan:** không có TBD/TODO; mọi step code đầy đủ. ✓

**Type consistency:** `stream_socratic_reply(content_md, history, user_message)` đồng nhất giữa module (Task 2), router import (Task 3), fakes (Task 2/3). `repo` + `stream_socratic_reply` là tên module-level trong `chat_router` mà test monkeypatch — khớp. `ChatMessage{role,content}` đồng nhất backend `MessageOut` ↔ frontend. `apiStream` trả `Response`. `getChatHistory/clearChat/streamChat` khớp giữa `lib/chat.ts` (Task 4) và `ChatPanel` (Task 5). ✓
