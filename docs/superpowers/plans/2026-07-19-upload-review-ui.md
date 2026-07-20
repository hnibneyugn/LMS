# #1b — UI upload + duyệt chương — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khép kín luồng ingest — user upload file từ trình duyệt, theo dõi xử lý, duyệt danh sách chương nháp (sửa tên / gộp / bỏ), xác nhận để sinh bài học trong bảng `lessons`.

**Architecture:** Backend thêm đúng một endpoint `POST /api/files/{id}/confirm` nhận **lệnh** (`{title, source_indexes[]}`) chứ không nhận nội dung — server đọc `draft_outline` từ DB rồi tự dựng `content_md`, nên nội dung bài học không bao giờ đi qua client. Song song, `docx.py` được thêm heuristic nhận diện heading đánh số để tài liệu Word tiếng Việt không heading style vẫn cắt ra chương dùng được. Frontend thêm hai trang React: `/files` (upload + danh sách + poll) và `/files/:id/review` (duyệt chương).

**Tech Stack:** FastAPI + Pydantic + supabase-py (backend) · React 19 + React Router 7 + Tailwind 4 + Shadcn (frontend) · pytest · Không thêm dependency mới ở cả hai phía.

## Global Constraints

- Spec nguồn: `docs/superpowers/specs/2026-07-19-upload-review-ui-design.md`. Mọi quyết định bám theo spec đó.
- Chuỗi hiển thị cho user = **tiếng Việt**. Code, tên biến, comment kỹ thuật, commit message = **tiếng Anh**.
- Mọi route riêng tư dùng `Depends(get_current_user)`. **Không endpoint nào nhận `user_id` từ client** — luôn lấy từ JWT.
- File của user khác → **404**, không bao giờ 403 (tránh lộ sự tồn tại).
- Backend chạy trong venv: `cd backend && .venv/Scripts/Activate.ps1` trước khi chạy `pytest`.
- `pytest` phải xanh **và output sạch** — không warning mới.
- `npm run build` từ `frontend/` phải sạch TypeScript.
- **Không thêm dependency mới.** Slugify viết tay bằng `unicodedata` (stdlib).
- Commit sau mỗi task hoàn thành (quy ước dự án).
- Mọi lỗi hiện cho user **ưu tiên `detail` của backend** thay vì tự chế câu mới.

---

## File Structure

**Backend — tạo mới:**
- `backend/app/ingest/extractors/_numbering.py` — nhận diện đoạn văn là heading đánh số. Thuần hàm, không phụ thuộc python-docx, test độc lập được.
- `backend/app/lessons/__init__.py` — package mới.
- `backend/app/lessons/slug.py` — `slugify()` + `unique_slug()`. Thuần hàm.
- `backend/tests/test_numbering.py`
- `backend/tests/test_slug.py`
- `backend/tests/test_confirm_api.py`

**Backend — sửa:**
- `backend/app/ingest/extractors/docx.py` — dùng `_numbering` khi style không phải heading.
- `backend/app/routers/files.py` — thêm `confirm`, thêm `response_model`, chặn `/process` trên `done`, thêm 2 method vào `_Repo`.
- `backend/tests/test_extractors.py` — test hồi quy docx.
- `backend/tests/test_files_api.py` — test `/process` trên `done` + payload whitelist.

**Frontend — tạo mới:**
- `frontend/src/lib/files.ts` — kiểu dữ liệu + hàm gọi API của luồng file. Tách khỏi component để test/đọc dễ.
- `frontend/src/components/UploadDropzone.tsx` — chọn file + validate + chạy 3 bước presign/PUT/process.
- `frontend/src/components/FileTable.tsx` — bảng danh sách + badge trạng thái + nút hành động.
- `frontend/src/pages/Files.tsx` — ghép dropzone + bảng + vòng poll.
- `frontend/src/pages/ReviewChapters.tsx` — trang duyệt chương.

**Frontend — sửa:**
- `frontend/src/lib/api.ts` — `apiFetch` ném lỗi mang theo `detail` + `status` (hiện đang vứt đi).
- `frontend/src/App.tsx` — thêm route.
- `frontend/src/pages/Home.tsx` — thêm link tới `/files`.

**Thứ tự:** Task 1–2 là hàm thuần (không phụ thuộc gì). Task 3–5 là backend API. Task 6 sửa nền tảng frontend. Task 7–9 là UI. Task 10 verify thật.

---

### Task 1: Heuristic heading đánh số cho `.docx`

**Files:**
- Create: `backend/app/ingest/extractors/_numbering.py`
- Create: `backend/tests/test_numbering.py`
- Modify: `backend/app/ingest/extractors/docx.py:26-38`
- Modify: `backend/tests/test_extractors.py` (thêm test hồi quy ở cuối)

**Interfaces:**
- Consumes: không có (task đầu tiên)
- Produces: `numbered_heading_level(text: str) -> int | None` trong `app.ingest.extractors._numbering` — trả 2/3/4 (cấp markdown `##`/`###`/`####`) nếu đoạn văn trông như heading đánh số, `None` nếu không.

**Bối cảnh:** #1a phát hiện tài liệu Word tiếng Việt thường không gán heading style (file mẫu: 110/114 đoạn là `Normal`), khiến 19k ký tự đầu bị cắt cứng thành 3 cục "Mở đầu (1)(2)(3)". Sửa ở extractor chứ không ở `splitter.py` — splitter chỉ ăn markdown, giữ nguyên ranh giới trách nhiệm từ #1a.

- [ ] **Step 1: Viết test thất bại cho `numbered_heading_level`**

Tạo `backend/tests/test_numbering.py`:

```python
import pytest

from app.ingest.extractors._numbering import numbered_heading_level


@pytest.mark.parametrize(
    "text",
    [
        "Chương 1 Tổng quan",
        "Chương 12: Kết luận",
        "Bài 3 Câu điều kiện",
        "Phần 2 — Ứng dụng",
        "Mục 4 Thực hành",
        "Chapter 5 Overview",
        "I. Mở đầu",
        "IV. Tổng kết",
    ],
)
def test_word_and_roman_patterns_are_level_two(text):
    assert numbered_heading_level(text) == 2


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1. Giới thiệu", 2),
        ("2 Giới thiệu", 2),
        ("1.1 Bối cảnh", 3),
        ("1.1. Bối cảnh", 3),
        ("1.1.1 Chi tiết", 4),
        ("1.1.1.1 Sâu hơn", 4),  # clamped: markdown level never exceeds 4
    ],
)
def test_decimal_depth_maps_to_heading_level(text, expected):
    assert numbered_heading_level(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Đoạn văn bình thường không đánh số.",
        "1. Điều thứ nhất là phải giữ cho câu này kết thúc bằng dấu chấm.",
        "2. Tiếp theo,",
        "3. Sau đó;",
        "4. Cuối cùng:",
        "",
        "   ",
        "Chương",  # keyword with no number
        "Chapter",
        "1234",  # a bare number is not a heading
    ],
)
def test_non_headings_return_none(text):
    assert numbered_heading_level(text) is None


def test_long_line_is_not_a_heading():
    assert numbered_heading_level("Chương 1 " + "x" * 200) is None


def test_leading_and_trailing_space_is_tolerated():
    assert numbered_heading_level("  Chương 1 Tổng quan  ") == 2
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && python -m pytest tests/test_numbering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingest.extractors._numbering'`

- [ ] **Step 3: Viết `_numbering.py`**

Tạo `backend/app/ingest/extractors/_numbering.py`:

