# #3 Lessons UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép người dùng xem danh sách bài học đã duyệt từ tài liệu của mình, đọc nội dung markdown, và đánh dấu "Đã học".

**Architecture:** Ba endpoint FastAPI mới trong `app/routers/lessons.py` (repo mỏng dùng service-role client, mọi truy vấn lọc `user_id` tường minh, không sở hữu → 404). Backend trả danh sách **phẳng**; frontend gom nhóm theo file nguồn để trình bày. Hai trang React mới đọc qua `apiFetch`.

**Tech Stack:** FastAPI + supabase-py + pytest · React 19 + React Router 7 + Tailwind v4 + `react-markdown`/`remark-gfm`/`@tailwindcss/typography`.

**Spec:** `docs/superpowers/specs/2026-07-20-lessons-ui-design.md`

## Global Constraints

- Chuỗi hiển thị cho user = **tiếng Việt**; code, tên biến, comment, commit message = **tiếng Anh**.
- Backend không bao giờ nhận `user_id` từ client — luôn lấy từ `Depends(get_current_user)`.
- Tài nguyên không thuộc về user trả **404** (không phải 403), thông điệp `"Không tìm thấy bài học."`
- `db.admin()` bypass RLS → **mọi** truy vấn phải `.eq("user_id", ...)` tường minh.
- `pytest` từ `backend/` phải xanh **và output sạch** (không warning).
- `npm run build` từ `frontend/` phải không lỗi TypeScript.
- Không bật `rehype-raw` cho `react-markdown` (HTML thô phải giữ nguyên trạng thái bị chặn).
- Commit sau mỗi task.
- Nhánh làm việc: `feature/lessons-ui` (đã tạo, spec đã commit ở `f31cb88`).

---

### Task 1: `GET /api/lessons` — danh sách bài học

**Files:**
- Create: `backend/app/routers/lessons.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_lessons_api.py`

**Interfaces:**
- Consumes: `app.db.admin()`, `app.dependencies.auth.get_current_user` / `CurrentUser`.
- Produces: `router` (prefix `/api/lessons`), module-level `repo` (instance của `_Repo`, tests monkeypatch nó), Pydantic `LessonOut`, hàm `_merge(row, file_names, progress) -> dict`.

- [ ] **Step 1: Write the failing test**

Tạo `backend/tests/test_lessons_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import lessons as lessons_router
from tests.conftest import OTHER_USER_ID, USER_ID, auth_headers

client = TestClient(app)


class _FakeRepo:
    """Stands in for every db call the router makes.

    Mirrors the real _Repo's signatures, including the user_id scoping, so
    router tests still exercise the router's own logic faithfully. The real
    query-building code is exercised separately in test_lessons_repo.py.
    """

    def __init__(self):
        self.lessons: list[dict] = []
        self.files: dict[str, dict] = {}
        self.progress: list[dict] = []
        self.upserted: list[dict] = []

    def list_lessons(self, user_id):
        return [dict(r) for r in self.lessons if r["user_id"] == user_id]

    def get_lesson_by_slug(self, user_id, slug):
        for row in self.lessons:
            if row["user_id"] == user_id and row["slug"] == slug:
                return dict(row)
        return None

    def get_lesson(self, lesson_id, user_id):
        for row in self.lessons:
            if row["id"] == lesson_id and row["user_id"] == user_id:
                return dict(row)
        return None

    def list_file_names(self, user_id):
        return {
            fid: f["file_name"]
            for fid, f in self.files.items()
            if f["user_id"] == user_id
        }

    def list_progress(self, user_id):
        return {p["lesson_id"]: dict(p) for p in self.progress if p["user_id"] == user_id}

    def upsert_progress(self, values):
        self.upserted.append(dict(values))


def make_lesson(lesson_id, slug, title, order_index, file_id, user_id=USER_ID):
    return {
        "id": lesson_id,
        "user_id": user_id,
        "slug": slug,
        "title": title,
        "order_index": order_index,
        "source_file_id": file_id,
        "content_md": f"# {title}\n\nnội dung",
    }


@pytest.fixture
def repo(monkeypatch):
    fake = _FakeRepo()
    monkeypatch.setattr(lessons_router, "repo", fake)
    return fake


# --- list --------------------------------------------------------------------

def test_list_returns_only_my_lessons_with_file_name_and_progress(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "giao-trinh.docx"}
    repo.lessons = [
        make_lesson("l1", "gt-0", "Chương 1", 0, "f1"),
        make_lesson("l2", "gt-1", "Chương 2", 1, "f1"),
        make_lesson("l9", "khac-0", "Của người khác", 0, "f1", user_id=OTHER_USER_ID),
    ]
    repo.progress = [
        {"user_id": USER_ID, "lesson_id": "l1", "status": "done", "completed_at": "2026-07-20T10:00:00+00:00"}
    ]

    res = client.get("/api/lessons", headers=auth_headers())

    assert res.status_code == 200
    body = res.json()
    assert [r["slug"] for r in body] == ["gt-0", "gt-1"]
    assert body[0]["source_file_name"] == "giao-trinh.docx"
    assert body[0]["done"] is True
    assert body[0]["completed_at"] == "2026-07-20T10:00:00+00:00"
    # No lesson_progress row at all means not done, not an error.
    assert body[1]["done"] is False
    assert body[1]["completed_at"] is None


def test_list_sorts_orphan_lessons_last(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "b-sach.docx"}
    repo.files["f2"] = {"user_id": USER_ID, "file_name": "a-sach.pdf"}
    repo.lessons = [
        # source_file_id is ON DELETE SET NULL, so an orphan is a real state.
        make_lesson("l0", "mo-coi", "Mồ côi", 0, None),
        make_lesson("l1", "b-1", "B chương 2", 1, "f1"),
        make_lesson("l2", "b-0", "B chương 1", 0, "f1"),
        make_lesson("l3", "a-0", "A chương 1", 0, "f2"),
    ]

    body = client.get("/api/lessons", headers=auth_headers()).json()

    assert [r["slug"] for r in body] == ["a-0", "b-0", "b-1", "mo-coi"]
    assert body[-1]["source_file_name"] is None


def test_list_requires_a_token(repo):
    assert client.get("/api/lessons").status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_lessons_api.py -v` (từ `backend/`)
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.lessons'`

