# #1a — Upload → Extract → Cắt chương — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Từ một file user upload lên R2 (`.md`/`.docx`/`.pptx`/`.pdf`), backend extract sang markdown và cắt thành danh sách chương nháp lưu ở `user_files.draft_outline`, trạng thái `ready_for_review`.

**Architecture:** FastAPI router mỏng (`routers/files.py`) → gọi module nghiệp vụ. R2 truy cập qua `boto3` (S3-compatible), DB ghi bằng Supabase service-role client (bypass RLS, backend tự kiểm quyền theo `user_id` trong JWT). Xử lý nặng chạy trong `BackgroundTasks` cùng process. Pipeline tách đôi: `ingest/extractors/*.py` (phụ thuộc định dạng, `extract(bytes) -> str`) và `ingest/splitter.py` (chỉ ăn markdown thuần → test độc lập, không cần file mẫu).

**Tech Stack:** Python 3.11+, FastAPI, boto3, supabase-py, python-frontmatter, python-docx, python-pptx, pypdf, pytest.

## Global Constraints

- Ngôn ngữ: **mọi chuỗi hiển thị cho user (kể cả `error_message`) là tiếng Việt**; code/tên biến/comment/commit là tiếng Anh.
- Không endpoint nào nhận `user_id` từ client — luôn lấy từ JWT qua `Depends(get_current_user)`.
- Thao tác lên file không thuộc về user gọi → trả **404**, không bao giờ 403 (tránh lộ sự tồn tại của file người khác).
- Giới hạn upload: **20 MB**. Presigned URL hết hạn **15 phút** (900 giây).
- Trần **8000 ký tự** cho `content_md` mỗi chương.
- Graceful degradation: mọi lỗi trong background task → `processing_status='error'` + `error_message` tiếng Việt, **không** để exception thoát ra ngoài, **không** trả 500.
- `SUPABASE_SERVICE_ROLE_KEY` và mọi key R2 chỉ tồn tại ở backend, đọc từ biến môi trường. Không hardcode.
- Verify sau mỗi task: `pytest` từ `backend/` phải **xanh và output sạch** (không warning mới).
- Commit sau mỗi task hoàn thành (theo quy ước dự án).

## Bối cảnh có sẵn (đọc trước khi bắt đầu)

- Spec: `docs/superpowers/specs/2026-07-18-upload-extract-design.md`
- `backend/app/dependencies/auth.py` đã có `get_current_user()` → trả `CurrentUser(user_id: str, email: str | None)`.
- `backend/app/main.py` đã có `load_dotenv()`, CORS, `include_router(health)`, `include_router(me)`.
- `supabase/migrations/0002_tables.sql` đã tạo `lessons` và `user_files` (bản cũ, thời Obsidian).
- `supabase/migrations/0003_rls.sql` đã bật RLS + tạo policy `lessons_select` (**shared read** — task 1 phải bỏ policy này).
- Chạy backend local: `cd backend && .venv/Scripts/Activate.ps1 && python -m uvicorn app.main:app --port 8000`.

## File Structure

| File | Trách nhiệm |
|---|---|
| `supabase/migrations/0006_lessons_per_user_and_files.sql` | (tạo) Schema + RLS cho `lessons` per-user, nới `user_files` |
| `backend/app/config/settings.py` | (tạo) Đọc + validate biến môi trường R2/Supabase, một chỗ duy nhất |
| `backend/app/db.py` | (tạo) Supabase service-role client (singleton) |
| `backend/app/storage/r2.py` | (tạo) boto3 client + `presign_put()` / `object_exists()` / `download()` |
| `backend/app/ingest/chapter.py` | (tạo) dataclass `Chapter` |
| `backend/app/ingest/splitter.py` | (tạo) `split_into_chapters(md, fallback_title)` — thuần markdown |
| `backend/app/ingest/extractors/{md,docx,pptx,pdf}.py` | (tạo) mỗi file một hàm `extract(data: bytes) -> str` |
| `backend/app/ingest/extractors/__init__.py` | (tạo) `EXTRACTORS` dict + `ExtractError` |
| `backend/app/ingest/pipeline.py` | (tạo) `process_file(file_id)` — orchestrate, bắt mọi lỗi |
| `backend/app/routers/files.py` | (tạo) 4 endpoint |
| `backend/app/main.py` | (sửa) `include_router(files.router)` |
| `backend/requirements.txt`, `backend/.env.example` | (sửa) deps + env mới |
| `backend/tests/test_splitter.py`, `test_extractors.py`, `test_files_api.py` | (tạo) test |
| `backend/tests/fixtures/` | (tạo) file mẫu nhỏ cho extractor |

## Sai lệch có chủ ý so với spec (đã cân nhắc)

1. **Spec mục 6 thiếu `drop policy lessons_select`.** `0003_rls.sql` cho mọi user authenticated `select` trên `lessons`. Nếu không bỏ, policy per-user thêm vào là vô nghĩa (policy trong Postgres là OR). Task 1 bỏ nó.
2. **`split_into_chapters` bỏ tham số `file_type`.** Thay vì để splitter biết định dạng, extractor PDF tự chèn heading `##` (theo bookmark, hoặc mỗi 10 trang), extractor PPTX chèn `##` mỗi slide. Splitter chỉ còn một quy tắc duy nhất — heading cấp cao nhất thực sự có mặt — nên test được thuần túy, không cần fixture nhị phân. Đây là cách rẻ hơn để đạt đúng hành vi spec mô tả ở mục 5.2.
3. **Thêm `backend/app/db.py` dùng `supabase-py`** (spec không nói backend nói chuyện với DB kiểu gì). Chọn supabase-py vì không cần Postgres connection string riêng, dùng lại `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` đã có.

---

### Task 1: Migration 0006 — `lessons` per-user + nới `user_files`

**Files:**
- Create: `supabase/migrations/0006_lessons_per_user_and_files.sql`

**Interfaces:**
- Consumes: schema từ `0002_tables.sql`, policies từ `0003_rls.sql`
- Produces: bảng `lessons` có `user_id`/`source_file_id`/`order_index`; `user_files` có `draft_outline` và chấp nhận `file_type='md'`, `processing_status in ('ready_for_review','done')`

- [ ] **Step 1: Viết migration**

Tạo `supabase/migrations/0006_lessons_per_user_and_files.sql`:

```sql
-- 0006_lessons_per_user_and_files.sql
-- Sub-project #1a. Lessons become PRIVATE per user (each user uploads their own
-- material), and user_files gains the draft chapter outline produced by ingest.

-- ---------------------------------------------------------------------------
-- lessons: shared content -> private per user.
-- ---------------------------------------------------------------------------
alter table lessons
  add column if not exists user_id uuid not null references auth.users(id) on delete cascade,
  add column if not exists source_file_id uuid references user_files(id) on delete set null,
  add column if not exists order_index int not null default 0;

-- Slug is only unique within one user's library now.
alter table lessons drop constraint if exists lessons_slug_key;
create unique index if not exists lessons_user_slug_idx on lessons (user_id, slug);

-- 0003 granted every authenticated user SELECT on lessons (content used to be
-- shared). Policies are OR-ed, so that policy must go or per-user isolation
-- would be a no-op.
drop policy if exists "lessons_select" on lessons;

alter table lessons enable row level security;
create policy "lessons_own" on lessons
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- user_files: draft outline + wider type/status vocabularies.
-- ---------------------------------------------------------------------------
alter table user_files add column if not exists draft_outline jsonb;

alter table user_files drop constraint if exists user_files_file_type_check;
alter table user_files add constraint user_files_file_type_check
  check (file_type in ('md', 'pdf', 'docx', 'pptx'));

alter table user_files drop constraint if exists user_files_processing_status_check;
alter table user_files add constraint user_files_processing_status_check
  check (processing_status in
    ('pending', 'processing', 'ready_for_review', 'done', 'error'));
```