```python
"""Detect numbered headings in paragraphs that carry no heading style.

Vietnamese Word documents routinely leave every paragraph as `Normal` and
express structure through numbering alone ("Chương 1", "1.1", "I."). Without
this, such a document reaches the splitter with no heading at all and gets
hard-cut into a few oversized chunks -- and #1b's review UI deliberately has
no "split chapter" action, so an oversized chapter cannot be fixed by hand.
Cutting too finely is recoverable (the user merges); cutting too coarsely is
not. That asymmetry is why this leans towards detecting.
"""

import re

# Long enough for a real heading, short enough to exclude prose. A numbered
# list item ("1. Điều thứ nhất là...") is the main false positive this and
# the trailing-punctuation rule below are aimed at.
_MAX_HEADING_CHARS = 120
_SENTENCE_ENDINGS = (".", ",", ";", ":")

_KEYWORD = re.compile(
    r"^(chương|bài|phần|mục|chapter)\s+\d+\b",
    re.IGNORECASE,
)
_ROMAN = re.compile(r"^[IVXLC]+\.\s+\S", re.IGNORECASE)
# Captures the dotted number so its depth can set the heading level.
_DECIMAL = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")


def numbered_heading_level(text: str) -> int | None:
    """Markdown heading level (2..4) if `text` looks like a numbered heading.

    Returns None for anything else. Level 2 is the floor because real Word
    Heading styles already occupy 1..3 via docx._heading_level -- a heuristic
    hit must never outrank a genuine top-level heading and change which level
    the splitter picks as its chapter boundary.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return None
    # A heading does not end mid-sentence. This is what keeps ordinary
    # numbered list items out.
    if stripped.endswith(_SENTENCE_ENDINGS):
        return None

    if _KEYWORD.match(stripped) or _ROMAN.match(stripped):
        return 2

    decimal = _DECIMAL.match(stripped)
    if decimal:
        depth = decimal.group(1).count(".") + 1
        return min(depth + 1, 4)
    return None
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/test_numbering.py -v`
Expected: PASS — toàn bộ (khoảng 26 test qua parametrize)

- [ ] **Step 5: Viết test hồi quy cho `docx.py`**

Thêm vào cuối `backend/tests/test_extractors.py`:

```python
def _docx_bytes(paragraphs: list[tuple[str, str]]) -> bytes:
    """Build a .docx in memory. Each tuple is (style_name, text)."""
    import io

    from docx import Document

    document = Document()
    for style_name, text in paragraphs:
        document.add_paragraph(text, style=style_name)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_docx_normal_paragraphs_with_numbering_become_headings():
    from app.ingest.extractors import docx as docx_extractor

    data = _docx_bytes(
        [
            ("Normal", "Chương 1 Tổng quan"),
            ("Normal", "Nội dung chương một."),
            ("Normal", "Chương 2 Chi tiết"),
            ("Normal", "Nội dung chương hai."),
            ("Normal", "2.1 Mục nhỏ"),
            ("Normal", "Nội dung mục nhỏ."),
        ]
    )
    md = docx_extractor.extract(data)
    assert "## Chương 1 Tổng quan" in md
    assert "## Chương 2 Chi tiết" in md
    assert "### 2.1 Mục nhỏ" in md
    assert "Nội dung chương một." in md


def test_docx_numbered_list_prose_is_not_turned_into_headings():
    from app.ingest.extractors import docx as docx_extractor

    data = _docx_bytes(
        [
            ("Normal", "1. Điều thứ nhất là phải giữ nguyên câu này."),
            ("Normal", "2. Điều thứ hai cũng vậy, không được thành heading."),
        ]
    )
    md = docx_extractor.extract(data)
    assert "#" not in md.replace("\\#", "")


def test_docx_real_heading_styles_still_win():
    """Regression: documents that DO carry heading styles must be unchanged."""
    from app.ingest.extractors import docx as docx_extractor

    data = _docx_bytes(
        [
            ("Heading 1", "Phần mở đầu"),
            ("Normal", "Nội dung."),
            ("Heading 2", "Chi tiết"),
            ("Normal", "Thêm nội dung."),
        ]
    )
    md = docx_extractor.extract(data)
    assert "# Phần mở đầu" in md
    assert "## Chi tiết" in md
```

- [ ] **Step 6: Chạy test hồi quy, xác nhận 2 test đầu thất bại**

Run: `cd backend && python -m pytest tests/test_extractors.py -k docx -v`
Expected: `test_docx_normal_paragraphs_with_numbering_become_headings` FAIL (chưa có heuristic nên `## Chương 1` không xuất hiện); `test_docx_real_heading_styles_still_win` và `test_docx_numbered_list_prose_is_not_turned_into_headings` PASS sẵn.

- [ ] **Step 7: Nối heuristic vào `docx.py`**

Sửa `backend/app/ingest/extractors/docx.py`. Thêm import ở đầu file:

```python
from app.ingest.extractors._numbering import numbered_heading_level
```

Thay thân vòng lặp trong `extract()` (dòng 27-37) bằng:

```python
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = (paragraph.style.name or "").lower()
        is_list = "list" in style_name
        level = _heading_level(paragraph.style)
        if level is None and not is_list:
            # No real heading style: fall back to numbering, which is how
            # most Vietnamese Word documents express structure.
            level = numbered_heading_level(text)
        if level is not None:
            parts.append(f"{'#' * level} {text}")
        elif is_list:
            parts.append(f"- {escape_accidental_headings(text)}")
        else:
            parts.append(escape_accidental_headings(text))
```

Lưu ý: list item **không** đi qua heuristic — một danh sách đánh số của Word là list thật, không phải heading.

- [ ] **Step 8: Chạy toàn bộ test extractor + splitter**

Run: `cd backend && python -m pytest tests/test_extractors.py tests/test_numbering.py tests/test_splitter.py -v`
Expected: PASS toàn bộ, không warning.

- [ ] **Step 9: Commit**

```bash
git add backend/app/ingest/extractors/_numbering.py backend/app/ingest/extractors/docx.py backend/tests/test_numbering.py backend/tests/test_extractors.py
git commit -m "feat(ingest): detect numbered headings in unstyled docx paragraphs"
```

---

### Task 2: Sinh slug cho bài học

**Files:**
- Create: `backend/app/lessons/__init__.py`
- Create: `backend/app/lessons/slug.py`
- Create: `backend/tests/test_slug.py`

**Interfaces:**
- Consumes: không có
- Produces:
  - `slugify(text: str) -> str` — bỏ dấu tiếng Việt, hạ chữ thường, ký tự lạ thành `-`, cắt 80 ký tự. Trả `""` nếu không còn gì.
  - `unique_slug(base: str, taken: set[str]) -> str` — trả `base` nếu chưa dùng, không thì `base-2`, `base-3`…

**Bối cảnh:** Unique constraint là `(user_id, slug)` (migration `0006`). Hai file **cùng tên** của cùng một user sẽ đụng nhau, nên phải đọc slug đã có rồi thêm hậu tố.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/test_slug.py`:

```python
import pytest

from app.lessons.slug import slugify, unique_slug


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bài giảng số 1", "bai-giang-so-1"),
        ("Tiếng Việt có dấu", "tieng-viet-co-dau"),
        ("Đường lối Đảng", "duong-loi-dang"),
        ("  khoảng  trắng  thừa  ", "khoang-trang-thua"),
        ("Ký!tự@lạ#nhiều", "ky-tu-la-nhieu"),
        ("UPPER Case", "upper-case"),
        ("---đầu-cuối---", "dau-cuoi"),
    ],
)
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_slugify_returns_empty_when_nothing_survives():
    assert slugify("!!!") == ""
    assert slugify("") == ""


def test_slugify_truncates_to_80_chars():
    result = slugify("a" * 200)
    assert len(result) == 80


def test_slugify_does_not_end_with_dash_after_truncation():
    # 79 chars, then a separator, then more -- naive truncation would leave a
    # trailing dash.
    result = slugify("a" * 79 + " bcd")
    assert not result.endswith("-")


def test_unique_slug_returns_base_when_free():
    assert unique_slug("bai-1", set()) == "bai-1"


def test_unique_slug_appends_counter_when_taken():
    assert unique_slug("bai-1", {"bai-1"}) == "bai-1-2"
    assert unique_slug("bai-1", {"bai-1", "bai-1-2"}) == "bai-1-3"
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && python -m pytest tests/test_slug.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.lessons'`

- [ ] **Step 3: Tạo package + implement**

Tạo `backend/app/lessons/__init__.py` (file rỗng).

Tạo `backend/app/lessons/slug.py`:

```python
"""Slug generation for lessons.

Hand-rolled rather than pulling in python-slugify: the project's first design
principle is to stay simple and dependency-light, and the only hard
requirement here is stripping Vietnamese diacritics, which `unicodedata`
already does.
"""

import re
import unicodedata

_MAX_SLUG_CHARS = 80
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase ASCII slug. Returns "" if nothing usable survives."""
    # NFD splits "ế" into "e" + combining accent; the Mn filter then drops the
    # accent. "đ"/"Đ" is NOT a base letter plus accent, so it survives NFD
    # untouched and has to be mapped by hand.
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    ascii_text = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    ).lower()
    slug = _NON_SLUG.sub("-", ascii_text).strip("-")
    # Strip again after truncation so a cut that lands on a separator does not
    # leave a trailing dash.
    return slug[:_MAX_SLUG_CHARS].strip("-")


def unique_slug(base: str, taken: set[str]) -> str:
    """`base`, or `base-2`, `base-3`... until one is free in `taken`."""
    if base not in taken:
        return base
    counter = 2
    while f"{base}-{counter}" in taken:
        counter += 1
    return f"{base}-{counter}"
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/test_slug.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/lessons/
git add backend/tests/test_slug.py
git commit -m "feat(lessons): add diacritic-stripping slug generation"
```