- [ ] **Step 3: Write minimal implementation**

Tạo `backend/app/routers/lessons.py`:

```python
"""Reading lessons: the library list, one lesson's content, and progress."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app import db
from app.dependencies.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/lessons", tags=["lessons"])

NOT_FOUND = "Không tìm thấy bài học."


class LessonOut(BaseModel):
    """A row of the library list.

    `content_md` is deliberately absent: the list would carry every lesson's
    full text otherwise, and nothing on that screen renders it.
    """

    id: str
    slug: str
    title: str
    order_index: int
    source_file_id: str | None = None
    source_file_name: str | None = None
    done: bool
    completed_at: str | None = None


class _Repo:
    """Thin data layer. Isolated in a class so tests can swap it wholesale.

    Uses the service-role client, which bypasses RLS -- every read here
    filters on user_id explicitly.
    """

    def list_lessons(self, user_id: str) -> list[dict]:
        result = (
            db.admin()
            .table("lessons")
            .select("id, slug, title, order_index, source_file_id")
            .eq("user_id", user_id)
            .execute()
        )
        return result.data or []

    def list_file_names(self, user_id: str) -> dict[str, str]:
        result = (
            db.admin()
            .table("user_files")
            .select("id, file_name")
            .eq("user_id", user_id)
            .execute()
        )
        return {row["id"]: row["file_name"] for row in (result.data or [])}

    def list_progress(self, user_id: str) -> dict[str, dict]:
        result = (
            db.admin()
            .table("lesson_progress")
            .select("lesson_id, status, completed_at")
            .eq("user_id", user_id)
            .execute()
        )
        return {row["lesson_id"]: row for row in (result.data or [])}


repo = _Repo()


def _merge(row: dict, file_names: dict[str, str], progress: dict[str, dict]) -> dict:
    """Lesson row + its file name + its progress -> one flat response dict."""
    entry = progress.get(row["id"]) or {}
    return {
        **row,
        "source_file_name": file_names.get(row.get("source_file_id")),
        "done": entry.get("status") == "done",
        "completed_at": entry.get("completed_at"),
    }


def _sort_key(row: dict) -> tuple:
    """By file name, then chapter order. Orphans (no source file) go last."""
    name = row["source_file_name"]
    return (name is None, name or "", row["order_index"])


@router.get("", response_model=list[LessonOut])
def list_lessons(user: CurrentUser = Depends(get_current_user)):
    file_names = repo.list_file_names(user.user_id)
    progress = repo.list_progress(user.user_id)
    rows = [_merge(r, file_names, progress) for r in repo.list_lessons(user.user_id)]
    rows.sort(key=_sort_key)
    return rows
```

Sửa `backend/app/main.py` — dòng import và dòng include:

```python
from app.routers import files, health, lessons, me
```

```python
app.include_router(files.router)
app.include_router(lessons.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_lessons_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest`
Expected: tất cả xanh, không warning mới.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/lessons.py backend/app/main.py backend/tests/test_lessons_api.py
git commit -m "feat(lessons): list a user's lessons with source file and progress"
```

---

### Task 2: `GET /api/lessons/{slug}` — nội dung bài + prev/next

**Files:**
- Modify: `backend/app/routers/lessons.py`
- Test: `backend/tests/test_lessons_api.py`

**Interfaces:**
- Consumes: `repo`, `_merge`, `NOT_FOUND`, `LessonOut` từ Task 1; `_FakeRepo`/`make_lesson`/`repo` fixture từ file test Task 1.
- Produces: `LessonNav`, `LessonDetailOut`, `_Repo.get_lesson_by_slug(user_id, slug)`, `_neighbours(row, all_rows) -> tuple[dict | None, dict | None]`.

- [ ] **Step 1: Write the failing test**

Thêm vào cuối `backend/tests/test_lessons_api.py`:

```python
# --- detail ------------------------------------------------------------------

def test_detail_returns_content_and_neighbours(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "giao-trinh.docx"}
    repo.lessons = [
        make_lesson("l1", "gt-0", "Chương 1", 0, "f1"),
        make_lesson("l2", "gt-1", "Chương 2", 1, "f1"),
        make_lesson("l3", "gt-2", "Chương 3", 2, "f1"),
    ]

    body = client.get("/api/lessons/gt-1", headers=auth_headers()).json()

    assert body["content_md"] == "# Chương 2\n\nnội dung"
    assert body["source_file_name"] == "giao-trinh.docx"
    assert body["prev"] == {"slug": "gt-0", "title": "Chương 1"}
    assert body["next"] == {"slug": "gt-2", "title": "Chương 3"}