Ghi chú: bỏ `'image'` khỏi `file_type` — không định dạng nào trong #1a dùng nó và bảng đang rỗng. Bỏ `'ready'` khỏi status vì vòng đời mới dùng `ready_for_review`.

- [ ] **Step 2: Apply lên Supabase thật**

Mở Supabase Dashboard → SQL Editor → dán nội dung file → Run.
Expected: `Success. No rows returned`.

Nếu báo lỗi `column user_id contains null values`: bảng `lessons` không rỗng như giả định — **dừng lại**, báo user, đừng tự xóa dữ liệu.

- [ ] **Step 3: Verify schema**

Chạy trong SQL Editor:

```sql
select column_name, is_nullable
from information_schema.columns
where table_name = 'lessons' and column_name in ('user_id','source_file_id','order_index')
order by column_name;

select policyname from pg_policies where tablename = 'lessons';
```

Expected: query 1 trả 3 dòng (`order_index` NO, `source_file_id` YES, `user_id` NO).
Query 2 trả **đúng một** dòng: `lessons_own`. Nếu còn `lessons_select` → policy chưa bị drop, sửa rồi chạy lại.

- [ ] **Step 4: Verify RLS thật bằng anon key**

Chạy từ `backend/` với venv đã activate (thay `<...>` bằng giá trị trong `.env`; anon key lấy từ `frontend/.env`):

```bash
python -c "
import os, urllib.request, json
url = os.environ['SUPABASE_URL'] + '/rest/v1/lessons?select=id'
key = '<ANON_KEY>'
req = urllib.request.Request(url, headers={'apikey': key, 'Authorization': 'Bearer ' + key})
print(json.load(urllib.request.urlopen(req)))
"
```

Expected: `[]` — anon chưa đăng nhập không đọc được dòng nào (kể cả khi bảng có dữ liệu).

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0006_lessons_per_user_and_files.sql
git commit -m "feat(db): 0006 make lessons private per user, extend user_files"
```

---

### Task 2: Cấu hình — deps, env, R2 client, Supabase client

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`
- Create: `backend/app/config/settings.py`
- Create: `backend/app/db.py`
- Create: `backend/app/storage/__init__.py` (rỗng)
- Create: `backend/app/storage/r2.py`
- Test: `backend/tests/test_settings.py`

**Interfaces:**
- Produces:
  - `settings.r2_bucket() -> str`, `settings.r2_endpoint() -> str`, `settings.MAX_FILE_BYTES: int`, `settings.PRESIGN_EXPIRY_SECONDS: int`, `settings.ALLOWED_FILE_TYPES: frozenset[str]`
  - `db.admin() -> Client` (supabase-py client dùng service-role key)
  - `r2.presign_put(key: str, content_length: int) -> str`
  - `r2.object_exists(key: str) -> bool`
  - `r2.download(key: str) -> bytes`

- [ ] **Step 1: Thêm dependencies**

Sửa `backend/requirements.txt`, thêm vào cuối:

```
boto3>=1.35
supabase>=2.9
python-frontmatter>=1.1
python-docx>=1.1
python-pptx>=1.0
pypdf>=5.1
```

Cài: `cd backend && .venv/Scripts/Activate.ps1 && pip install -r requirements.txt`

- [ ] **Step 2: Thêm biến môi trường**

Sửa `backend/.env.example`, thêm vào cuối:

```
# --- Cloudflare R2 (S3-compatible object storage) ---
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=
```

Rồi điền giá trị thật vào `backend/.env` (file này KHÔNG commit). Nếu chưa có key R2 → dừng, hỏi user.

- [ ] **Step 3: Viết test cho settings**

Tạo `backend/tests/test_settings.py`:

```python
import pytest

from app.config import settings


def test_r2_endpoint_is_built_from_account_id(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "abc123")
    assert settings.r2_endpoint() == "https://abc123.r2.cloudflarestorage.com"


def test_missing_r2_config_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
    with pytest.raises(RuntimeError, match="R2_ACCOUNT_ID"):
        settings.r2_endpoint()


def test_limits_match_the_spec():
    assert settings.MAX_FILE_BYTES == 20 * 1024 * 1024
    assert settings.PRESIGN_EXPIRY_SECONDS == 900
    assert settings.ALLOWED_FILE_TYPES == frozenset({"md", "docx", "pptx", "pdf"})
```

- [ ] **Step 4: Chạy test để thấy nó fail**

Run: `cd backend && python -m pytest tests/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config.settings'`

- [ ] **Step 5: Viết `settings.py`**

Tạo `backend/app/config/settings.py`:

```python
"""Single place that reads and validates environment configuration.

Values are read lazily (inside functions, not at import time) so tests can
monkeypatch the environment and so importing the app never fails on a machine
with incomplete config.
"""

import os

MAX_FILE_BYTES = 20 * 1024 * 1024
PRESIGN_EXPIRY_SECONDS = 900
ALLOWED_FILE_TYPES = frozenset({"md", "docx", "pptx", "pdf"})
MAX_CHAPTER_CHARS = 8000


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def r2_endpoint() -> str:
    return f"https://{_required('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"


def r2_bucket() -> str:
    return _required("R2_BUCKET")


def r2_access_key_id() -> str:
    return _required("R2_ACCESS_KEY_ID")


def r2_secret_access_key() -> str:
    return _required("R2_SECRET_ACCESS_KEY")


def supabase_url() -> str:
    return _required("SUPABASE_URL")


def supabase_service_role_key() -> str:
    return _required("SUPABASE_SERVICE_ROLE_KEY")
```

- [ ] **Step 6: Chạy test để thấy nó pass**

Run: `cd backend && python -m pytest tests/test_settings.py -v`
Expected: 3 passed

- [ ] **Step 7: Viết `db.py`**

Tạo `backend/app/db.py`:

```python
"""Supabase client using the SERVICE ROLE key — it bypasses RLS.

Every query issued through this client MUST filter by user_id explicitly;
the database will not do it for us here. The key never leaves the backend.
"""

import functools

from supabase import Client, create_client

from app.config import settings


@functools.lru_cache(maxsize=1)
def admin() -> Client:
    return create_client(
        settings.supabase_url(), settings.supabase_service_role_key()
    )
```

- [ ] **Step 8: Viết `storage/r2.py`**

Tạo `backend/app/storage/__init__.py` (file rỗng) và `backend/app/storage/r2.py`:

```python
"""Cloudflare R2 access (S3-compatible) via boto3."""

import functools

import boto3
from botocore.client import Config

from app.config import settings


@functools.lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint(),
        aws_access_key_id=settings.r2_access_key_id(),
        aws_secret_access_key=settings.r2_secret_access_key(),
        # R2 ignores regions but boto3 requires one; "auto" is what R2 documents.
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def presign_put(key: str, content_length: int) -> str:
    """URL the browser can PUT the file to directly, bypassing our backend.

    ContentLength is signed in so the client cannot upload something larger
    than what we validated.
    """
    return _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.r2_bucket(),
            "Key": key,
            "ContentLength": content_length,
        },
        ExpiresIn=settings.PRESIGN_EXPIRY_SECONDS,
    )


def object_exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=settings.r2_bucket(), Key=key)
        return True
    except _client().exceptions.ClientError:
        return False


def download(key: str) -> bytes:
    response = _client().get_object(Bucket=settings.r2_bucket(), Key=key)
    return response["Body"].read()
```

- [ ] **Step 9: Chạy toàn bộ test**

Run: `cd backend && python -m pytest -v`
Expected: 10 passed (7 cũ + 3 mới), **không warning mới**. Nếu supabase/boto3 sinh DeprecationWarning, ghi lại nhưng đừng suppress vội — báo ở phần review.

- [ ] **Step 10: Commit**

```bash
git add backend/requirements.txt backend/.env.example backend/app/config/settings.py backend/app/db.py backend/app/storage backend/tests/test_settings.py
git commit -m "feat(backend): add R2 storage client, supabase admin client, settings module"
```

---

### Task 3: `splitter.py` — cắt markdown thành chương

**Files:**
- Create: `backend/app/ingest/__init__.py` (rỗng)
- Create: `backend/app/ingest/chapter.py`
- Create: `backend/app/ingest/splitter.py`
- Test: `backend/tests/test_splitter.py`

**Interfaces:**
- Consumes: `settings.MAX_CHAPTER_CHARS`
- Produces:
  - `Chapter` dataclass với `title: str`, `content_md: str`, `order_index: int`, method `to_dict() -> dict`
  - `split_into_chapters(md: str, fallback_title: str) -> list[Chapter]`

Đây là phần logic nhiều nhất và hoàn toàn thuần túy — làm TDD nghiêm túc, viết hết test trước.

- [ ] **Step 1: Viết toàn bộ test**

Tạo `backend/tests/test_splitter.py`:

```python
from app.ingest.splitter import split_into_chapters


def test_splits_on_h1_when_present():
    md = "# A\nnoi dung a\n\n# B\nnoi dung b\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.title for c in chapters] == ["A", "B"]
    assert "noi dung a" in chapters[0].content_md
    assert "noi dung b" in chapters[1].content_md


def test_falls_back_to_h2_when_no_h1():
    md = "## A\nx\n\n## B\ny\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.title for c in chapters] == ["A", "B"]


def test_deeper_headings_stay_inside_their_chapter():
    md = "# A\n## A1\nx\n### A2\ny\n\n# B\nz\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters) == 2
    assert "A1" in chapters[0].content_md
    assert "A2" in chapters[0].content_md


def test_long_preamble_becomes_its_own_chapter():
    md = "loi noi dau " * 30 + "\n\n# A\nx\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert chapters[0].title == "Mở đầu"
    assert chapters[1].title == "A"


def test_short_preamble_is_merged_into_the_first_chapter():
    md = "ngan gon\n\n# A\nx\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters) == 1
    assert chapters[0].title == "A"
    assert "ngan gon" in chapters[0].content_md


def test_document_without_any_heading_becomes_one_chapter_named_after_the_file():
    md = "chi co van ban thuan tuy, khong heading nao ca"
    chapters = split_into_chapters(md, fallback_title="giao-trinh")
    assert len(chapters) == 1
    assert chapters[0].title == "giao-trinh"


def test_empty_chapters_are_dropped():
    md = "# A\nx\n\n# Rong\n\n   \n\n# B\ny\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.title for c in chapters] == ["A", "B"]


def test_order_index_is_sequential_from_zero():
    md = "# A\nx\n\n# B\ny\n\n# C\nz\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.order_index for c in chapters] == [0, 1, 2]


def test_oversized_chapter_is_split_on_sub_headings():
    body = "chu " * 3000  # ~12000 chars, over the 8000 cap
    md = f"# A\n## A1\n{body}\n## A2\n{body}\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters) >= 2
    assert all(len(c.content_md) <= 8000 for c in chapters)


def test_oversized_chapter_without_sub_headings_is_hard_split():
    md = "# A\n" + ("mot doan van rat dai. " * 1200)
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters) >= 2
    assert all(len(c.content_md) <= 8000 for c in chapters)


def test_title_is_truncated_to_200_chars():
    md = "# " + ("t" * 300) + "\nx\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters[0].title) == 200


def test_headings_inside_fenced_code_blocks_are_not_boundaries():
    md = "# A\n```\n# khong phai heading\n```\nx\n\n# B\ny\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.title for c in chapters] == ["A", "B"]


def test_empty_document_yields_no_chapters():
    assert split_into_chapters("   \n\n  ", fallback_title="tai-lieu") == []


def test_chapter_serialises_to_the_draft_outline_shape():
    chapters = split_into_chapters("# A\nx\n", fallback_title="tai-lieu")
    assert chapters[0].to_dict() == {
        "title": "A",
        "content_md": chapters[0].content_md,
        "order_index": 0,
    }
```

- [ ] **Step 2: Chạy test để thấy nó fail**

Run: `cd backend && python -m pytest tests/test_splitter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingest'`

- [ ] **Step 3: Viết `chapter.py`**

Tạo `backend/app/ingest/__init__.py` (rỗng) và `backend/app/ingest/chapter.py`:

```python
from dataclasses import dataclass


@dataclass
class Chapter:
    title: str
    content_md: str
    order_index: int

    def to_dict(self) -> dict:
        """Shape stored in user_files.draft_outline (jsonb)."""
        return {
            "title": self.title,
            "content_md": self.content_md,
            "order_index": self.order_index,
        }
```

- [ ] **Step 4: Viết `splitter.py`**

Tạo `backend/app/ingest/splitter.py`:

```python
"""Cut a markdown document into chapter-sized pieces.

Pure markdown in, chapters out — no knowledge of the source format. Format
specific structure (PDF page breaks, PPTX slides) is turned into headings by
the extractors before the text reaches here, so there is exactly one rule.
"""

import re

from app.config.settings import MAX_CHAPTER_CHARS
from app.ingest.chapter import Chapter

MAX_TITLE_CHARS = 200
MIN_PREAMBLE_CHARS = 200
PREAMBLE_TITLE = "Mở đầu"

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def _heading_lines(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return (line_index, level, text) for headings outside fenced code."""
    found: list[tuple[int, int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            found.append((index, len(match.group(1)), match.group(2).strip()))
    return found


def _sections(md: str, level: int) -> list[tuple[str, list[str]]]:
    """Split `md` at headings of exactly `level`.

    Returns (title, body_lines) pairs. Text before the first heading comes back
    with the sentinel title "" so the caller can decide what to do with it.
    """
    lines = md.splitlines()
    boundaries = [i for i, lvl, _ in _heading_lines(lines) if lvl == level]
    titles = {i: text for i, lvl, text in _heading_lines(lines) if lvl == level}

    sections: list[tuple[str, list[str]]] = []
    preamble_end = boundaries[0] if boundaries else len(lines)
    sections.append(("", lines[:preamble_end]))

    for position, start in enumerate(boundaries):
        end = boundaries[position + 1] if position + 1 < len(boundaries) else len(lines)
        sections.append((titles[start], lines[start + 1 : end]))
    return sections


def _hard_split(text: str) -> list[str]:
    """Last resort: pack paragraphs into <= MAX_CHAPTER_CHARS pieces."""
    pieces: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= MAX_CHAPTER_CHARS:
            current = candidate
            continue
        if current:
            pieces.append(current)
        # A single paragraph can still be too long — chop it on the char cap.
        while len(paragraph) > MAX_CHAPTER_CHARS:
            pieces.append(paragraph[:MAX_CHAPTER_CHARS])
            paragraph = paragraph[MAX_CHAPTER_CHARS:]
        current = paragraph
    if current.strip():
        pieces.append(current)
    return pieces


def _shrink(title: str, body: str, level: int) -> list[tuple[str, str]]:
    """Break an oversized chapter down until every piece fits the cap."""
    if len(body) <= MAX_CHAPTER_CHARS:
        return [(title, body)]

    lines = body.splitlines()
    deeper = [lvl for _, lvl, _ in _heading_lines(lines) if lvl > level]
    if deeper:
        next_level = min(deeper)
        result: list[tuple[str, str]] = []
        for sub_title, sub_lines in _sections(body, next_level):
            sub_body = "\n".join(sub_lines).strip()
            if not sub_body:
                continue
            label = sub_title[:MAX_TITLE_CHARS] if sub_title else title
            result.extend(_shrink(label, sub_body, next_level))
        if result:
            return result

    return [
        (f"{title} ({n + 1})", piece)
        for n, piece in enumerate(_hard_split(body))
    ]


def split_into_chapters(md: str, fallback_title: str) -> list[Chapter]:
    if not md.strip():
        return []

    lines = md.splitlines()
    levels = [lvl for _, lvl, _ in _heading_lines(lines)]
    if not levels:
        pairs = [(fallback_title[:MAX_TITLE_CHARS], md.strip())]
        return _to_chapters(pairs)

    top_level = min(levels)
    sections = _sections(md, top_level)

    pairs: list[tuple[str, str]] = []
    preamble = "\n".join(sections[0][1]).strip()
    rest = sections[1:]

    if preamble and len(preamble) >= MIN_PREAMBLE_CHARS:
        pairs.append((PREAMBLE_TITLE, preamble))
        preamble = ""

    for position, (title, body_lines) in enumerate(rest):
        body = "\n".join(body_lines).strip()
        # A short preamble is glued onto the first real chapter instead of
        # becoming a stub of its own.
        if position == 0 and preamble:
            body = f"{preamble}\n\n{body}".strip()
        if not body:
            continue
        pairs.append((title[:MAX_TITLE_CHARS], body))

    expanded: list[tuple[str, str]] = []
    for title, body in pairs:
        expanded.extend(_shrink(title, body, top_level))
    return _to_chapters(expanded)


def _to_chapters(pairs: list[tuple[str, str]]) -> list[Chapter]:
    return [
        Chapter(title=title, content_md=body, order_index=index)
        for index, (title, body) in enumerate(
            (t, b) for t, b in pairs if b.strip()
        )
    ]
```

- [ ] **Step 5: Chạy test cho tới khi xanh**

Run: `cd backend && python -m pytest tests/test_splitter.py -v`
Expected: 14 passed.

Nếu `test_short_preamble_is_merged_into_the_first_chapter` fail vì đếm ra 2 chương → kiểm tra nhánh `position == 0 and preamble`. Nếu `test_oversized_chapter_...` fail vì có mảnh > 8000 → kiểm `_hard_split` có xử lý đoạn đơn quá dài không.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingest backend/tests/test_splitter.py
git commit -m "feat(ingest): split markdown into capped chapters"
```

---

### Task 4: 4 extractor

**Files:**
- Create: `backend/app/ingest/extractors/__init__.py`
- Create: `backend/app/ingest/extractors/{md,docx,pptx,pdf}.py`
- Test: `backend/tests/test_extractors.py`

Không cần thư mục `tests/fixtures/`: test tự sinh file mẫu trong bộ nhớ bằng chính
`python-docx`/`python-pptx`/`pypdf`, khỏi commit file nhị phân.

**Interfaces:**
- Produces:
  - `ExtractError(Exception)` — message là tiếng Việt, hiển thị thẳng cho user
  - `EXTRACTORS: dict[str, Callable[[bytes], str]]` với key `'md'|'docx'|'pptx'|'pdf'`
  - mỗi module có `extract(data: bytes) -> str`

- [ ] **Step 1: Viết test**

Tạo `backend/tests/test_extractors.py`:

```python
import io

import pytest
from docx import Document
from pptx import Presentation

from app.ingest.extractors import EXTRACTORS, ExtractError
from app.ingest.extractors import md as md_extractor
from app.ingest.extractors import pdf as pdf_extractor


def test_registry_covers_all_four_formats():
    assert set(EXTRACTORS) == {"md", "docx", "pptx", "pdf"}


def test_md_keeps_the_body_and_drops_frontmatter():
    raw = b"---\ntitle: Bai 1\n---\n\n# Chuong 1\nnoi dung\n"
    result = md_extractor.extract(raw)
    assert "# Chuong 1" in result
    assert "title: Bai 1" not in result


def test_md_without_frontmatter_is_unchanged():
    raw = b"# Chuong 1\nnoi dung\n"
    assert md_extractor.extract(raw).strip() == "# Chuong 1\nnoi dung"


def test_docx_maps_headings_and_lists_to_markdown():
    document = Document()
    document.add_heading("Chuong mot", level=1)
    document.add_paragraph("doan van thuong")
    document.add_paragraph("mot muc", style="List Bullet")
    document.add_heading("Muc con", level=2)
    buffer = io.BytesIO()
    document.save(buffer)

    result = EXTRACTORS["docx"](buffer.getvalue())
    assert "# Chuong mot" in result
    assert "## Muc con" in result
    assert "- mot muc" in result
    assert "doan van thuong" in result


def test_pptx_turns_each_slide_into_an_h2():
    presentation = Presentation()
    for title_text in ("Slide mot", "Slide hai"):
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = title_text
        slide.placeholders[1].text = f"noi dung {title_text}"
    buffer = io.BytesIO()
    presentation.save(buffer)

    result = EXTRACTORS["pptx"](buffer.getvalue())
    assert "## Slide mot" in result
    assert "## Slide hai" in result
    assert "noi dung Slide hai" in result


def test_pdf_without_text_layer_raises_a_vietnamese_error():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(ExtractError) as err:
        pdf_extractor.extract(buffer.getvalue())
    assert "không có văn bản" in str(err.value)


