# Architecture — Personal LMS

Kiến trúc hệ thống ở mức tổng quan. Cập nhật khi cấu trúc thay đổi.

## Sơ đồ tổng quan

Frontend và Backend là **hai deployment tách biệt**, giao tiếp qua REST API kèm JWT.

```
                             ┌───────────────────────┐
   file .md/.docx            │  VERCEL (static)      │
   .pptx/.pdf  ─────────────►│  React SPA (Vite)     │
   (user upload)             │  /login /dashboard    │
                             │  /upload /lessons/... │
                             └───────────┬───────────┘
        ┌────────────────────────────────┤ fetch + Authorization: Bearer <JWT>
        │ PUT thẳng lên R2               ▼
        │ (presigned URL)     ┌───────────────────────┐
        │                     │  KOYEB (Docker)       │
        │                     │  FastAPI              │
        │                     │  /api/files/*  /me    │
        │                     │  /api/quiz/grade      │
        │                     │  /api/chat/{id} ...   │
        │                     └───┬───────────┬───────┘
        │                         │           │
        │     ┌──────────────────▼──┐  ┌─────▼────────────┐  ┌──────────────┐
        │     │   Supabase          │  │  Google Gemini   │  │ Cloudflare   │
        │     │   (Postgres)        │  │  (google-genai)  │  │ R2 (S3 API)  │
        │     │  - Auth (Magic Link)│  │  - sinh câu hỏi  │  │  file gốc    │
        │     │  - tables + RLS     │  │  - grading       │  │  private     │
        │     │  - pgvector         │  │  - chat          │  │  bucket      │
        │     └─────────────────────┘  └──────────────────┘  └──────┬───────┘
        └────────────────────────────────────────────────────────────┘
                        ▲
                        └──── frontend nói thẳng với Supabase Auth (Magic Link, session)
```

Điểm mấu chốt: **frontend xử lý toàn bộ luồng auth trực tiếp với Supabase Auth**; backend không quản
session, chỉ verify JWT đính kèm mỗi request.

## Các lớp

### Frontend (React + Vite + React Router, TypeScript, Tailwind, Shadcn)
- SPA thuần, **không SSR** — build tĩnh, Vercel chỉ serve file.
- Auth bằng `@supabase/supabase-js` (Magic Link). Session lưu ở browser, tự refresh.
- Bảo vệ route bằng component `ProtectedRoute` (kiểm tra `getSession()` + `onAuthStateChange`).
  Không có middleware server-side.
- Mọi lời gọi backend đi qua `lib/api.ts` → `apiFetch()`, tự gắn `Authorization: Bearer <token>`.
- Charts: Tremor.

### Backend (FastAPI, Python)
- `dependencies/auth.py` — `get_current_user()`: verify JWT Supabase qua **JWKS/ES256**, kiểm tra
  `audience = "authenticated"`; trả `CurrentUser(user_id, email)`; hỏng → 401, thiếu cấu hình → 500.