def test_detail_neighbours_are_null_at_both_ends(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "giao-trinh.docx"}
    repo.lessons = [
        make_lesson("l1", "gt-0", "Chương 1", 0, "f1"),
        make_lesson("l2", "gt-1", "Chương 2", 1, "f1"),
    ]

    first = client.get("/api/lessons/gt-0", headers=auth_headers()).json()
    last = client.get("/api/lessons/gt-1", headers=auth_headers()).json()

    assert first["prev"] is None
    assert first["next"] == {"slug": "gt-1", "title": "Chương 2"}
    assert last["prev"] == {"slug": "gt-0", "title": "Chương 1"}
    assert last["next"] is None


def test_detail_neighbours_never_cross_into_another_file(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "a.docx"}
    repo.files["f2"] = {"user_id": USER_ID, "file_name": "b.docx"}
    repo.lessons = [
        make_lesson("l1", "a-0", "A chương 1", 0, "f1"),
        make_lesson("l2", "b-0", "B chương 1", 0, "f2"),
    ]

    body = client.get("/api/lessons/a-0", headers=auth_headers()).json()

    assert body["prev"] is None
    assert body["next"] is None


def test_detail_of_an_orphan_lesson_has_no_neighbours(repo):
    repo.lessons = [make_lesson("l0", "mo-coi", "Mồ côi", 0, None)]

    body = client.get("/api/lessons/mo-coi", headers=auth_headers()).json()

    assert body["prev"] is None
    assert body["next"] is None
    assert body["source_file_name"] is None


def test_detail_of_another_users_lesson_is_404_not_403(repo):
    # 403 would confirm the slug exists; 404 gives nothing away.
    repo.lessons = [make_lesson("l9", "cua-ho", "Của họ", 0, None, user_id=OTHER_USER_ID)]

    res = client.get("/api/lessons/cua-ho", headers=auth_headers())

    assert res.status_code == 404
    assert res.json()["detail"] == "Không tìm thấy bài học."


def test_detail_of_an_unknown_slug_is_404(repo):
    res = client.get("/api/lessons/khong-co", headers=auth_headers())
    assert res.status_code == 404


def test_detail_requires_a_token(repo):
    assert client.get("/api/lessons/gt-0").status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_lessons_api.py -k detail -v`
Expected: FAIL — 404 cho mọi ca (route chưa tồn tại).

- [ ] **Step 3: Write minimal implementation**

Thêm vào `backend/app/routers/lessons.py`. Model, đặt ngay dưới `LessonOut`:

```python
class LessonNav(BaseModel):
    slug: str
    title: str


class LessonDetailOut(LessonOut):
    content_md: str
    prev: LessonNav | None = None
    next: LessonNav | None = None
```

Method mới trong `_Repo`:

```python
    def get_lesson_by_slug(self, user_id: str, slug: str) -> dict | None:
        # Slug is unique per user (lessons_user_slug_idx), not globally, so
        # both columns are needed to identify a row.
        result = (
            db.admin()
            .table("lessons")
            .select("*")
            .eq("user_id", user_id)
            .eq("slug", slug)
            .maybe_single()
            .execute()
        )
        # postgrest's maybe_single returns None itself when nothing matched.
        return result.data if result else None
```

Helper + route, cuối file:

```python
def _neighbours(row: dict, all_rows: list[dict]) -> tuple[dict | None, dict | None]:
    """Previous/next chapter within the SAME source file, by order_index.

    An orphan lesson has no file to be adjacent within, so it gets neither.
    """
    file_id = row.get("source_file_id")
    if file_id is None:
        return None, None

    siblings = sorted(
        (r for r in all_rows if r.get("source_file_id") == file_id),
        key=lambda r: r["order_index"],
    )
    ids = [r["id"] for r in siblings]
    if row["id"] not in ids:
        return None, None

    index = ids.index(row["id"])
    before = siblings[index - 1] if index > 0 else None
    after = siblings[index + 1] if index + 1 < len(siblings) else None

    def nav(target: dict | None) -> dict | None:
        return None if target is None else {"slug": target["slug"], "title": target["title"]}

    return nav(before), nav(after)


@router.get("/{slug}", response_model=LessonDetailOut)
def get_lesson(slug: str, user: CurrentUser = Depends(get_current_user)):
    row = repo.get_lesson_by_slug(user.user_id, slug)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    merged = _merge(row, repo.list_file_names(user.user_id), repo.list_progress(user.user_id))
    before, after = _neighbours(row, repo.list_lessons(user.user_id))
    return {**merged, "prev": before, "next": after}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_lessons_api.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/lessons.py backend/tests/test_lessons_api.py