def test_corrupt_bytes_raise_extract_error_not_a_library_exception():
    for file_type in ("docx", "pptx", "pdf"):
        with pytest.raises(ExtractError):
            EXTRACTORS[file_type](b"day khong phai file hop le")
```

- [ ] **Step 2: Chạy test để thấy nó fail**

Run: `cd backend && python -m pytest tests/test_extractors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingest.extractors'`

Ghi chú: test tự sinh file mẫu trong bộ nhớ bằng chính `python-docx`/`python-pptx`/`pypdf` nên **không cần thư mục `tests/fixtures/`** — bỏ nó khỏi kế hoạch, đỡ commit file nhị phân.

- [ ] **Step 3: Viết `extractors/md.py`**

```python
"""Markdown files: strip YAML frontmatter, keep the body verbatim."""

import frontmatter

from app.ingest.extractors.errors import ExtractError


def extract(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as err:
        raise ExtractError(
            "File markdown không đọc được — hãy lưu lại ở dạng UTF-8."
        ) from err
    try:
        post = frontmatter.loads(text)
    except Exception:
        # Malformed frontmatter is not worth failing over — keep the raw text.
        return text.strip()
    return post.content.strip()
```

- [ ] **Step 4: Viết `extractors/errors.py`**

```python
class ExtractError(Exception):
    """Extraction failed for a reason the user can act on.

    The message is Vietnamese and is surfaced directly as
    user_files.error_message, so it must stay user-facing prose.
    """
```

- [ ] **Step 5: Viết `extractors/docx.py`**

```python
"""DOCX: headings 1-3 become #/##/###, bullets become '-', rest stays prose."""

import io

from docx import Document

from app.ingest.extractors.errors import ExtractError


def extract(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
    except Exception as err:
        raise ExtractError(
            "Không mở được file .docx — file có thể hỏng hoặc không đúng định dạng."
        ) from err

    parts: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower()
        if style.startswith("heading"):
            level = _heading_level(style)
            parts.append(f"{'#' * level} {text}")
        elif "list" in style:
            parts.append(f"- {text}")
        else:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _heading_level(style_name: str) -> int:
    """'heading 2' -> 2, clamped to 1..3 as the spec only maps three levels."""
    tail = style_name.replace("heading", "").strip()
    try:
        return min(max(int(tail), 1), 3)
    except ValueError:
        return 1
```

- [ ] **Step 6: Viết `extractors/pptx.py`**

```python
"""PPTX: one slide becomes one '## <title>' section so the splitter can cut it."""

import io

from pptx import Presentation

from app.ingest.extractors.errors import ExtractError


def extract(data: bytes) -> str:
    try:
        presentation = Presentation(io.BytesIO(data))
    except Exception as err:
        raise ExtractError(
            "Không mở được file .pptx — file có thể hỏng hoặc không đúng định dạng."
        ) from err

    parts: list[str] = []
    for number, slide in enumerate(presentation.slides, start=1):
        title = _title_of(slide) or f"Slide {number}"
        parts.append(f"## {title}")
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if text and text != title:
                parts.append(text)
    return "\n\n".join(parts).strip()


def _title_of(slide) -> str:
    placeholder = slide.shapes.title
    if placeholder is None:
        return ""
    return placeholder.text.strip()
```

- [ ] **Step 7: Viết `extractors/pdf.py`**

```python
"""PDF: text layer only (no OCR).

The PDF is the one format that carries structure the splitter cannot see, so
this extractor injects '## ' headings itself — from the document outline when
there is one, otherwise every PAGES_PER_CHAPTER pages.
"""

import io

from pypdf import PdfReader

from app.ingest.extractors.errors import ExtractError

PAGES_PER_CHAPTER = 10
MIN_USABLE_CHARS = 100


def extract(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as err:
        raise ExtractError(
            "Không mở được file .pdf — file có thể hỏng hoặc được đặt mật khẩu."
        ) from err

    if sum(len(text) for text in pages) < MIN_USABLE_CHARS:
        raise ExtractError(
            "File PDF này không có văn bản (có thể là bản scan/ảnh). "
            "Hãy dùng bản PDF có text, hoặc chuyển sang .docx rồi tải lại."
        )

    titles = _outline_titles(reader, len(pages))
    parts: list[str] = []
    for index, text in enumerate(pages):
        if index in titles:
            parts.append(f"## {titles[index]}")
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _outline_titles(reader: PdfReader, page_count: int) -> dict[int, str]:
    """Map page index -> chapter heading, from bookmarks or a fixed page stride."""
    titles: dict[int, str] = {}
    try:
        for item in reader.outline or []:
            # Nested outline levels come through as lists; only top level is used.
            if isinstance(item, list):
                continue
            page_index = reader.get_page_number(item.page)
            titles.setdefault(page_index, str(item.title).strip())
    except Exception:
        # A broken outline must not sink an otherwise readable PDF.
        titles = {}

    if titles:
        return titles
    return {
        index: f"Phần {index // PAGES_PER_CHAPTER + 1}"
        for index in range(0, page_count, PAGES_PER_CHAPTER)
    }
```

- [ ] **Step 8: Viết `extractors/__init__.py`**

```python
from collections.abc import Callable

from app.ingest.extractors import docx, md, pdf, pptx
from app.ingest.extractors.errors import ExtractError

EXTRACTORS: dict[str, Callable[[bytes], str]] = {
    "md": md.extract,
    "docx": docx.extract,
    "pptx": pptx.extract,
    "pdf": pdf.extract,
}

__all__ = ["EXTRACTORS", "ExtractError"]
```

- [ ] **Step 9: Chạy test cho tới khi xanh**

Run: `cd backend && python -m pytest tests/test_extractors.py -v`
Expected: 7 passed.

Nếu `test_pptx_...` fail vì `slide_layouts[1]` không có placeholder 1 → đổi sang layout khác và sửa test cho khớp. Nếu `test_corrupt_bytes_...` fail vì thư viện raise thay vì `ExtractError` → mở rộng `except` trong extractor tương ứng.

- [ ] **Step 10: Chạy toàn bộ test**

Run: `cd backend && python -m pytest -v`
Expected: tất cả xanh, output sạch.

- [ ] **Step 11: Commit**

```bash
git add backend/app/ingest/extractors backend/tests/test_extractors.py
git commit -m "feat(ingest): add md/docx/pptx/pdf extractors"
```

---

### Task 5: Pipeline xử lý nền

**Files:**
- Create: `backend/app/ingest/pipeline.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `EXTRACTORS`, `ExtractError`, `split_into_chapters`, `r2.download`, `db.admin`
- Produces: `process_file(file_id: str) -> None` — không bao giờ raise

- [ ] **Step 1: Viết test**

Tạo `backend/tests/test_pipeline.py`:

```python
import pytest

from app.ingest import pipeline


class _FakeTable:
    def __init__(self, store, row):
        self._store = store
        self._row = row
        self._update = None

    def select(self, *_):
        return self

    def update(self, values):
        self._update = values
        return self

    def eq(self, *_):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        if self._update is not None:
            self._store.update(self._update)
            self._update = None
            return type("Res", (), {"data": [self._store]})()
        return type("Res", (), {"data": dict(self._row)})()