---

### Task 3: `POST /api/files/{file_id}/confirm`

**Files:**
- Modify: `backend/app/routers/files.py` (thêm model, thêm 2 method vào `_Repo`, thêm route)
- Create: `backend/tests/test_confirm_api.py`

**Interfaces:**
- Consumes: `slugify`, `unique_slug` từ `app.lessons.slug` (Task 2)
- Produces:
  - Route `POST /api/files/{file_id}/confirm`, request `{ chapters: [{ title: str, source_indexes: [int] }] }`, response `{ lesson_count: int }`
  - `_Repo.insert_lessons(rows: list[dict]) -> None`
  - `_Repo.list_lesson_slugs(user_id: str) -> list[str]`

**Bối cảnh — thứ tự ghi rất quan trọng:** insert `lessons` **xong mới** set `done`. Nếu insert lỗi thì file vẫn `ready_for_review` và user duyệt lại được, không để lại `lessons` mồ côi.

- [ ] **Step 1: Viết test thất bại — đường hạnh phúc + gộp + bỏ**

Tạo `backend/tests/test_confirm_api.py`:

```python
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


def _outline(count: int) -> list[dict]:
    return [
        {"title": f"Chương {i}", "content_md": f"Nội dung {i}", "order_index": i}
        for i in range(count)
    ]


class _FakeRepo:
    """Stands in for every db call `confirm` makes."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.lessons: list[dict] = []
        self.insert_should_fail = False

    def get_file(self, file_id, user_id):
        row = self.rows.get(file_id)
        if row is None or row["user_id"] != user_id:
            return None
        return row

    def set_status(self, file_id, user_id, status, error_message=None):
        row = self.rows.get(file_id)
        if row is None or row["user_id"] != user_id:
            return
        row["processing_status"] = status
        if error_message is not None:
            row["error_message"] = error_message

    def insert_lessons(self, rows):
        if self.insert_should_fail:
            raise RuntimeError("db down")
        self.lessons.extend(rows)

    def list_lesson_slugs(self, user_id):
        return [
            lesson["slug"] for lesson in self.lessons if lesson["user_id"] == user_id
        ]


@pytest.fixture
def repo(monkeypatch):
    fake = _FakeRepo()
    monkeypatch.setattr(files_router, "repo", fake)
    return fake


def _ready_file(repo, file_id="f1", user_id=_USER_ID, chapters=3, name="Giáo trình.docx"):
    repo.rows[file_id] = {
        "id": file_id,
        "user_id": user_id,
        "file_name": name,
        "file_type": "docx",
        "processing_status": "ready_for_review",
        "draft_outline": _outline(chapters),
    }
    return file_id


def test_confirm_writes_one_lesson_per_chapter(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={
            "chapters": [
                {"title": "Bài một", "source_indexes": [0]},
                {"title": "Bài hai", "source_indexes": [1]},
                {"title": "Bài ba", "source_indexes": [2]},
            ]
        },
        headers=_headers(),
    )
    assert res.status_code == 200
    assert res.json() == {"lesson_count": 3}
    assert [lesson["title"] for lesson in repo.lessons] == ["Bài một", "Bài hai", "Bài ba"]
    assert [lesson["order_index"] for lesson in repo.lessons] == [0, 1, 2]
    assert all(lesson["user_id"] == _USER_ID for lesson in repo.lessons)
    assert all(lesson["source_file_id"] == file_id for lesson in repo.lessons)
    assert repo.rows[file_id]["processing_status"] == "done"


def test_confirm_merges_adjacent_chapters(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={
            "chapters": [
                {"title": "Gộp", "source_indexes": [0, 1]},
                {"title": "Riêng", "source_indexes": [2]},
            ]
        },
        headers=_headers(),
    )
    assert res.status_code == 200
    assert res.json() == {"lesson_count": 2}
    assert repo.lessons[0]["content_md"] == "Nội dung 0\n\nNội dung 1"
    assert repo.lessons[1]["content_md"] == "Nội dung 2"


def test_confirm_drops_omitted_chapters(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "Chỉ giữ cái giữa", "source_indexes": [1]}]},
        headers=_headers(),
    )
    assert res.status_code == 200
    assert len(repo.lessons) == 1
    assert repo.lessons[0]["content_md"] == "Nội dung 1"


def test_confirm_trims_title(repo):
    file_id = _ready_file(repo)
    client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "  Có khoảng trắng  ", "source_indexes": [0]}]},
        headers=_headers(),
    )
    assert repo.lessons[0]["title"] == "Có khoảng trắng"
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && python -m pytest tests/test_confirm_api.py -v`
Expected: FAIL — mọi test trả 404 vì route chưa tồn tại.

- [ ] **Step 3: Thêm 2 method vào `_Repo`**

Trong `backend/app/routers/files.py`, thêm vào cuối class `_Repo` (sau `claim_for_processing`):

```python
    def insert_lessons(self, rows: list[dict]) -> None:
        """Insert every lesson of a confirmed file in one call.

        One batched insert rather than a loop: supabase-py has no transaction
        handle here, so a loop that fails halfway would leave a partially
        confirmed file behind. A single insert either lands whole or not at all.
        """
        db.admin().table("lessons").insert(rows).execute()

    def list_lesson_slugs(self, user_id: str) -> list[str]:
        result = (
            db.admin().table("lessons").select("slug").eq("user_id", user_id).execute()
        )
        return [row["slug"] for row in (result.data or [])]
```

- [ ] **Step 4: Thêm model + hằng số**

Trong `backend/app/routers/files.py`, thêm import ở đầu file:

```python
from app.lessons.slug import slugify, unique_slug
```

Thêm sau `PresignResponse`:

```python
class ConfirmChapter(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_indexes: list[int] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _trim_title(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Tiêu đề chương không được để trống.")
        return trimmed


class ConfirmRequest(BaseModel):
    chapters: list[ConfirmChapter] = Field(min_length=1)


class ConfirmResponse(BaseModel):
    lesson_count: int


# Every status other than ready_for_review is a 409 with its own explanation.
_CONFIRM_BLOCKED = {
    "pending": "File chưa xử lý xong.",
    "processing": "File chưa xử lý xong.",
    "error": "File xử lý lỗi — hãy xử lý lại trước khi duyệt.",
    "done": "File đã được duyệt.",
}
```

Sửa dòng import pydantic thành:

```python
from pydantic import BaseModel, Field, field_validator
```

- [ ] **Step 5: Thêm hàm validate + dựng row**

Thêm vào `backend/app/routers/files.py`, trước định nghĩa `router` các endpoint (sau `repo = _Repo()`):

```python
def _validate_source_indexes(
    chapters: list[ConfirmChapter], outline_length: int
) -> None:
    """Raise 400 if the requested chapter layout violates data integrity.

    Two things are enforced: every index is in range and used by at most one
    chapter (the `seen` set -- a source chapter cannot end up duplicated
    across two lessons), and within a chapter the indexes are strictly
    ascending (content is concatenated in index order in
    `_build_lesson_rows`, so a reversed or unordered list would silently
    scramble a lesson's text).

    Indexes need NOT be contiguous within a chapter: a user who drops a
    chapter in the middle of what should be one lesson must still be able to
    merge the two chapters flanking the gap, so e.g. `[0, 2]` is valid.
    """
    seen: set[int] = set()
    for chapter in chapters:
        indexes = chapter.source_indexes
        for index in indexes:
            if not 0 <= index < outline_length:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Danh sách chương không hợp lệ.",
                )
            if index in seen:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Một chương gốc không thể nằm trong hai bài học.",
                )
            seen.add(index)
        if any(indexes[i] >= indexes[i + 1] for i in range(len(indexes) - 1)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Thứ tự chương trong một bài học phải tăng dần.",
            )


def _build_lesson_rows(
    chapters: list[ConfirmChapter],
    outline: list[dict],
    file_name: str,
    file_id: str,
    user_id: str,
    taken_slugs: set[str],
) -> list[dict]:
    base = slugify(file_name.rsplit(".", 1)[0])
    used = set(taken_slugs)
    rows: list[dict] = []
    for order, chapter in enumerate(chapters):
        candidate = f"{base}-{order}" if base else f"bai-{order}"
        slug = unique_slug(candidate, used)
        used.add(slug)
        rows.append(
            {
                "user_id": user_id,
                "source_file_id": file_id,
                "title": chapter.title,
                "slug": slug,
                "content_md": "\n\n".join(
                    outline[index]["content_md"] for index in chapter.source_indexes
                ),
                "order_index": order,
            }
        )
    return rows
```