git commit -m "feat(lessons): serve one lesson with prev/next chapter navigation"
```

---

### Task 3: `PUT /api/lessons/{id}/progress` — đánh dấu đã học

**Files:**
- Modify: `backend/app/routers/lessons.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_lessons_api.py`, `backend/tests/test_lessons_repo.py` (create)

**Interfaces:**
- Consumes: `repo`, `NOT_FOUND` từ Task 1; `FakeClient`/`FakeTable` từ `tests/conftest.py`.
- Produces: `ProgressRequest{done: bool}`, `ProgressOut{done: bool, completed_at: str | None}`, `_Repo.get_lesson(lesson_id, user_id)`, `_Repo.upsert_progress(values: dict)`. `FakeTable.upsert(values, on_conflict)` cho test.

- [ ] **Step 1: Write the failing router test**

Thêm vào cuối `backend/tests/test_lessons_api.py`:

```python
# --- progress ----------------------------------------------------------------

def test_marking_done_upserts_progress_with_a_timestamp(repo):
    repo.lessons = [make_lesson("l1", "gt-0", "Chương 1", 0, None)]

    res = client.put(
        "/api/lessons/l1/progress", json={"done": True}, headers=auth_headers()
    )

    assert res.status_code == 200
    assert res.json()["done"] is True
    assert res.json()["completed_at"] is not None
    written = repo.upserted[-1]
    assert written["user_id"] == USER_ID
    assert written["lesson_id"] == "l1"
    assert written["status"] == "done"
    assert written["completed_at"] == res.json()["completed_at"]


def test_unmarking_clears_the_timestamp(repo):
    repo.lessons = [make_lesson("l1", "gt-0", "Chương 1", 0, None)]

    client.put("/api/lessons/l1/progress", json={"done": True}, headers=auth_headers())
    res = client.put(
        "/api/lessons/l1/progress", json={"done": False}, headers=auth_headers()
    )

    assert res.json() == {"done": False, "completed_at": None}
    assert repo.upserted[-1]["status"] == "not_done"
    assert repo.upserted[-1]["completed_at"] is None


def test_progress_on_another_users_lesson_is_404_and_writes_nothing(repo):
    repo.lessons = [make_lesson("l9", "cua-ho", "Của họ", 0, None, user_id=OTHER_USER_ID)]

    res = client.put(
        "/api/lessons/l9/progress", json={"done": True}, headers=auth_headers()
    )

    assert res.status_code == 404
    assert repo.upserted == []


def test_progress_requires_a_token(repo):
    res = client.put("/api/lessons/l1/progress", json={"done": True})
    assert res.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_lessons_api.py -k progress -v`
Expected: FAIL — 405/404, route chưa tồn tại.

- [ ] **Step 3: Implement the endpoint**

Trong `backend/app/routers/lessons.py`, thêm import ở đầu file:

```python
from datetime import datetime, timezone
```

Models, dưới `LessonDetailOut`:

```python
class ProgressRequest(BaseModel):
    done: bool


class ProgressOut(BaseModel):
    done: bool
    completed_at: str | None = None