- `CORSMiddleware` whitelist origin frontend qua `ALLOWED_ORIGINS` (KHÔNG dùng `*` vì có Bearer token).
- Routers hiện có: `/api/health` (public, dùng cho keep-alive), `/api/me` (protected).
- Routers sẽ thêm: `/api/files/*` (#1a — presign R2, process, trạng thái),
  `/api/quiz/grade` (structured output qua Pydantic), `/api/chat/{lesson_id}` (`StreamingResponse`),
  `/api/admin/invite`. `/api/sync` đã bỏ cùng Obsidian sync (D17).

### Data layer (Supabase Postgres) — không đổi theo pivot
- **Riêng tư** (D16): `lessons` — mỗi user chỉ thấy bài từ tài liệu mình upload. `questions`
  cũng riêng từng user (D13, migration ở #4a).
- **Riêng tư** (RLS `auth.uid() = user_id`): `quiz_attempts`, `lesson_progress`, `chat_sessions`,
  `daily_activity`, `user_files`, `document_chunks`.
- **Profile**: `user_profiles` (đọc chung cho leaderboard, sửa của riêng mình).
- **View**: `leaderboard_view` (aggregate, cố ý bypass RLS — chỉ số liệu tổng hợp).
- **Vector**: `document_chunks.embedding VECTOR(768)` + HNSW index (`vector_cosine_ops`).
- **Trigger**: tạo `user_profiles` tự động khi có user mới trong `auth.users`.

### Storage (Cloudflare R2) — hoãn cùng RAG
- Bucket private `user-documents`. Key pattern: `{user_id}/{file_id}/{filename}`.
- Truy cập qua presigned URL ngắn hạn (`boto3`).

### AI (Google Gemini qua `google-genai`)
- Grading: structured output ép theo Pydantic model `{ score, missing_points[], comment }`.
- Chat: streaming → FastAPI `StreamingResponse`.
- Embedding: model đa phương thức, `output_dimensionality = 768` (phải khớp `VECTOR(768)`).
- Model chat = `gemini-2.5-flash` (chốt 2026-07-21). Embedding — chốt sau cùng RAG.

## Tổ chức code (folder layout)

Một repo, hai thư mục độc lập:

```
frontend/src/   # main.tsx, App.tsx (router), lib/{supabase,api,utils}, components/{ui,ProtectedRoute}, pages/
backend/app/    # main.py, dependencies/auth.py, routers/, config/callout_types.py  (sau: parser/, ai/, rag/)
backend/tests/  # pytest
supabase/migrations/   # SQL schema
```

Ranh giới: hai bên **không share code**, chỉ share hợp đồng REST. Alias `@` → `frontend/src`.

## Module quan trọng

### Ingest: Upload → Extract → Cắt chương (chưa làm — sub-project #1a)
Spec: `docs/superpowers/specs/2026-07-18-upload-extract-design.md`

- `ingest/extractors/` — mỗi định dạng một module, cùng chữ ký `extract(bytes) -> str`:
  `.md` (`python-frontmatter`), `.docx` (`python-docx`), `.pptx` (`python-pptx`),
  `.pdf` (`pypdf`). **Không OCR** — PDF không có text layer báo lỗi rõ (D19).
- `ingest/splitter.py` — `split_into_chapters(md, file_type)`, thuần túy, chỉ ăn markdown nên
  test được độc lập. Cắt theo heading cấp cao nhất, trần 8000 ký tự/chương.
- Một file → **nhiều** `lessons` (D18): `user_files` là "cuốn sách", `lessons` là "chương",
  nối bằng `source_file_id` + `order_index`.
- Kết quả cắt để ở `user_files.draft_outline` (jsonb) cho user duyệt ở #1b, **chưa** ghi `lessons`.
- Câu hỏi **không** parse từ tài liệu — AI sinh riêng từng user ở #4a (D13). `callout_types.py`
  giữ lại với vai trò enum ép AI chọn `type`.
- Không có đáp án mẫu — AI chấm dựa trên toàn bộ `lesson.content_md`.

## Ranh giới bảo mật

- Frontend dùng **anon key** (RLS ràng buộc). Backend dùng **service-role key** (bypass RLS) — chỉ
  cho các tác vụ hệ thống như `/api/sync`, không bao giờ lộ ra client.
- Backend verify JWT bằng **khóa công khai từ JWKS** (ES256), thuật toán pin cứng — không chấp nhận
  `alg` khác, không có shared secret để rò rỉ.
- CORS whitelist domain frontend cụ thể, `allow_credentials=True`.
- Upload: `storage_path` trên R2 luôn có tiền tố `{user_id}/`; presigned URL hết hạn 15 phút;
  bucket private. Endpoint `/api/files/*` lấy `user_id` từ JWT, **không** nhận từ client — thao
  tác lên file người khác trả **404** (không phải 403, tránh lộ sự tồn tại).
- RAG retrieval luôn filter cứng `user_id` — không rò tài liệu giữa các user.