- [ ] **Step 6: Thêm route `confirm`**

Thêm vào cuối `backend/app/routers/files.py`:

```python
@router.post("/{file_id}/confirm", response_model=ConfirmResponse)
def confirm(
    file_id: str,
    body: ConfirmRequest,
    user: CurrentUser = Depends(get_current_user),
):
    row = repo.get_file(file_id, user.user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file."
        )

    current_status = row["processing_status"]
    if current_status != "ready_for_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CONFIRM_BLOCKED.get(current_status, "File chưa xử lý xong."),
        )

    outline = row.get("draft_outline") or []
    if not outline:
        # ready_for_review with nothing to review means the row is
        # inconsistent -- refuse rather than write zero lessons and mark done.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="File chưa xử lý xong."
        )

    _validate_source_indexes(body.chapters, len(outline))

    rows = _build_lesson_rows(
        body.chapters,
        outline,
        row["file_name"],
        file_id,
        user.user_id,
        set(repo.list_lesson_slugs(user.user_id)),
    )

    # Insert first, mark done second. A failure here leaves the file at
    # ready_for_review so the user can simply confirm again -- the reverse
    # order would strand a `done` file with no lessons.
    repo.insert_lessons(rows)
    repo.set_status(file_id, user.user_id, "done")
    return ConfirmResponse(lesson_count=len(rows))
```

- [ ] **Step 7: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/test_confirm_api.py -v`
Expected: PASS cả 4 test.

- [ ] **Step 8: Viết test cho các ca lỗi**

Thêm vào cuối `backend/tests/test_confirm_api.py`:

```python
@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"chapters": []}, "empty chapters"),
        ({"chapters": [{"title": "", "source_indexes": [0]}]}, "empty title"),
        ({"chapters": [{"title": "   ", "source_indexes": [0]}]}, "blank title"),
        ({"chapters": [{"title": "x" * 201, "source_indexes": [0]}]}, "title too long"),
        ({"chapters": [{"title": "ok", "source_indexes": []}]}, "empty indexes"),
    ],
)
def test_confirm_rejects_malformed_payload(repo, payload, reason):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm", json=payload, headers=_headers()
    )
    assert res.status_code == 422, reason
    assert repo.rows[file_id]["processing_status"] == "ready_for_review"


def test_confirm_rejects_out_of_range_index(repo):
    file_id = _ready_file(repo, chapters=2)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [5]}]},
        headers=_headers(),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Danh sách chương không hợp lệ."
    assert repo.lessons == []


def test_confirm_rejects_negative_index(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [-1]}]},
        headers=_headers(),
    )
    assert res.status_code == 400


def test_confirm_rejects_index_used_twice(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={
            "chapters": [
                {"title": "a", "source_indexes": [0]},
                {"title": "b", "source_indexes": [0]},
            ]
        },
        headers=_headers(),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Một chương gốc không thể nằm trong hai bài học."
    assert repo.lessons == []


def test_confirm_allows_merge_across_a_dropped_chapter(repo):
    """Non-adjacent indexes are valid: a user who drops the chapter in the
    middle must still be able to merge the two chapters flanking the gap."""
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "a", "source_indexes": [0, 2]}]},
        headers=_headers(),
    )
    assert res.status_code == 200
    assert repo.lessons[0]["content_md"] == "Nội dung 0\n\nNội dung 2"


def test_confirm_rejects_descending_merge(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "a", "source_indexes": [1, 0]}]},
        headers=_headers(),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Thứ tự chương trong một bài học phải tăng dần."


@pytest.mark.parametrize(
    ("file_status", "detail"),
    [
        ("pending", "File chưa xử lý xong."),
        ("processing", "File chưa xử lý xong."),
        ("error", "File xử lý lỗi — hãy xử lý lại trước khi duyệt."),
        ("done", "File đã được duyệt."),
    ],
)
def test_confirm_rejects_wrong_status(repo, file_status, detail):
    file_id = _ready_file(repo)
    repo.rows[file_id]["processing_status"] = file_status
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
        headers=_headers(),
    )
    assert res.status_code == 409
    assert res.json()["detail"] == detail
    assert repo.lessons == []


def test_confirm_on_another_users_file_is_404(repo):
    file_id = _ready_file(repo, user_id=_OTHER_USER_ID)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
        headers=_headers(),
    )
    assert res.status_code == 404
    assert repo.lessons == []


def test_confirm_without_token_is_401(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
    )
    assert res.status_code == 401


def test_confirm_leaves_file_reviewable_when_insert_fails(repo):
    file_id = _ready_file(repo)
    repo.insert_should_fail = True
    with pytest.raises(RuntimeError):
        client.post(
            f"/api/files/{file_id}/confirm",
            json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
            headers=_headers(),
        )
    assert repo.rows[file_id]["processing_status"] == "ready_for_review"
    assert repo.lessons == []


def test_confirm_avoids_slug_collision_with_existing_lessons(repo):
    repo.lessons.append(
        {"user_id": _USER_ID, "slug": "giao-trinh-0", "title": "cũ"}
    )
    file_id = _ready_file(repo, chapters=1, name="Giáo trình.docx")
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "mới", "source_indexes": [0]}]},
        headers=_headers(),
    )
    assert res.status_code == 200
    assert repo.lessons[-1]["slug"] == "giao-trinh-0-2"


def test_confirm_falls_back_when_file_name_has_no_usable_characters(repo):
    file_id = _ready_file(repo, chapters=1, name="!!!.docx")
    client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
        headers=_headers(),
    )
    assert repo.lessons[0]["slug"] == "bai-0"
```

Lưu ý: payload sai kiểu bị Pydantic chặn → **422**, còn index sai ngữ nghĩa do `_validate_source_indexes` chặn → **400**. Hai loại khác nhau, test phản ánh đúng thực tế thay vì ép cả hai về 400.

- [ ] **Step 9: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/test_confirm_api.py -v`
Expected: PASS toàn bộ (~20 test).

- [ ] **Step 10: Chạy toàn bộ suite**

Run: `cd backend && python -m pytest`
Expected: PASS toàn bộ, output sạch.

- [ ] **Step 11: Commit**

```bash
git add backend/app/routers/files.py backend/tests/test_confirm_api.py
git commit -m "feat(files): add confirm endpoint writing lessons from draft outline"
```

---

### Task 4: Chặn `/process` trên file `done`

**Files:**
- Modify: `backend/app/routers/files.py` (route `process`, sau khối kiểm tra `processing`)
- Modify: `backend/tests/test_files_api.py`

**Interfaces:**
- Consumes: route `process` hiện có
- Produces: không có gì cho task sau

**Bối cảnh:** Nợ kỹ thuật từ #1a — `/process` trên file `ready_for_review`/`done` đang ghi đè `draft_outline` không hỏi gì. Spec #1b chốt: `done` → 409; `ready_for_review` **vẫn cho chạy lại** (user muốn cắt lại trước khi duyệt là hợp lý).

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_files_api.py`, ngay sau các test `process` hiện có (tìm test có `409` trong tên để đặt cạnh):

```python
def test_process_on_confirmed_file_is_409(repo, fake_r2):
    file_id = "f-done"
    repo.rows[file_id] = {
        "id": file_id,
        "user_id": _USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "storage_path": f"{_USER_ID}/{file_id}.docx",
        "processing_status": "done",
    }
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 409
    assert res.json()["detail"] == "File đã được duyệt."
    assert repo.rows[file_id]["processing_status"] == "done"


