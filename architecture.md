# Architecture — Personal LMS

Kiến trúc hệ thống ở mức tổng quan. Cập nhật khi cấu trúc thay đổi.

## Sơ đồ tổng quan

Frontend và Backend là **hai deployment tách biệt**, giao tiếp qua REST API kèm JWT.

```
   Obsidian Vault            ┌───────────────────────┐
   (admin, local)            │  VERCEL (static)      │
        │                    │  React SPA (Vite)     │
   Obsidian Git              │  /login /dashboard    │
        │ push               │  /lessons/:slug ...   │
        ▼                    └───────────┬───────────┘
   GitHub (private)                      │ fetch + Authorization: Bearer <JWT>
        │ webhook                        ▼
        │                    ┌───────────────────────┐
        └───────────────────►│  KOYEB (Docker)       │
          POST /api/sync     │  FastAPI              │
                             │  /api/sync  /api/me   │
                             │  /api/quiz/grade      │
                             │  /api/chat/{id} ...   │
                             └───┬───────────┬───────┘
                                 │           │
              ┌──────────────────▼──┐  ┌─────▼────────────┐  ┌──────────────┐
              │   Supabase          │  │  Google Gemini   │  │ Cloudflare   │
              │   (Postgres)        │  │  (google-genai)  │  │ R2 (S3 API)  │
              │  - Auth (Magic Link)│  │  - grading       │  │  file gốc    │
              │  - tables + RLS     │  │  - chat          │  │  private     │
              │  - pgvector         │  │  - embedding     │  │  bucket      │
              └─────────────────────┘  └──────────────────┘  └──────────────┘
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
- Routers sẽ thêm: `/api/sync` (webhook GitHub, verify HMAC, parse, upsert bằng service-role),
  `/api/quiz/grade` (structured output qua Pydantic), `/api/chat/{lesson_id}` (`StreamingResponse`),
  `/api/documents/upload` (R2 + RAG — hoãn), `/api/admin/invite`.

### Data layer (Supabase Postgres) — không đổi theo pivot
- **Dùng chung**: `lessons`, `questions` (chỉ service-role ghi; user chỉ đọc).
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
- Model IDs cụ thể — chốt sau (xem `check_list.md`).

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

### Markdown/Callout Parser (chưa làm — sub-project #1)
- Module **Python thuần túy, độc lập** với webhook: `input: markdown string` → `output:
  { frontmatter, content, questions[] }` (dict/Pydantic model).
- Frontmatter qua `python-frontmatter` (`title`, `week`, `topic`).
- Callout: quét block `> [!type]`, chỉ nhận type có trong `backend/app/config/callout_types.py`
  (`QUESTION_TYPES`).
- Không có đáp án mẫu — AI chấm dựa trên toàn bộ `lesson.content_md`.

## Ranh giới bảo mật

- Frontend dùng **anon key** (RLS ràng buộc). Backend dùng **service-role key** (bypass RLS) — chỉ
  cho các tác vụ hệ thống như `/api/sync`, không bao giờ lộ ra client.
- Backend verify JWT bằng **khóa công khai từ JWKS** (ES256), thuật toán pin cứng — không chấp nhận
  `alg` khác, không có shared secret để rò rỉ.
- CORS whitelist domain frontend cụ thể, `allow_credentials=True`.
- Webhook verify HMAC (`GITHUB_WEBHOOK_SECRET`) trước khi xử lý.
- RAG retrieval luôn filter cứng `user_id` — không rò tài liệu giữa các user.