class _FakeClient:
    def __init__(self, row):
        self.row = row

    def table(self, _name):
        return _FakeTable(self.row, self.row)


@pytest.fixture
def fake_db(monkeypatch):
    row = {
        "id": "f1",
        "user_id": "u1",
        "file_name": "giao-trinh.md",
        "file_type": "md",
        "storage_path": "u1/f1.md",
        "processing_status": "processing",
    }
    client = _FakeClient(row)
    monkeypatch.setattr(pipeline.db, "admin", lambda: client)
    return row


def test_successful_run_stores_the_outline_and_marks_ready(fake_db, monkeypatch):
    monkeypatch.setattr(
        pipeline.r2, "download", lambda key: b"# A\nnoi dung a\n\n# B\nnoi dung b\n"
    )
    pipeline.process_file("f1")

    assert fake_db["processing_status"] == "ready_for_review"
    assert [c["title"] for c in fake_db["draft_outline"]] == ["A", "B"]
    assert fake_db["error_message"] is None


def test_extract_error_is_recorded_as_a_vietnamese_message(fake_db, monkeypatch):
    fake_db["file_type"] = "pdf"
    fake_db["storage_path"] = "u1/f1.pdf"
    monkeypatch.setattr(pipeline.r2, "download", lambda key: b"khong phai pdf")

    pipeline.process_file("f1")

    assert fake_db["processing_status"] == "error"
    assert "pdf" in fake_db["error_message"].lower()


def test_unexpected_exception_does_not_escape(fake_db, monkeypatch):
    def boom(_key):
        raise ConnectionError("R2 down")

    monkeypatch.setattr(pipeline.r2, "download", boom)

    pipeline.process_file("f1")  # must not raise

    assert fake_db["processing_status"] == "error"
    assert fake_db["error_message"]


def test_document_with_no_usable_content_is_an_error(fake_db, monkeypatch):
    monkeypatch.setattr(pipeline.r2, "download", lambda key: b"   \n  ")

    pipeline.process_file("f1")

    assert fake_db["processing_status"] == "error"
    assert "nội dung" in fake_db["error_message"]
```

- [ ] **Step 2: Chạy test để thấy nó fail**

Run: `cd backend && python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingest.pipeline'`

- [ ] **Step 3: Viết `pipeline.py`**

```python
"""Background job: R2 object -> markdown -> chapters -> draft_outline.

Runs inside the API process via FastAPI BackgroundTasks (D4 — under 10 users
does not justify a queue). Nothing here may raise: a failure must land in the
row as an actionable Vietnamese message so #1b can offer a retry.
"""

import logging
from pathlib import Path

from app import db
from app.ingest.extractors import EXTRACTORS, ExtractError
from app.ingest.splitter import split_into_chapters
from app.storage import r2

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Xử lý file thất bại do lỗi hệ thống. Hãy thử lại sau ít phút."
EMPTY_ERROR = "Không trích xuất được nội dung nào từ file này."


def process_file(file_id: str) -> None:
    try:
        row = _load(file_id)
        if row is None:
            logger.warning("process_file: %s no longer exists", file_id)
            return

        data = r2.download(row["storage_path"])
        raw_md = EXTRACTORS[row["file_type"]](data)

        fallback = Path(row["file_name"]).stem
        chapters = split_into_chapters(raw_md, fallback_title=fallback)
        if not chapters:
            _fail(file_id, EMPTY_ERROR)
            return

        _finish(file_id, [chapter.to_dict() for chapter in chapters])
    except ExtractError as err:
        _fail(file_id, str(err))
    except Exception:
        # Anything unexpected (network, R2, DB) — log the detail for us, show
        # the user something generic rather than a stack trace.
        logger.exception("process_file failed for %s", file_id)
        _fail(file_id, GENERIC_ERROR)


def _load(file_id: str) -> dict | None:
    result = (
        db.admin()
        .table("user_files")
        .select("id, user_id, file_name, file_type, storage_path")
        .eq("id", file_id)
        .maybe_single()
        .execute()
    )
    return result.data


def _finish(file_id: str, outline: list[dict]) -> None:
    _update(
        file_id,
        {
            "processing_status": "ready_for_review",
            "draft_outline": outline,
            "error_message": None,
        },
    )


def _fail(file_id: str, message: str) -> None:
    try:
        _update(
            file_id, {"processing_status": "error", "error_message": message}
        )
    except Exception:
        # If even the failure write fails the row stays 'processing'; #1b's
        # stuck-file retry button is the backstop.
        logger.exception("could not record failure for %s", file_id)


def _update(file_id: str, values: dict) -> None:
    db.admin().table("user_files").update(values).eq("id", file_id).execute()
```

- [ ] **Step 4: Chạy test cho tới khi xanh**

Run: `cd backend && python -m pytest tests/test_pipeline.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingest/pipeline.py backend/tests/test_pipeline.py
git commit -m "feat(ingest): background pipeline extracting files into draft outlines"
```

---

### Task 6: Router `/api/files`

**Files:**
- Create: `backend/app/routers/files.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_files_api.py`

**Interfaces:**
- Consumes: `get_current_user`, `settings`, `r2`, `db`, `pipeline.process_file`
- Produces: 4 endpoint theo spec mục 4

- [ ] **Step 1: Viết test**

Tạo `backend/tests/test_files_api.py`:

```python
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.main import app
from app.routers import files as files_router

client = TestClient(app)

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_USER_ID = "11111111-1111-1111-1111-111111111111"
_OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _auth(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example-project.supabase.co")
    monkeypatch.setattr(
        "app.dependencies.auth._get_signing_key", lambda token: _PUBLIC_KEY
    )


def _headers(user_id: str = _USER_ID) -> dict:
    token = jwt.encode(
        {"sub": user_id, "email": "a@b.c", "aud": "authenticated"},
        _PRIVATE_KEY,
        algorithm="ES256",
    )
    return {"Authorization": f"Bearer {token}"}


class _FakeRepo:
    """Stands in for every db call the router makes."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.inserted: list[dict] = []

    def insert_file(self, values):
        self.rows[values["id"]] = dict(values)
        self.inserted.append(values)

    def get_file(self, file_id, user_id):
        row = self.rows.get(file_id)
        if row is None or row["user_id"] != user_id:
            return None
        return row

    def list_files(self, user_id):
        return [r for r in self.rows.values() if r["user_id"] == user_id]

    def set_status(self, file_id, status):
        self.rows[file_id]["processing_status"] = status


@pytest.fixture
def repo(monkeypatch):
    fake = _FakeRepo()
    monkeypatch.setattr(files_router, "repo", fake)
    monkeypatch.setattr(files_router.r2, "presign_put", lambda k, n: f"https://r2/{k}")
    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: True)
    monkeypatch.setattr(files_router.pipeline, "process_file", lambda file_id: None)
    return fake


# --- presign -----------------------------------------------------------------

def test_presign_rejects_a_file_over_20mb(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.pdf", "file_type": "pdf", "file_size": 21 * 1024 * 1024},
        headers=_headers(),
    )
    assert res.status_code == 400
    assert repo.inserted == []


def test_presign_rejects_an_unknown_file_type(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.exe", "file_type": "exe", "file_size": 100},
        headers=_headers(),
    )
    assert res.status_code == 422


def test_presign_creates_a_pending_row_with_a_user_scoped_key(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.pdf", "file_type": "pdf", "file_size": 1000},
        headers=_headers(),
    )
    assert res.status_code == 200
    body = res.json()
    file_id = body["file_id"]
    assert body["storage_path"] == f"{_USER_ID}/{file_id}.pdf"
    assert repo.rows[file_id]["processing_status"] == "pending"
    assert repo.rows[file_id]["user_id"] == _USER_ID


def test_presign_requires_authentication(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.pdf", "file_type": "pdf", "file_size": 100},
    )
    assert res.status_code == 401


# --- process -----------------------------------------------------------------

def _make_row(repo, status="pending", user_id=_USER_ID):
    file_id = str(uuid.uuid4())
    repo.insert_file(
        {
            "id": file_id,
            "user_id": user_id,
            "file_name": "a.pdf",
            "file_type": "pdf",
            "storage_path": f"{user_id}/{file_id}.pdf",
            "processing_status": status,
        }
    )
    return file_id


def test_process_marks_processing_and_returns_202(repo):
    file_id = _make_row(repo)
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 202
    assert repo.rows[file_id]["processing_status"] == "processing"


def test_process_on_another_users_file_is_404_not_403(repo):
    file_id = _make_row(repo, user_id=_OTHER_USER_ID)
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 404


def test_process_while_already_processing_is_409(repo):
    file_id = _make_row(repo, status="processing")
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 409


def test_process_retries_a_failed_file(repo):
    file_id = _make_row(repo, status="error")
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 202
    assert repo.rows[file_id]["processing_status"] == "processing"


def test_process_errors_when_the_object_is_missing_from_r2(repo, monkeypatch):
    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: False)
    file_id = _make_row(repo)
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 400
    assert repo.rows[file_id]["processing_status"] == "error"


# --- read --------------------------------------------------------------------

def test_get_file_returns_status_and_outline(repo):
    file_id = _make_row(repo, status="ready_for_review")
    repo.rows[file_id]["draft_outline"] = [
        {"title": "A", "content_md": "x", "order_index": 0}
    ]
    res = client.get(f"/api/files/{file_id}", headers=_headers())
    assert res.status_code == 200
    assert res.json()["processing_status"] == "ready_for_review"
    assert res.json()["draft_outline"][0]["title"] == "A"


def test_get_another_users_file_is_404(repo):
    file_id = _make_row(repo, user_id=_OTHER_USER_ID)
    res = client.get(f"/api/files/{file_id}", headers=_headers())
    assert res.status_code == 404


def test_list_files_only_returns_own_files(repo):
    mine = _make_row(repo)
    _make_row(repo, user_id=_OTHER_USER_ID)
    res = client.get("/api/files", headers=_headers())
    assert res.status_code == 200
    assert [f["id"] for f in res.json()] == [mine]
```

- [ ] **Step 2: Chạy test để thấy nó fail**

Run: `cd backend && python -m pytest tests/test_files_api.py -v`
Expected: FAIL — `ImportError: cannot import name 'files' from 'app.routers'`

- [ ] **Step 3: Viết `routers/files.py`**

```python
"""File upload lifecycle: presign -> (browser PUTs to R2) -> process -> poll."""

import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import db
from app.config import settings
from app.dependencies.auth import CurrentUser, get_current_user
from app.ingest import pipeline
from app.storage import r2

router = APIRouter(prefix="/api/files", tags=["files"])

FileType = Literal["md", "docx", "pptx", "pdf"]


class PresignRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_type: FileType
    file_size: int = Field(gt=0)


class PresignResponse(BaseModel):
    file_id: str
    upload_url: str
    storage_path: str


class _Repo:
    """Thin data layer. Isolated in a class so tests can swap it wholesale.

    Uses the service-role client, which bypasses RLS — every read here filters
    on user_id explicitly.
    """

    def insert_file(self, values: dict) -> None:
        db.admin().table("user_files").insert(values).execute()

    def get_file(self, file_id: str, user_id: str) -> dict | None:
        result = (
            db.admin()
            .table("user_files")
            .select("*")
            .eq("id", file_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def list_files(self, user_id: str) -> list[dict]:
        result = (
            db.admin()
            .table("user_files")
            .select("*")
            .eq("user_id", user_id)
            .order("uploaded_at", desc=True)
            .execute()
        )
        return result.data or []

    def set_status(self, file_id: str, status_value: str) -> None:
        db.admin().table("user_files").update(
            {"processing_status": status_value}
        ).eq("id", file_id).execute()


repo = _Repo()


@router.post("/presign", response_model=PresignResponse)
def presign(body: PresignRequest, user: CurrentUser = Depends(get_current_user)):
    if body.file_size > settings.MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File vượt quá giới hạn 20MB.",
        )

    file_id = str(uuid.uuid4())
    # user_id prefix: a leaked key still tells you nothing about other users.
    storage_path = f"{user.user_id}/{file_id}.{body.file_type}"

    repo.insert_file(
        {
            "id": file_id,
            "user_id": user.user_id,
            "file_name": body.file_name,
            "file_type": body.file_type,
            "storage_path": storage_path,
            "file_size": body.file_size,
            "processing_status": "pending",
        }
    )
    return PresignResponse(
        file_id=file_id,
        upload_url=r2.presign_put(storage_path, body.file_size),
        storage_path=storage_path,
    )


@router.post("/{file_id}/process", status_code=status.HTTP_202_ACCEPTED)
def process(
    file_id: str,
    background: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    row = repo.get_file(file_id, user.user_id)
    if row is None:
        # 404, never 403 — do not confirm that someone else's file exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file."
        )
    if row["processing_status"] == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="File đang được xử lý."
        )

    if not r2.object_exists(row["storage_path"]):
        repo.set_status(file_id, "error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chưa thấy file trên kho lưu trữ — hãy tải lên lại.",
        )

    repo.set_status(file_id, "processing")
    background.add_task(pipeline.process_file, file_id)
    return {"status": "processing"}


@router.get("/{file_id}")
def get_file(file_id: str, user: CurrentUser = Depends(get_current_user)):
    row = repo.get_file(file_id, user.user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file."
        )
    return row


@router.get("")
def list_files(user: CurrentUser = Depends(get_current_user)):
    return repo.list_files(user.user_id)
```

- [ ] **Step 4: Đăng ký router**

Sửa `backend/app/main.py`:

```python
from app.routers import files, health, me
```

và thêm sau `app.include_router(me.router)`:

```python
app.include_router(files.router)
```

- [ ] **Step 5: Chạy test cho tới khi xanh**

Run: `cd backend && python -m pytest tests/test_files_api.py -v`
Expected: 13 passed.

Nếu `test_presign_rejects_an_unknown_file_type` trả 400 thay vì 422 → `Literal` chưa được dùng cho `file_type`, sửa model.
Nếu `_finish`/`set_status` không phản ánh vào `_FakeRepo` → kiểm tra router có gọi qua biến module-level `repo` không (monkeypatch chỉ thay được biến module-level).

- [ ] **Step 6: Chạy toàn bộ test**