def test_process_on_ready_for_review_still_reruns(repo, fake_r2):
    file_id = "f-ready"
    repo.rows[file_id] = {
        "id": file_id,
        "user_id": _USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "storage_path": f"{_USER_ID}/{file_id}.docx",
        "processing_status": "ready_for_review",
    }
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 202
```

Tên fixture `repo` và `fake_r2` phải khớp fixture có sẵn trong file — nếu tên khác, dùng đúng tên đang có thay vì thêm fixture mới.

- [ ] **Step 2: Chạy test, xác nhận test đầu thất bại**

Run: `cd backend && python -m pytest tests/test_files_api.py -k "confirmed_file or still_reruns" -v`
Expected: `test_process_on_confirmed_file_is_409` FAIL (nhận 202); `test_process_on_ready_for_review_still_reruns` PASS.

- [ ] **Step 3: Thêm kiểm tra vào route `process`**

Trong `backend/app/routers/files.py`, ngay sau khối `if row["processing_status"] == "processing":` (kết thúc ở dòng raise 409 hiện có), thêm:

```python
    if row["processing_status"] == "done":
        # Reprocessing would overwrite draft_outline while `lessons` already
        # point at this file. Confirmed is final -- see spec #1b decision B3.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="File đã được duyệt."
        )
```

- [ ] **Step 4: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/test_files_api.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/files.py backend/tests/test_files_api.py
git commit -m "fix(files): reject reprocessing a confirmed file"
```

---

### Task 5: Whitelist payload cho `GET /api/files*`

**Files:**
- Modify: `backend/app/routers/files.py` (thêm `FileOut`/`FileDetailOut`, gắn `response_model`)
- Modify: `backend/tests/test_files_api.py`

**Interfaces:**
- Consumes: `_Repo.get_file`, `_Repo.list_files` hiện có
- Produces: hình dạng JSON mà frontend Task 6–9 dựa vào:
  - `FileOut`: `id, file_name, file_type, file_size, processing_status, error_message, uploaded_at, chapter_count`
  - `FileDetailOut`: `FileOut` + `draft_outline: list[{title, content_md, order_index}] | null`

**Bối cảnh:** Nợ kỹ thuật từ #1a — hai endpoint đang trả `select("*")`, lộ `storage_path` và `user_id`. `chapter_count` để `/files` hiện "N chương" mà không phải tải cả `draft_outline` cho từng dòng.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/test_files_api.py`:

```python
def test_list_files_hides_storage_path_and_user_id(repo):
    repo.rows["f-list"] = {
        "id": "f-list",
        "user_id": _USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "file_size": 123,
        "storage_path": f"{_USER_ID}/f-list.docx",
        "processing_status": "ready_for_review",
        "draft_outline": [
            {"title": "a", "content_md": "aa", "order_index": 0},
            {"title": "b", "content_md": "bb", "order_index": 1},
        ],
    }
    res = client.get("/api/files", headers=_headers())
    assert res.status_code == 200
    row = res.json()[0]
    assert "storage_path" not in row
    assert "user_id" not in row
    assert "draft_outline" not in row
    assert row["chapter_count"] == 2


def test_list_files_reports_null_chapter_count_before_processing(repo):
    repo.rows["f-pending"] = {
        "id": "f-pending",
        "user_id": _USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "file_size": 1,
        "storage_path": f"{_USER_ID}/f-pending.docx",
        "processing_status": "pending",
    }
    res = client.get("/api/files", headers=_headers())
    assert res.json()[0]["chapter_count"] is None


def test_get_file_includes_draft_outline_but_not_storage_path(repo):
    repo.rows["f-one"] = {
        "id": "f-one",
        "user_id": _USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "file_size": 5,
        "storage_path": f"{_USER_ID}/f-one.docx",
        "processing_status": "ready_for_review",
        "draft_outline": [{"title": "a", "content_md": "aa", "order_index": 0}],
    }
    res = client.get("/api/files/f-one", headers=_headers())
    assert res.status_code == 200
    body = res.json()
    assert "storage_path" not in body
    assert "user_id" not in body
    assert body["draft_outline"] == [
        {"title": "a", "content_md": "aa", "order_index": 0}
    ]
    assert body["chapter_count"] == 1
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `cd backend && python -m pytest tests/test_files_api.py -k "hides_storage or chapter_count or includes_draft" -v`
Expected: FAIL — `storage_path` vẫn có trong response, `chapter_count` KeyError.

- [ ] **Step 3: Thêm model**

Trong `backend/app/routers/files.py`, thêm sau `ConfirmResponse`:

```python
class DraftChapterOut(BaseModel):
    title: str
    content_md: str
    order_index: int


class FileOut(BaseModel):
    """Everything the file list needs -- and nothing else.

    `storage_path` and `user_id` are deliberately absent: the client never
    addresses R2 directly (it only ever uses a presigned URL) and never needs
    to name a user, so shipping either would be leaking internals for free.
    """

    id: str
    file_name: str
    file_type: str
    file_size: int | None = None
    processing_status: str
    error_message: str | None = None
    uploaded_at: str | None = None
    chapter_count: int | None = None


class FileDetailOut(FileOut):
    draft_outline: list[DraftChapterOut] | None = None
```

- [ ] **Step 4: Thêm hàm chuyển đổi + gắn `response_model`**

Thêm hàm sau `_build_lesson_rows`:

```python
def _to_file_out(row: dict) -> dict:
    """Row -> FileOut-shaped dict, deriving chapter_count from the outline."""
    outline = row.get("draft_outline")
    return {**row, "chapter_count": len(outline) if outline is not None else None}
```

Sửa hai endpoint cuối file:

```python
@router.get("/{file_id}", response_model=FileDetailOut)
def get_file(file_id: str, user: CurrentUser = Depends(get_current_user)):
    row = repo.get_file(file_id, user.user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file."
        )
    return _to_file_out(row)


@router.get("", response_model=list[FileOut])
def list_files(user: CurrentUser = Depends(get_current_user)):
    return [_to_file_out(row) for row in repo.list_files(user.user_id)]
```

`response_model` của FastAPI tự lọc bỏ field thừa, nên `{**row, ...}` mang theo `storage_path` cũng không lọt ra ngoài.

- [ ] **Step 5: Chạy test, xác nhận xanh**

Run: `cd backend && python -m pytest tests/test_files_api.py -v`
Expected: PASS toàn bộ. Nếu test cũ nào assert vào `storage_path` trong response thì sửa test đó — hành vi mới là đúng.

- [ ] **Step 6: Chạy toàn bộ suite**

Run: `cd backend && python -m pytest`
Expected: PASS toàn bộ, output sạch.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/files.py backend/tests/test_files_api.py
git commit -m "fix(files): whitelist list/detail payloads with response models"
```

---

### Task 6: `apiFetch` giữ lại `detail` của backend

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Consumes: không có
- Produces: `ApiError` (class, có `status: number`) và `apiFetch(path, options)` — ném `ApiError` với `message` là `detail` từ backend khi có.

**Bối cảnh:** `apiFetch` hiện ném `new Error(\`API ${path} lỗi ${res.status}\`)` — vứt hết `detail`. Spec §7 yêu cầu mọi lỗi ưu tiên `detail` của backend, nên phải sửa trước khi viết UI.

- [ ] **Step 1: Viết lại `api.ts`**

Thay toàn bộ `frontend/src/lib/api.ts`:

```ts
import { supabase } from "./supabase"

const BASE = import.meta.env.VITE_API_BASE_URL as string

/** An HTTP error from the backend, carrying its status and Vietnamese detail. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

/** Call the FastAPI backend, attaching the Bearer token from the Supabase session. */
export async function apiFetch(path: string, options: RequestInit = {}) {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error("Chưa đăng nhập")

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...(options.headers ?? {}), Authorization: `Bearer ${token}` },
  })

  if (!res.ok) {
    // The backend writes user-facing Vietnamese into `detail`; surfacing it
    // beats any message invented here. Falls back only when the body is not
    // the expected shape (a proxy error page, a network-level failure).
    let detail = `Yêu cầu thất bại (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === "string") detail = body.detail
    } catch {
      // Body was not JSON -- keep the fallback.
    }
    throw new ApiError(detail, res.status)
  }
  return res.json()
}
```

- [ ] **Step 2: Kiểm tra build**

Run: `cd frontend && npm run build`
Expected: build thành công, không lỗi TypeScript. `Home.tsx` dùng `(e as Error).message` vẫn chạy vì `ApiError` kế thừa `Error`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(api): surface backend error detail from apiFetch"
```