```

Methods mới trong `_Repo`:

```python
    def get_lesson(self, lesson_id: str, user_id: str) -> dict | None:
        result = (
            db.admin()
            .table("lessons")
            .select("id")
            .eq("id", lesson_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def upsert_progress(self, values: dict) -> None:
        # lesson_progress's primary key is (user_id, lesson_id), so the
        # conflict target must name both -- the default `id` column does not
        # exist on this table.
        db.admin().table("lesson_progress").upsert(
            values, on_conflict="user_id,lesson_id"
        ).execute()
```

Route, cuối file:

```python
@router.put("/{lesson_id}/progress", response_model=ProgressOut)
def set_progress(
    lesson_id: str,
    body: ProgressRequest,
    user: CurrentUser = Depends(get_current_user),
):
    if repo.get_lesson(lesson_id, user.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    completed_at = (
        datetime.now(timezone.utc).isoformat() if body.done else None
    )
    repo.upsert_progress(
        {
            "user_id": user.user_id,
            "lesson_id": lesson_id,
            "status": "done" if body.done else "not_done",
            "completed_at": completed_at,
        }
    )
    return {"done": body.done, "completed_at": completed_at}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_lessons_api.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Teach the fake supabase client to upsert**

Router tests dùng fake repo; bước này để test **query thật** ở Step 6. Trong `backend/tests/conftest.py`, thêm vào `FakeTable.__init__` (cạnh `self._insert_values = None`):

```python
        self._upsert_values: dict | None = None
        # Conflict target, as column names. Defaults to the primary key most
        # tables here use; lesson_progress passes "user_id,lesson_id" because
        # it has no `id` column at all.
        self._upsert_key: tuple[str, ...] = ("id",)
```

Thêm method (cạnh `insert`):

```python
    def upsert(self, values, on_conflict="id"):
        self._upsert_values = values
        self._upsert_key = tuple(c.strip() for c in on_conflict.split(","))
        return self
```

Trong `FakeTable.execute`, thêm ngay **trước** khối `if self._insert_values is not None:`:

```python
        if self._upsert_values is not None:
            key = tuple(self._upsert_values[c] for c in self._upsert_key)
            self._store[key] = {**self._store.get(key, {}), **self._upsert_values}
            return type("Res", (), {"data": [dict(self._store[key])]})()
```

- [ ] **Step 6: Write the failing repo test**

Tạo `backend/tests/test_lessons_repo.py`:

```python
"""Exercises _Repo's real query building against a fake supabase client.

The router tests swap _Repo out wholesale, so without this file the actual
.eq()/.upsert() chains would never run.
"""

import pytest

from app.routers import lessons as lessons_router
from tests.conftest import OTHER_USER_ID, USER_ID, FakeClient


@pytest.fixture
def stores(monkeypatch):
    tables = {
        "lessons": {},
        "user_files": {},
        "lesson_progress": {},
    }
    monkeypatch.setattr(
        lessons_router.db, "admin", lambda: FakeClient({}, tables=tables)
    )
    return tables


def test_list_lessons_filters_by_user(stores):
    stores["lessons"]["l1"] = {"id": "l1", "user_id": USER_ID, "slug": "a"}
    stores["lessons"]["l9"] = {"id": "l9", "user_id": OTHER_USER_ID, "slug": "b"}

    rows = lessons_router._Repo().list_lessons(USER_ID)

    assert [r["id"] for r in rows] == ["l1"]


def test_get_lesson_by_slug_needs_both_user_and_slug(stores):
    stores["lessons"]["l9"] = {"id": "l9", "user_id": OTHER_USER_ID, "slug": "a"}

    assert lessons_router._Repo().get_lesson_by_slug(USER_ID, "a") is None


def test_upsert_progress_keys_on_user_and_lesson(stores):
    repo = lessons_router._Repo()

    repo.upsert_progress(
        {"user_id": USER_ID, "lesson_id": "l1", "status": "done", "completed_at": "t"}
    )
    repo.upsert_progress(
        {"user_id": USER_ID, "lesson_id": "l1", "status": "not_done", "completed_at": None}
    )

    # Second call must replace the first, not add a second row.
    assert len(stores["lesson_progress"]) == 1
    stored = next(iter(stores["lesson_progress"].values()))
    assert stored["status"] == "not_done"
    assert stored["completed_at"] is None


def test_list_progress_is_keyed_by_lesson_id(stores):
    stores["lesson_progress"][(USER_ID, "l1")] = {
        "user_id": USER_ID, "lesson_id": "l1", "status": "done", "completed_at": "t"
    }

    assert lessons_router._Repo().list_progress(USER_ID)["l1"]["status"] == "done"
```

- [ ] **Step 7: Run the repo tests**

Run: `python -m pytest tests/test_lessons_repo.py -v`
Expected: PASS (4 passed)

- [ ] **Step 8: Run the whole suite**

Run: `python -m pytest`
Expected: tất cả xanh, output sạch. Nếu có warning mới → sửa, không suppress.

- [ ] **Step 9: Commit**

```bash
git add backend/app/routers/lessons.py backend/tests/test_lessons_api.py backend/tests/test_lessons_repo.py backend/tests/conftest.py
git commit -m "feat(lessons): toggle per-user lesson progress"
```

---

### Task 4: Frontend — dependency, API wrapper, trang `/lessons`

**Files:**
- Modify: `frontend/package.json` (qua `npm install`), `frontend/src/index.css`, `frontend/src/App.tsx`, `frontend/src/pages/Home.tsx`, `frontend/src/pages/Files.tsx`
- Create: `frontend/src/lib/lessons.ts`, `frontend/src/pages/Lessons.tsx`

**Interfaces:**
- Consumes: `apiFetch` từ `@/lib/api`, `errorMessage` từ `@/lib/files`, hợp đồng `GET /api/lessons` của Task 1.
- Produces: types `Lesson`, `LessonNav`, `LessonDetail`, `LessonGroup`; hàm `listLessons()`, `getLesson(slug)`, `setLessonProgress(id, done)`, `groupLessons(lessons)`; component `Lessons`; route `/lessons`.

- [ ] **Step 1: Install the dependencies**

Run (từ `frontend/`):

```bash
npm install react-markdown remark-gfm
npm install -D @tailwindcss/typography
```

Expected: `package.json` có `react-markdown`, `remark-gfm` trong `dependencies` và `@tailwindcss/typography` trong `devDependencies`.

- [ ] **Step 2: Enable the typography plugin**

Trong `frontend/src/index.css`, thêm ngay sau dòng `@import "@fontsource-variable/geist";`:

```css

/* Tailwind v4 loads plugins from CSS, not tailwind.config. `prose` styles the
   rendered lesson markdown. */
@plugin "@tailwindcss/typography";
```

- [ ] **Step 3: Write the API wrapper**

Tạo `frontend/src/lib/lessons.ts`:

```ts
import { apiFetch } from "@/lib/api"

export interface Lesson {
  id: string
  slug: string
  title: string
  order_index: number
  source_file_id: string | null
  source_file_name: string | null
  done: boolean
  completed_at: string | null
}

export interface LessonNav {
  slug: string
  title: string
}

export interface LessonDetail extends Lesson {
  content_md: string
  prev: LessonNav | null
  next: LessonNav | null
}

export interface LessonProgress {
  done: boolean
  completed_at: string | null
}

/** Lessons of one source file -- a "book" and its chapters. */
export interface LessonGroup {
  fileId: string | null
  fileName: string
  lessons: Lesson[]
}

export function listLessons(): Promise<Lesson[]> {
  return apiFetch("/api/lessons")
}

export function getLesson(slug: string): Promise<LessonDetail> {
  return apiFetch(`/api/lessons/${encodeURIComponent(slug)}`)
}

export function setLessonProgress(
  lessonId: string,
  done: boolean,
): Promise<LessonProgress> {
  return apiFetch(`/api/lessons/${lessonId}/progress`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ done }),
  })
}

/**
 * Group by source file for display.
 *
 * Relies on the backend already sorting by file name then order_index (with
 * orphans last), so insertion order into the Map is the display order and
 * this does no sorting of its own. Orphans -- lessons whose source file was
 * deleted, source_file_id being ON DELETE SET NULL -- share one "Khác" group.
 */
export function groupLessons(lessons: Lesson[]): LessonGroup[] {
  const groups = new Map<string, LessonGroup>()
  for (const lesson of lessons) {
    const key = lesson.source_file_id ?? ""
    let group = groups.get(key)
    if (!group) {
      group = {
        fileId: lesson.source_file_id,
        fileName: lesson.source_file_name ?? "Khác",
        lessons: [],
      }
      groups.set(key, group)
    }
    group.lessons.push(lesson)
  }
  return [...groups.values()]
}
```

- [ ] **Step 4: Write the list page**

Tạo `frontend/src/pages/Lessons.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { errorMessage } from "@/lib/files"
import { groupLessons, listLessons, type Lesson } from "@/lib/lessons"

type Filter = "all" | "todo" | "done"

const FILTER_LABELS: Record<Filter, string> = {
  all: "Tất cả",
  todo: "Chưa học",
  done: "Đã học",
}

function matches(lesson: Lesson, filter: Filter): boolean {
  if (filter === "todo") return !lesson.done
  if (filter === "done") return lesson.done
  return true
}

export function Lessons() {
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [filter, setFilter] = useState<Filter>("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setLessons(await listLessons())
      setError(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Filter first, then group: a group whose every lesson is filtered out
  // should disappear rather than render as an empty heading.
  const groups = groupLessons(lessons.filter((l) => matches(l, filter))).filter(
    (g) => g.lessons.length > 0,
  )

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Bài học của tôi</h1>
        <div className="space-x-4 text-sm text-gray-500">
          <Link to="/files" className="underline">
            Tài liệu
          </Link>
          <Link to="/" className="underline">
            Trang chủ
          </Link>
        </div>
      </div>

      <div className="flex gap-2">
        {(Object.keys(FILTER_LABELS) as Filter[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={
              filter === key
                ? "rounded-md bg-gray-900 px-3 py-1 text-sm text-white"
                : "rounded-md border px-3 py-1 text-sm text-gray-600"
            }
          >
            {FILTER_LABELS[key]}
          </button>
        ))}
      </div>

      {error && (
        <div className="space-y-2">
          <p className="text-sm text-red-600">{error}</p>
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-md border px-3 py-1 text-sm"
          >
            Thử lại
          </button>
        </div>
      )}

      {loading ? (
        <p className="py-8 text-center text-sm text-gray-500">Đang tải…</p>
      ) : lessons.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-500">
          Chưa có bài học nào.{" "}
          <Link to="/files" className="underline">
            Hãy tải tài liệu lên.
          </Link>
        </p>
      ) : groups.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-500">
          Không có bài học nào khớp bộ lọc.
        </p>
      ) : (
        <div className="space-y-6">
          {groups.map((group) => (
            <section key={group.fileId ?? "orphans"} className="space-y-2">
              <div className="flex items-baseline justify-between">
                <h2 className="font-medium">{group.fileName}</h2>
                <span className="text-xs text-gray-500">
                  {group.lessons.filter((l) => l.done).length}/{group.lessons.length} đã học
                </span>
              </div>
              <ul className="divide-y rounded-md border">
                {group.lessons.map((lesson) => (
                  <li key={lesson.id}>
                    <Link
                      to={`/lessons/${lesson.slug}`}
                      className="flex items-center justify-between px-4 py-3 hover:bg-gray-50"
                    >
                      <span className="text-sm">{lesson.title}</span>
                      {lesson.done && (
                        <span className="text-xs text-green-700">Đã học</span>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
```

> Lưu ý tiến độ `x/y` được tính trên **danh sách đã lọc**. Đó là chủ ý: khi lọc "Chưa học" thì `0/n` là con số đúng với những gì đang hiển thị.

- [ ] **Step 5: Register the route**

Trong `frontend/src/App.tsx`, thêm import:

```tsx
import { Lessons } from "@/pages/Lessons"
```

và thêm route **trước** route bắt-tất-cả `/*`:

```tsx
        <Route
          path="/lessons"
          element={
            <ProtectedRoute>
              <Lessons />
            </ProtectedRoute>
          }
        />
```

- [ ] **Step 6: Add a way in**

Trong `frontend/src/pages/Files.tsx`, đổi khối link ở header (dòng 102-104) thành:

```tsx
        <div className="space-x-4 text-sm text-gray-500">
          <Link to="/lessons" className="underline">
            Bài học
          </Link>
          <Link to="/" className="underline">
            Trang chủ
          </Link>
        </div>
```

Trong `frontend/src/pages/Home.tsx`, thêm một nút "Bài học" ngay **trước** nút "Tài liệu của tôi" (dòng 37) — bài học là đích đến thường xuyên hơn tài liệu:

```tsx
        <Button onClick={() => navigate("/lessons")}>Bài học</Button>
        <Button variant="outline" onClick={() => navigate("/files")}>
          Tài liệu của tôi
        </Button>
```

(nút `/files` đổi sang `variant="outline"` để chỉ còn một nút nhấn mạnh trên hàng).

- [ ] **Step 7: Verify the build**

Run (từ `frontend/`): `npm run build`
Expected: build xong, không lỗi TypeScript.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/index.css frontend/src/lib/lessons.ts frontend/src/pages/Lessons.tsx frontend/src/App.tsx frontend/src/pages/Files.tsx frontend/src/pages/Home.tsx
git commit -m "feat(lessons): lesson library page grouped by source file"
```

---

### Task 5: Frontend — trang đọc bài `/lessons/:slug`

**Files:**
- Create: `frontend/src/pages/LessonDetail.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `getLesson`, `setLessonProgress`, type `LessonDetail` từ Task 4; `GET /api/lessons/{slug}` và `PUT /api/lessons/{id}/progress` từ Task 2 và 3.
- Produces: component `LessonDetailPage`; route `/lessons/:slug`.

- [ ] **Step 1: Write the page**

Tạo `frontend/src/pages/LessonDetail.tsx`:

```tsx
import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { ApiError } from "@/lib/api"
import { errorMessage } from "@/lib/files"
import { getLesson, setLessonProgress, type LessonDetail } from "@/lib/lessons"

export function LessonDetailPage() {
  const { slug } = useParams<{ slug: string }>()
  const [lesson, setLesson] = useState<LessonDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!slug) return
    let cancelled = false
    setLoading(true)
    setNotFound(false)
    setError(null)
    getLesson(slug)
      .then((data) => {
        if (!cancelled) setLesson(data)
      })
      .catch((err) => {
        if (cancelled) return
        // 404 gets its own screen; anything else is a banner over the page.
        if (err instanceof ApiError && err.status === 404) setNotFound(true)
        else setError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    // Guards against a stale response landing after the user navigated to
    // the next chapter -- this page re-fetches on every slug change.
    return () => {
      cancelled = true
    }
  }, [slug])

  async function toggleDone() {
    if (!lesson || saving) return
    const next = !lesson.done
    // Optimistic: flip now, roll back if the write fails. Reading feels
    // instant and a failed write must not leave the box lying.
    setLesson({ ...lesson, done: next })
    setSaving(true)
    setError(null)
    try {
      const result = await setLessonProgress(lesson.id, next)
      setLesson((current) =>
        current === null ? current : { ...current, ...result },
      )
    } catch (err) {
      setLesson((current) =>
        current === null ? current : { ...current, done: !next },
      )
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="p-8 text-center text-sm text-gray-500">Đang tải…</p>
  }

  if (notFound || !lesson) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-8 text-center">
        <p className="text-sm text-gray-600">Không tìm thấy bài học.</p>
        <Link to="/lessons" className="text-sm underline">
          Về danh sách bài học
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <div className="space-y-2">
        <Link to="/lessons" className="text-sm text-gray-500 underline">
          ← Bài học
        </Link>
        {lesson.source_file_name && (
          <p className="text-xs text-gray-500">{lesson.source_file_name}</p>
        )}
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-xl font-semibold">{lesson.title}</h1>
          <label className="flex shrink-0 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={lesson.done}
              disabled={saving}
              onChange={() => void toggleDone()}
            />
            Đã học
          </label>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* No rehype-raw: react-markdown drops raw HTML by default, and lesson
          text comes from user-uploaded documents. Keep it that way. */}
      <article className="prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{lesson.content_md}</ReactMarkdown>
      </article>

      <nav className="flex justify-between gap-4 border-t pt-4 text-sm">
        {lesson.prev ? (
          <Link to={`/lessons/${lesson.prev.slug}`} className="underline">
            ← {lesson.prev.title}
          </Link>
        ) : (
          <span />
        )}
        {lesson.next ? (
          <Link to={`/lessons/${lesson.next.slug}`} className="text-right underline">
            {lesson.next.title} →
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </div>
  )
}
```

- [ ] **Step 2: Register the route**

Trong `frontend/src/App.tsx`, thêm import:

```tsx
import { LessonDetailPage } from "@/pages/LessonDetail"
```

và route ngay sau `/lessons`, vẫn **trước** `/*`:

```tsx
        <Route
          path="/lessons/:slug"
          element={
            <ProtectedRoute>
              <LessonDetailPage />
            </ProtectedRoute>
          }
        />
```

- [ ] **Step 3: Verify the build**

Run (từ `frontend/`): `npm run build`
Expected: không lỗi TypeScript.

- [ ] **Step 4: Lint**

Run (từ `frontend/`): `npm run lint`
Expected: sạch.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/LessonDetail.tsx frontend/src/App.tsx
git commit -m "feat(lessons): lesson reading page with markdown and progress toggle"
```

---

### Task 6: Verify thật + cập nhật tài liệu

**Files:**
- Create: `backend/scripts/verify_3.py`
- Modify: `check_list.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: `mint_access_token()` từ `backend/scripts/verify_1b.py`; cả ba endpoint của Task 1-3.
- Produces: không có (script một lần + tài liệu).

- [ ] **Step 1: Write the live verification script**

Tạo `backend/scripts/verify_3.py`:

```python
"""One-off live end-to-end check of #3: list -> read -> progress.

Checks what only a real run can establish:

  * GET /api/lessons returns this account's lessons, grouped-able by source
    file, with `done` merged in from lesson_progress.
  * GET /api/lessons/{slug} returns content_md matching the DB row, and
    prev/next in real chapter order.
  * PUT progress actually writes lesson_progress and can be turned back off.
  * the anon key reads 0 rows from lesson_progress (RLS is really on).
  * whatever this script wrote is removed again.

Usage: python scripts/verify_3.py
Requires the API running on http://localhost:8000 and at least one confirmed
lesson on the ADMIN_EMAIL account.
"""

import os
import sys

import httpx
from dotenv import load_dotenv

from verify_1b import mint_access_token

load_dotenv()

API = "http://localhost:8000"


def main() -> int:
    token = mint_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    lessons = httpx.get(f"{API}/api/lessons", headers=headers, timeout=30).json()
    print(f"GET /api/lessons -> {len(lessons)} lessons")
    if not lessons:
        print("FAIL: no lessons on this account; confirm a file first (#1b).")
        return 1
    for row in lessons:
        print(f"  [{row['source_file_name']}] #{row['order_index']} {row['title']}"
              f" done={row['done']}")

    target = lessons[0]
    detail = httpx.get(
        f"{API}/api/lessons/{target['slug']}", headers=headers, timeout=30
    ).json()
    print(f"\nGET /api/lessons/{target['slug']} -> {len(detail['content_md'])} chars")
    print(f"  prev={detail['prev']}  next={detail['next']}")
    assert detail["title"] == target["title"]

    # Compare against the DB directly, so a bug that mangles content_md on the
    # way out cannot pass by matching itself.
    base = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    db_row = httpx.get(
        f"{base}/rest/v1/lessons",
        params={"id": f"eq.{target['id']}", "select": "content_md"},
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        timeout=30,
    ).json()[0]
    assert detail["content_md"] == db_row["content_md"], "content_md differs from DB"
    print("  content_md matches the DB row")

    on = httpx.put(
        f"{API}/api/lessons/{target['id']}/progress",
        json={"done": True},
        headers=headers,
        timeout=30,
    ).json()
    print(f"\nPUT progress done=true -> {on}")
    assert on["done"] is True and on["completed_at"]

    anon = httpx.get(
        f"{base}/rest/v1/lesson_progress",
        params={"select": "lesson_id"},
        headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
        timeout=30,
    ).json()
    print(f"anon key sees {len(anon)} lesson_progress rows (must be 0)")
    assert anon == [], "RLS is NOT protecting lesson_progress"

    off = httpx.put(
        f"{API}/api/lessons/{target['id']}/progress",
        json={"done": False},
        headers=headers,
        timeout=30,
    ).json()
    print(f"PUT progress done=false -> {off}")
    assert off == {"done": False, "completed_at": None}

    # Leave the account exactly as found: drop the row this script created.
    httpx.delete(
        f"{base}/rest/v1/lesson_progress",
        params={"lesson_id": f"eq.{target['id']}"},
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        timeout=30,
    )
    print("cleaned up the lesson_progress row this script wrote")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against the real stack**

Bật backend (`python -m uvicorn app.main:app --port 8000` từ `backend/` trong venv), rồi:

Run (từ `backend/`): `python scripts/verify_3.py`
Expected: in ra danh sách bài thật, `content_md matches the DB row`, `anon key sees 0 lesson_progress rows`, và `ALL CHECKS PASSED`.

Nếu fail: **dừng lại và sửa code**, không sửa script cho vừa kết quả.

- [ ] **Step 3: Check the pages in a real browser**

Chạy `npm run dev` từ `frontend/`, đăng nhập, rồi kiểm bằng mắt:
- `/lessons` — bài gom đúng theo tài liệu, đếm `x/y` đúng, ba bộ lọc đổi danh sách đúng
- Mở một bài — markdown render ra tiêu đề/đoạn/danh sách, không phải chữ thô
- Tick "Đã học" → quay về `/lessons` thấy dấu "Đã học"; F5 vẫn còn
- Prev/next đi đúng chương, ẩn ở đầu và cuối tài liệu

- [ ] **Step 4: Update the checklist**

Trong `check_list.md`, thay mục `### #3 — Lessons UI` bằng bản đã đánh dấu xong: ghi rõ đã làm gì, ghi **D20-D23**, và ghi bằng chứng verify thật thu được ở Step 2-3. Thêm vào phần "Nợ kỹ thuật" bất cứ điều gì phát hiện lúc chạy thật.

- [ ] **Step 5: Update CLAUDE.md**

Trong `CLAUDE.md`, mục "Trạng thái hiện tại", ghi thêm một dòng rằng #3 đã xong và `/lessons` là nơi đọc bài; nêu rằng `topic`/`week` vẫn NULL nên phân nhóm đi theo file nguồn.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/verify_3.py check_list.md CLAUDE.md
git commit -m "docs: record #3 lessons UI verification and status"
```

---

## Sau khi xong

Chạy lần cuối `python -m pytest` (từ `backend/`) và `npm run build` (từ `frontend/`), rồi dùng skill `superpowers:finishing-a-development-branch` để chốt cách merge `feature/lessons-ui` vào `main`.