Run: `cd backend && python -m pytest -v`
Expected: tất cả xanh, output sạch.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/files.py backend/app/main.py backend/tests/test_files_api.py
git commit -m "feat(api): add file presign/process/read endpoints"
```

---

### Task 7: Verify thật end-to-end + cập nhật tài liệu

Pytest dùng R2 giả. Task này chứng minh code chạy với R2 và Supabase **thật** — spec mục 9 yêu cầu, không được bỏ.

**Files:**
- Modify: `check_list.md`
- Create: `backend/scripts/verify_upload.py` (script tạm, xóa sau khi verify)

**Interfaces:**
- Consumes: toàn bộ hệ thống từ Task 1–6

- [ ] **Step 1: Chuẩn bị file mẫu thật**

Cần 2 file trong `backend/scripts/samples/`:
- một `.docx` có **ít nhất 3 heading cấp 1**
- một `.pdf` có **ít nhất 3 chương / 15 trang**

Dùng tài liệu thật của user. Nếu chưa có, hỏi user — đừng tự sinh file giả rồi coi là đã verify.

- [ ] **Step 2: Khởi động backend thật**

```bash
cd backend && .venv/Scripts/Activate.ps1 && python -m uvicorn app.main:app --port 8000
```

Expected: `Application startup complete.` — không traceback.

- [ ] **Step 3: Lấy JWT thật**

Đăng nhập frontend (`npm run dev`, magic link), mở DevTools → Console:

```js
(await window.supabase?.auth.getSession())?.data.session.access_token
```

Nếu `window.supabase` không có, lấy từ Application → Local Storage → key `sb-*-auth-token` → trường `access_token`.

- [ ] **Step 4: Viết script verify**

Tạo `backend/scripts/verify_upload.py`:

```python
"""One-off end-to-end check against the real R2 bucket and Supabase project.

Usage: python scripts/verify_upload.py <jwt> <path-to-file> <file_type>
"""

import json
import sys
import time
from pathlib import Path

import httpx

API = "http://localhost:8000"


def main(token: str, path: str, file_type: str) -> None:
    data = Path(path).read_bytes()
    headers = {"Authorization": f"Bearer {token}"}

    presign = httpx.post(
        f"{API}/api/files/presign",
        json={
            "file_name": Path(path).name,
            "file_type": file_type,
            "file_size": len(data),
        },
        headers=headers,
    ).raise_for_status().json()
    print("presigned:", presign["storage_path"])

    put = httpx.put(
        presign["upload_url"],
        content=data,
        headers={"Content-Length": str(len(data))},
        timeout=120,
    )
    print("R2 PUT:", put.status_code)
    put.raise_for_status()

    httpx.post(
        f"{API}/api/files/{presign['file_id']}/process", headers=headers
    ).raise_for_status()

    for _ in range(60):
        row = httpx.get(
            f"{API}/api/files/{presign['file_id']}", headers=headers
        ).raise_for_status().json()
        if row["processing_status"] in ("ready_for_review", "error"):
            break
        time.sleep(2)

    print("status:", row["processing_status"])
    print("error:", row.get("error_message"))
    outline = row.get("draft_outline") or []
    print("chapters:", len(outline))
    for chapter in outline:
        print(f"  [{chapter['order_index']}] {chapter['title'][:70]}"
              f" ({len(chapter['content_md'])} chars)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
```

- [ ] **Step 5: Chạy verify với `.docx`**

```bash
cd backend && python scripts/verify_upload.py "<JWT>" scripts/samples/tai-lieu.docx docx
```

Expected:
- `R2 PUT: 200`
- `status: ready_for_review`
- `chapters:` bằng đúng số heading cấp 1 trong file
- mỗi chương có `< 8000 chars` và tiêu đề đọc được

**Đọc mắt thường danh sách chương in ra.** Nếu tên chương là rác hoặc chỉ có 1 chương trong khi file có nhiều → có bug, quay lại Task 3/4, đừng đánh dấu xong.

- [ ] **Step 6: Chạy verify với `.pdf`**

```bash
cd backend && python scripts/verify_upload.py "<JWT>" scripts/samples/giao-trinh.pdf pdf
```

Expected: `status: ready_for_review`, số chương khớp bookmark (hoặc `ceil(pages/10)` nếu PDF không có bookmark).

- [ ] **Step 7: Verify đường lỗi + retry**

```bash
# Đổi tên một file .txt thành .pdf rồi upload — PDF hỏng
cd backend && python scripts/verify_upload.py "<JWT>" scripts/samples/fake.pdf pdf
```

Expected: `status: error`, `error:` là câu tiếng Việt gợi ý cách xử lý, **không** phải traceback.

Rồi gọi lại process trên chính `file_id` đó → trả `202` (retry chạy được, không bị 409).

- [ ] **Step 8: Verify RLS per-user trên `lessons`**

Trong Supabase SQL Editor:

```sql
insert into lessons (user_id, slug, title, content_md)
values ('<USER_ID_THẬT>', 'test-rls', 'Test', 'x');
```

Rồi từ frontend đã đăng nhập bằng **user khác** (hoặc anon key), gọi `select` trên `lessons` → phải ra **0 dòng**. Xong thì `delete from lessons where slug = 'test-rls';`.

- [ ] **Step 9: Dọn dẹp**

```bash
rm -rf backend/scripts
```

Xóa các object test trên R2 qua Cloudflare Dashboard, và xóa các dòng `user_files` test trong Supabase.

- [ ] **Step 10: Cập nhật `check_list.md`**

Đánh dấu `[x]` cho cả 6 gạch đầu dòng ở mục `### #1a`, đổi tiêu đề mục thành `### #1a — ... — ✅ XONG (2026-07-19)`, và tick `[x]` cho dòng blocker R2 keys ở mục "Việc cần user".

- [ ] **Step 11: Commit**

```bash
git add check_list.md
git commit -m "docs: mark #1a upload/extract/chapters complete"
```

---

## Self-Review — đối chiếu với spec

| Yêu cầu spec | Task |
|---|---|
| §6 Migration 0006 (lessons + user_files) | Task 1 |
| §7 Env vars R2 + deps mới | Task 2 |
| §4 `POST /api/files/presign` (20MB, 15 phút, key có user prefix) | Task 6 |
| §4 `POST /api/files/{id}/process` (404/409/head_object/BackgroundTasks/202) | Task 6 |
| §4 `GET /api/files/{id}` + `GET /api/files` | Task 6 |
| §5.1 4 extractor, PDF không text layer → lỗi tiếng Việt | Task 4 |
| §5.2 Splitter: heading cấp cao nhất, mở đầu dài/ngắn, trần 8000, loại chương rỗng, title 200 ký tự, order_index | Task 3 |
| §3 Vòng đời trạng thái, không tự set `done` | Task 5 + 6 |
| §5 try/except toàn bộ → `error` + `error_message` | Task 5 |
| §9 Unit test splitter + extractor; API test mock R2 | Task 3, 4, 6 |
| §9 Verify thật `.docx` + `.pdf` trên R2 thật | Task 7 |
| §10 Định nghĩa hoàn thành | Task 1 (RLS), 3–6 (test), 7 (verify + docs) |

Không có mục nào của spec thiếu task.