---

### Task 7: Lớp API cho luồng file (frontend)

**Files:**
- Create: `frontend/src/lib/files.ts`

**Interfaces:**
- Consumes: `apiFetch`, `ApiError` từ `@/lib/api` (Task 6); hình dạng `FileOut`/`FileDetailOut` từ Task 5
- Produces:
  - `type FileType = "md" | "docx" | "pptx" | "pdf"`
  - `type ProcessingStatus = "pending" | "processing" | "ready_for_review" | "error" | "done"`
  - `interface UserFile` — khớp `FileOut`
  - `interface DraftChapter { title: string; content_md: string; order_index: number }`
  - `interface UserFileDetail extends UserFile { draft_outline: DraftChapter[] | null }`
  - `interface ConfirmChapter { title: string; source_indexes: number[] }`
  - `listFiles(): Promise<UserFile[]>`
  - `getFile(id): Promise<UserFileDetail>`
  - `processFile(id): Promise<void>`
  - `confirmChapters(id, chapters): Promise<{ lesson_count: number }>`
  - `uploadFile(file, onStep): Promise<string>` — chạy presign → PUT R2 → process, trả `file_id`
  - `MAX_FILE_BYTES`, `ACCEPTED_EXTENSIONS`, `fileTypeOf(name)`

Tách khỏi component để trang chỉ lo hiển thị, và để bước `PUT` thẳng lên R2 nằm ở đúng một chỗ có ghi rõ lý do không dùng `apiFetch`.

- [ ] **Step 1: Viết `files.ts`**

Tạo `frontend/src/lib/files.ts`:

```ts
import { ApiError, apiFetch } from "@/lib/api"

export type FileType = "md" | "docx" | "pptx" | "pdf"

export type ProcessingStatus =
  | "pending"
  | "processing"
  | "ready_for_review"
  | "error"
  | "done"

export interface UserFile {
  id: string
  file_name: string
  file_type: FileType
  file_size: number | null
  processing_status: ProcessingStatus
  error_message: string | null
  uploaded_at: string | null
  chapter_count: number | null
}

export interface DraftChapter {
  title: string
  content_md: string
  order_index: number
}

export interface UserFileDetail extends UserFile {
  draft_outline: DraftChapter[] | null
}

export interface ConfirmChapter {
  title: string
  source_indexes: number[]
}

export const MAX_FILE_BYTES = 20 * 1024 * 1024
export const ACCEPTED_EXTENSIONS = [".md", ".docx", ".pptx", ".pdf"] as const

/** File extension -> backend file_type, or null if unsupported. */
export function fileTypeOf(fileName: string): FileType | null {
  const ext = fileName.toLowerCase().split(".").pop()
  if (ext === "md" || ext === "docx" || ext === "pptx" || ext === "pdf") return ext
  return null
}

export function listFiles(): Promise<UserFile[]> {
  return apiFetch("/api/files")
}

export function getFile(fileId: string): Promise<UserFileDetail> {
  return apiFetch(`/api/files/${fileId}`)
}

export async function processFile(fileId: string): Promise<void> {
  await apiFetch(`/api/files/${fileId}/process`, { method: "POST" })
}

export function confirmChapters(
  fileId: string,
  chapters: ConfirmChapter[],
): Promise<{ lesson_count: number }> {
  return apiFetch(`/api/files/${fileId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chapters }),
  })
}

export type UploadStep = "presigning" | "uploading" | "processing"

/**
 * presign -> PUT straight to R2 -> ask the backend to process. Returns file_id.
 *
 * Each step reports through `onStep` so the page can say which one is running
 * instead of showing a fake progress bar.
 */
export async function uploadFile(
  file: File,
  onStep: (step: UploadStep) => void,
): Promise<string> {
  const fileType = fileTypeOf(file.name)
  if (!fileType) throw new Error("Định dạng không hỗ trợ. Chỉ nhận .md, .docx, .pptx, .pdf.")
  if (file.size > MAX_FILE_BYTES) throw new Error("File vượt quá giới hạn 20MB.")
  if (file.size === 0) throw new Error("File rỗng.")

  onStep("presigning")
  const { file_id, upload_url } = await apiFetch("/api/files/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_name: file.name,
      file_type: fileType,
      file_size: file.size,
    }),
  })

  onStep("uploading")
  // Plain fetch, NOT apiFetch: a presigned URL carries its own signature and
  // adding an Authorization header invalidates it. This is the only place in
  // the app that talks to something other than our own backend.
  const putRes = await fetch(upload_url, { method: "PUT", body: file })
  if (!putRes.ok) throw new Error("Tải file lên thất bại. Hãy thử lại.")

  onStep("processing")
  await processFile(file_id)
  return file_id
}

/** Message for any thrown value, preferring the backend's Vietnamese detail. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError || err instanceof Error) return err.message
  return "Đã có lỗi xảy ra."
}
```

- [ ] **Step 2: Kiểm tra build**

Run: `cd frontend && npm run build`
Expected: build sạch. (`files.ts` chưa được import ở đâu — TypeScript vẫn typecheck nó qua `tsc -b`.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/files.ts
git commit -m "feat(files): add frontend API layer for the upload flow"
```

---

### Task 8: Trang `/files` — upload + danh sách + poll

**Files:**
- Create: `frontend/src/components/UploadDropzone.tsx`
- Create: `frontend/src/components/FileTable.tsx`
- Create: `frontend/src/pages/Files.tsx`

**Interfaces:**
- Consumes: mọi thứ Task 7 export
- Produces: `<Files />` (default export không dùng — export tên `Files`), dùng ở Task 10

- [ ] **Step 1: Viết `UploadDropzone.tsx`**

```tsx
import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  ACCEPTED_EXTENSIONS,
  errorMessage,
  uploadFile,
  type UploadStep,
} from "@/lib/files"

const STEP_LABEL: Record<UploadStep, string> = {
  presigning: "Đang chuẩn bị tải lên…",
  uploading: "Đang tải file lên…",
  processing: "Đang bắt đầu xử lý…",
}

export function UploadDropzone({ onUploaded }: { onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<UploadStep | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  async function handleFile(file: File) {
    setError(null)
    try {
      await uploadFile(file, setStep)
      onUploaded()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setStep(null)
      // Clear the input so picking the same file again still fires onChange.
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        const file = e.dataTransfer.files[0]
        if (file) void handleFile(file)
      }}
      className={`rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
        dragging ? "border-primary bg-primary/5" : "border-gray-300"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS.join(",")}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) void handleFile(file)
        }}
      />
      {step ? (
        <p className="text-sm text-gray-600">{STEP_LABEL[step]}</p>
      ) : (
        <>
          <p className="mb-3 text-sm text-gray-600">
            Kéo thả tài liệu vào đây, hoặc
          </p>
          <Button onClick={() => inputRef.current?.click()}>Chọn file</Button>
          <p className="mt-3 text-xs text-gray-500">
            Nhận .md, .docx, .pptx, .pdf — tối đa 20MB
          </p>
        </>
      )}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 2: Viết `FileTable.tsx`**

```tsx
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import type { ProcessingStatus, UserFile } from "@/lib/files"

const STUCK_AFTER_MS = 10 * 60 * 1000

const BADGE_CLASS: Record<ProcessingStatus, string> = {
  pending: "bg-gray-100 text-gray-700",
  processing: "bg-blue-100 text-blue-700",
  ready_for_review: "bg-amber-100 text-amber-800",
  error: "bg-red-100 text-red-700",
  done: "bg-green-100 text-green-700",
}

function statusLabel(file: UserFile): string {
  switch (file.processing_status) {
    case "pending":
      return "Chưa xử lý"
    case "processing":
      return "Đang xử lý…"
    case "ready_for_review":
      return file.chapter_count === null
        ? "Chờ duyệt"
        : `Chờ duyệt · ${file.chapter_count} chương`
    case "error":
      return "Lỗi"
    case "done":
      return "Đã duyệt"
  }
}

/**
 * A file whose background task died with the backend stays `processing`
 * forever (a known, accepted risk from #1a). Offering "Xử lý lại" after ten
 * minutes is the escape hatch. The clock runs from `uploaded_at` because the
 * schema records no processing-start time; a file left alone for hours before
 * anyone pressed "Xử lý" therefore shows the button immediately, which is
 * harmless -- pressing it returns 409 and the list refetches.
 */
function looksStuck(file: UserFile): boolean {
  if (file.processing_status !== "processing" || !file.uploaded_at) return false
  return Date.now() - new Date(file.uploaded_at).getTime() > STUCK_AFTER_MS
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return ""
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function FileTable({
  files,
  onProcess,
  busyId,
}: {
  files: UserFile[]
  onProcess: (fileId: string) => void
  busyId: string | null
}) {
  if (files.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-500">
        Chưa có tài liệu nào. Tải lên file đầu tiên để bắt đầu.
      </p>
    )
  }

  return (
    <ul className="divide-y rounded-lg border">
      {files.map((file) => (
        <li key={file.id} className="flex items-center gap-4 p-4">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{file.file_name}</p>
            <p className="text-xs text-gray-500">{formatSize(file.file_size)}</p>
            {file.processing_status === "error" && file.error_message && (
              <p className="mt-1 text-sm text-red-600">{file.error_message}</p>
            )}
          </div>
          <span
            className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${
              BADGE_CLASS[file.processing_status]
            }`}
          >
            {statusLabel(file)}
          </span>
          <div className="w-32 shrink-0 text-right">
            {file.processing_status === "pending" && (
              <Button
                size="sm"
                disabled={busyId === file.id}
                onClick={() => onProcess(file.id)}
              >
                Xử lý
              </Button>
            )}
            {(file.processing_status === "error" || looksStuck(file)) && (
              <Button
                size="sm"
                variant="outline"
                disabled={busyId === file.id}
                onClick={() => onProcess(file.id)}
              >
                Xử lý lại
              </Button>
            )}
            {file.processing_status === "ready_for_review" && (
              <Button size="sm" asChild>
                <Link to={`/files/${file.id}/review`}>Duyệt chương</Link>
              </Button>
            )}
            {file.processing_status === "done" && (
              <Button size="sm" variant="outline" asChild>
                <Link to={`/files/${file.id}/review`}>Xem lại</Link>
              </Button>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
```

Nếu `Button` trong repo chưa hỗ trợ prop `asChild` hoặc `size="sm"`, thay bằng `<Link>` có class của button, đừng sửa `button.tsx` — kiểm tra `frontend/src/components/ui/button.tsx` trước khi viết.

- [ ] **Step 3: Viết `Files.tsx`**

```tsx
import { useCallback, useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { FileTable } from "@/components/FileTable"
import { UploadDropzone } from "@/components/UploadDropzone"
import { errorMessage, listFiles, processFile, type UserFile } from "@/lib/files"

const POLL_INTERVAL_MS = 3000

export function Files() {
  const [files, setFiles] = useState<UserFile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      setFiles(await listFiles())
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

  // Poll only while something is actually running, and never while the tab is
  // hidden -- a forgotten tab must not keep hitting the API forever.
  useEffect(() => {
    const anyProcessing = files.some((f) => f.processing_status === "processing")

    function stop() {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }
    }

    function sync() {
      if (anyProcessing && document.visibilityState === "visible") {
        if (timerRef.current === null) {
          timerRef.current = window.setInterval(() => void refresh(), POLL_INTERVAL_MS)
        }
      } else {
        stop()
      }
    }

    sync()
    document.addEventListener("visibilitychange", sync)
    return () => {
      document.removeEventListener("visibilitychange", sync)
      stop()
    }
  }, [files, refresh])

  async function handleProcess(fileId: string) {
    setBusyId(fileId)
    setError(null)
    try {
      await processFile(fileId)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
      // Refetch either way: on success to pick up `processing`, on failure to
      // resync with whatever state the backend actually holds.
      await refresh()
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Tài liệu của tôi</h1>
        <Link to="/" className="text-sm text-gray-500 underline">
          Trang chủ
        </Link>
      </div>

      <UploadDropzone onUploaded={refresh} />

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading ? (
        <p className="py-8 text-center text-sm text-gray-500">Đang tải…</p>
      ) : (
        <FileTable files={files} onProcess={handleProcess} busyId={busyId} />
      )}
    </div>
  )
}
```

- [ ] **Step 4: Kiểm tra build**

Run: `cd frontend && npm run build`
Expected: build sạch. Nếu lỗi liên quan `asChild`/`size` của Button thì sửa `FileTable.tsx` theo API thật của `button.tsx`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/UploadDropzone.tsx frontend/src/components/FileTable.tsx frontend/src/pages/Files.tsx
git commit -m "feat(ui): add files page with upload, list and status polling"
```

---

### Task 9: Trang `/files/:id/review` — duyệt chương

**Files:**
- Create: `frontend/src/pages/ReviewChapters.tsx`

**Interfaces:**
- Consumes: `getFile`, `confirmChapters`, `errorMessage`, `DraftChapter`, `ConfirmChapter` từ Task 7
- Produces: `<ReviewChapters />`, dùng ở Task 10

State client là mảng `{ title, source_indexes }` — **đúng hình dạng payload gửi đi**, nên không cần tầng chuyển đổi lúc submit.

- [ ] **Step 1: Viết `ReviewChapters.tsx`**

```tsx
import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  confirmChapters,
  errorMessage,
  getFile,
  type ConfirmChapter,
  type DraftChapter,
} from "@/lib/files"

/** A chapter as edited on this page: the payload shape plus a preview. */
interface EditableChapter extends ConfirmChapter {
  preview: string
  charCount: number
}

const PREVIEW_CHARS = 300

function toEditable(draft: DraftChapter[], indexes: number[], title: string): EditableChapter {
  const content = indexes.map((i) => draft[i].content_md).join("\n\n")
  return {
    title,
    source_indexes: indexes,
    preview: content.slice(0, PREVIEW_CHARS),
    charCount: content.length,
  }
}

export function ReviewChapters() {
  const { fileId } = useParams<{ fileId: string }>()
  const navigate = useNavigate()

  const [fileName, setFileName] = useState("")
  const [readOnly, setReadOnly] = useState(false)
  const [draft, setDraft] = useState<DraftChapter[]>([])
  const [chapters, setChapters] = useState<EditableChapter[]>([])
  const [removed, setRemoved] = useState<{ at: number; chapter: EditableChapter } | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!fileId) return
    getFile(fileId)
      .then((file) => {
        const outline = file.draft_outline ?? []
        setFileName(file.file_name)
        setReadOnly(file.processing_status === "done")
        setDraft(outline)
        setChapters(outline.map((c, i) => toEditable(outline, [i], c.title)))
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [fileId])

  function renameChapter(position: number, title: string) {
    setChapters((prev) =>
      prev.map((c, i) => (i === position ? { ...c, title } : c)),
    )
  }

  function mergeIntoPrevious(position: number) {
    setChapters((prev) => {
      const previous = prev[position - 1]
      const current = prev[position]
      const merged = toEditable(
        draft,
        [...previous.source_indexes, ...current.source_indexes],
        previous.title,
      )
      return [...prev.slice(0, position - 1), merged, ...prev.slice(position + 1)]
    })
    setRemoved(null)
  }

  function removeChapter(position: number) {
    // Dropping a chapter loses content, so it always leaves one level of undo.
    setRemoved({ at: position, chapter: chapters[position] })
    setChapters((prev) => prev.filter((_, i) => i !== position))
  }

  function undoRemove() {
    if (!removed) return
    setChapters((prev) => [
      ...prev.slice(0, removed.at),
      removed.chapter,
      ...prev.slice(removed.at),
    ])
    setRemoved(null)
  }

  function toggleExpanded(position: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(position)) next.delete(position)
      else next.add(position)
      return next
    })
  }

  async function handleConfirm() {
    if (!fileId) return
    setSubmitting(true)
    setError(null)
    try {
      await confirmChapters(
        fileId,
        chapters.map(({ title, source_indexes }) => ({ title, source_indexes })),
      )
      navigate("/files")
    } catch (err) {
      setError(errorMessage(err))
      setSubmitting(false)
    }
  }

  if (loading) return <p className="p-8 text-sm text-gray-500">Đang tải…</p>

  const canSubmit =
    !readOnly &&
    !submitting &&
    chapters.length > 0 &&
    chapters.every((c) => c.title.trim().length > 0)

  return (
    <div className="mx-auto max-w-3xl p-8 pb-28">
      <h1 className="text-xl font-semibold">Duyệt chương</h1>
      <p className="mt-1 text-sm text-gray-500">{fileName}</p>

      {readOnly && (
        <p className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800">
          File đã duyệt xong. Không sửa được nữa.
        </p>
      )}
      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <ul className="mt-6 space-y-4">
        {chapters.map((chapter, position) => (
          <li key={chapter.source_indexes[0]} className="rounded-lg border p-4">
            <Input
              value={chapter.title}
              disabled={readOnly}
              onChange={(e) => renameChapter(position, e.target.value)}
            />
            <p className="mt-2 text-xs text-gray-500">
              {chapter.charCount.toLocaleString("vi-VN")} ký tự
              {chapter.source_indexes.length > 1 &&
                ` · gộp từ ${chapter.source_indexes.length} chương`}
            </p>
            <button
              type="button"
              onClick={() => toggleExpanded(position)}
              className="mt-2 w-full text-left text-sm text-gray-600"
            >
              <span
                className={expanded.has(position) ? "whitespace-pre-wrap" : "line-clamp-3"}
              >
                {chapter.preview}
              </span>
            </button>
            {!readOnly && (
              <div className="mt-3 flex gap-2">
                {position > 0 && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => mergeIntoPrevious(position)}
                  >
                    Gộp với chương trên
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => removeChapter(position)}
                >
                  Bỏ chương này
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {chapters.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-500">
          Đã bỏ hết chương. Hoàn tác hoặc tải lại trang để bắt đầu lại.
        </p>
      )}

      {removed && (
        <div className="mt-4 flex items-center gap-3 rounded bg-gray-100 p-3 text-sm">
          <span>Đã bỏ “{removed.chapter.title}”.</span>
          <Button size="sm" variant="outline" onClick={undoRemove}>
            Hoàn tác
          </Button>
        </div>
      )}

      {!readOnly && (
        <div className="fixed inset-x-0 bottom-0 border-t bg-white p-4">
          <div className="mx-auto flex max-w-3xl items-center justify-between">
            <span className="text-sm text-gray-600">
              Sẽ tạo {chapters.length} bài học
            </span>
            <Button disabled={!canSubmit} onClick={handleConfirm}>
              {submitting ? "Đang lưu…" : "Xác nhận"}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
```

Ghi chú về `key`: dùng `source_indexes[0]` chứ không dùng `position` — sau khi gộp/bỏ, position thay đổi nhưng index gốc đầu tiên của một chương thì không, nên React không dựng lại nhầm ô input.

- [ ] **Step 2: Kiểm tra `line-clamp` có sẵn**

Run: `cd frontend && grep -rn "line-clamp" src/index.css`
Nếu không có gì và Tailwind 4 không bật sẵn plugin, thay `line-clamp-3` bằng `max-h-16 overflow-hidden`.

- [ ] **Step 3: Kiểm tra build**

Run: `cd frontend && npm run build`
Expected: build sạch.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ReviewChapters.tsx
git commit -m "feat(ui): add chapter review page with rename, merge and drop"
```

---

### Task 10: Nối route + verify thật + cập nhật checklist

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Home.tsx`
- Modify: `check_list.md`

**Interfaces:**
- Consumes: `Files` (Task 8), `ReviewChapters` (Task 9)
- Produces: sản phẩm cuối

- [ ] **Step 1: Thêm route vào `App.tsx`**

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Login } from "@/pages/Login"
import { AuthCallback } from "@/pages/AuthCallback"
import { Home } from "@/pages/Home"
import { Files } from "@/pages/Files"
import { ReviewChapters } from "@/pages/ReviewChapters"
import { ProtectedRoute } from "@/components/ProtectedRoute"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route
          path="/files"
          element={
            <ProtectedRoute>
              <Files />
            </ProtectedRoute>
          }
        />
        <Route
          path="/files/:fileId/review"
          element={
            <ProtectedRoute>
              <ReviewChapters />
            </ProtectedRoute>
          }
        />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Home />
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
```

Route `/files` phải nằm **trước** `/*`, nếu không catch-all sẽ nuốt mất.

- [ ] **Step 2: Thêm link vào `Home.tsx`**

Trong khối `<div className="flex gap-2">` của `frontend/src/pages/Home.tsx`, thêm trước nút "Gọi /api/me":

```tsx
        <Button onClick={() => navigate("/files")}>Tài liệu của tôi</Button>
```

(`navigate` đã có sẵn trong component.)

- [ ] **Step 3: Kiểm tra build**

Run: `cd frontend && npm run build`
Expected: build sạch.

- [ ] **Step 4: Chạy toàn bộ test backend**

Run: `cd backend && python -m pytest`
Expected: PASS toàn bộ, output sạch, không warning mới.

- [ ] **Step 5: Commit code**

```bash
git add frontend/src/App.tsx frontend/src/pages/Home.tsx
git commit -m "feat(ui): route /files and /files/:fileId/review"
```

- [ ] **Step 6: Verify thật — chạy cả hai nửa**

```bash
# terminal 1
cd backend && .venv/Scripts/Activate.ps1 && python -m uvicorn app.main:app --port 8000
# terminal 2
cd frontend && npm run dev
```

Mở `http://localhost:5173`, đăng nhập bằng magic link.

- [ ] **Step 7: Verify thật — 6 mục bắt buộc của spec §8**

Dùng lại chính file `.docx` 6MB và `.pdf` 30 trang đã verify ở #1a. Ghi lại bằng chứng cho từng mục:

1. Upload `.docx` qua UI → trạng thái tự chuyển `pending` → `processing` → `ready_for_review` **không cần F5**
2. Vào trang duyệt: gộp 2 chương, đổi tên 1 chương, bỏ 1 chương, bấm Hoàn tác rồi bỏ lại → Xác nhận
3. Kiểm tra bảng `lessons` trên Supabase thật: đúng số dòng, `content_md` của chương gộp chứa nội dung cả hai, `order_index` liên tục 0..N-1
4. Upload `.docx` **không có heading style** → verify heuristic ra nhiều chương thay vì 3 cục "Mở đầu"
5. Upload file hỏng → trạng thái `error` + thông báo tiếng Việt → bấm "Xử lý lại" chạy được
6. RLS: dùng anon key (chưa đăng nhập) query `lessons` → **0 dòng**

Nếu mục nào không đạt: dừng, sửa, chạy lại. **Không đánh dấu xong dựa vào pytest.**

- [ ] **Step 8: Cập nhật `check_list.md`**

Trong mục `### #1b — UI upload + duyệt chương`, đánh dấu `[x]` cả 3 dòng và thêm dòng spec/plan + bằng chứng verify theo đúng định dạng mục `#1a` phía trên.

Trong mục **Nợ kỹ thuật**, xoá 2 dòng đã giải quyết:
- dòng `/process` gọi trên file `ready_for_review`/`done` sẽ ghi đè `draft_outline`…
- dòng `GET /api/files*` trả `select("*")`, lộ `storage_path` + `user_id`…

Thêm dòng nợ mới: `_FakeRepo` giờ lặp ở 3 file test (`test_files_api.py`, `test_pipeline.py`, `test_confirm_api.py`) — đủ điều kiện gom vào `conftest.py` theo chính ghi chú đã có.

- [ ] **Step 9: Commit**

```bash
git add check_list.md
git commit -m "docs: mark #1b complete, retire two resolved tech-debt items"
```

---

## Ghi chú cho người thực thi

**Chỗ dễ sai nhất:**
1. `PUT` lên R2 phải dùng `fetch` trần. Gắn header `Authorization` vào presigned URL là hỏng chữ ký → 403 từ R2. Đây là ngoại lệ duy nhất với quy ước "mọi request qua `apiFetch`", và đã ghi comment tại chỗ.
2. Thứ tự trong `confirm`: insert `lessons` **trước**, `set_status(done)` **sau**. Đảo lại là để lại file `done` không có bài học nào.
3. Route `/files` phải đặt trước `/*` trong `App.tsx`.
4. Pydantic chặn payload sai kiểu → **422**, không phải 400. `_validate_source_indexes` mới trả 400. Đừng "sửa" test cho hai loại về cùng một mã.
5. Heuristic docx **không** áp cho list item — danh sách đánh số của Word là list thật.

**Nếu bí:** spec ở `docs/superpowers/specs/2026-07-19-upload-review-ui-design.md` có bảng trạng thái, bảng lỗi và lý do đằng sau mọi quyết định.
