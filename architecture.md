# Architecture — Personal LMS

Kiến trúc hệ thống ở mức tổng quan. Cập nhật khi cấu trúc thay đổi.

## Sơ đồ tổng quan

```
                    ┌──────────────────────────────────────────────┐
                    │                  VERCEL                       │
   Obsidian Vault   │   ┌────────────────────────────────────────┐ │
   (admin, local)   │   │            Next.js (App Router)         │ │
        │           │   │                                        │ │
   Obsidian Git     │   │  Pages:  /login /dashboard /lessons    │ │
        │ push      │   │          /lessons/[slug] /documents    │ │
        ▼           │   │          /admin/invite                 │ │
   GitHub (private) │   │  API:    /api/sync  /api/documents/*   │ │
        │ webhook   │   │          /api/grade /api/chat          │ │
        └──────────►│   └───────┬───────────────┬────────────────┘ │
                    │           │               │                  │
                    └───────────┼───────────────┼──────────────────┘
                                │               │
                 ┌──────────────▼───┐   ┌───────▼──────────┐   ┌──────────────┐
                 │   Supabase       │   │  Google Gemini   │   │ Cloudflare   │
                 │   (Postgres)     │   │  (Vercel AI SDK) │   │ R2 (S3 API)  │
                 │  - Auth (Magic)  │   │  - grading       │   │  file gốc    │
                 │  - tables + RLS  │   │  - chat          │   │  private     │
                 │  - pgvector      │   │  - embedding     │   │  bucket      │
                 └──────────────────┘   └──────────────────┘   └──────────────┘
```

## Các lớp

### Frontend (Next.js App Router, TypeScript, Tailwind, Shadcn)
- Server Components mặc định; Client Components cho phần tương tác (chat, upload, form).
- Charts: Tremor.
- Middleware: kiểm tra session ở mọi route trừ `/login`, `/auth/callback` (Pass sau).

### Backend (Next.js API Routes / Server Actions)
- `/api/sync` — nhận GitHub webhook, verify HMAC, đọc diff, parse, upsert (dùng service-role).
- `/api/documents/upload` — upload R2 + chạy RAG pipeline đồng bộ.
- `/api/grade` — chấm bài (`generateObject`).
- `/api/chat` — Socratic chat (`streamText`).

### Data layer (Supabase Postgres)
- **Dùng chung**: `lessons`, `questions` (chỉ service-role ghi; user chỉ đọc).
- **Riêng tư** (RLS `auth.uid() = user_id`): `quiz_attempts`, `lesson_progress`, `chat_sessions`,
  `daily_activity`, `user_files`, `document_chunks`.
- **Profile**: `user_profiles` (đọc chung cho leaderboard, sửa của riêng mình).
- **View**: `leaderboard_view` (aggregate, cố ý bypass RLS — chỉ số liệu tổng hợp).
- **Vector**: `document_chunks.embedding VECTOR(768)` + HNSW index (`vector_cosine_ops`).
- **Trigger**: tạo `user_profiles` tự động khi có user mới trong `auth.users`.

### Storage (Cloudflare R2)
- Bucket private `user-documents`. Key pattern: `{user_id}/{file_id}/{filename}`.
- Truy cập qua presigned URL ngắn hạn.

### AI (Google Gemini qua Vercel AI SDK)
- Grading: `generateObject` + Zod schema `{ score, missing_points[], comment }`.
- Chat: `streamText`.
- Embedding: model đa phương thức, `output_dimensionality = 768`.
- Model IDs cụ thể — chốt sau (xem `check_list.md`).

## Tổ chức code (folder layout)

Một app Next.js duy nhất, code chia 2 nửa. `app/` (routes) ở gốc vì Next.js yêu cầu; logic ở
`client/` + `server/`.

```
app/        # routes + API routes (thin)
client/     # UI: components/ui (shadcn), lib/utils, supabase/client (browser)
server/     # server-only: supabase/{server,admin}, config/callout-types, types/database.types
            #   (sau: parser/, ai/, rag/, db/)
supabase/migrations/   # SQL schema
```

Ranh giới: `client/` chỉ import **type-only** từ `server/` (không import runtime). Alias `@/*` →
root, dùng `@/client/...` và `@/server/...`.

## Module quan trọng

### Markdown/Callout Parser (Pass sau)
- Module **thuần túy, độc lập** với webhook: `input: markdown string` → `output: { frontmatter,
  content, questions[] }`.
- Frontmatter qua `gray-matter` (`title`, `week`, `topic`).
- Callout: quét block `> [!type]`, chỉ nhận type trong `server/config/callout-types.ts` (`QUESTION_TYPES`).
- Không có đáp án mẫu — AI chấm dựa trên toàn bộ `lesson.content_md`.

## Ranh giới bảo mật

- Client dùng **anon key** (RLS ràng buộc). Server-only dùng **service-role key** (bypass RLS,
  chỉ trong `/api/sync` và các API route server).
- Webhook verify HMAC (`GITHUB_WEBHOOK_SECRET`) trước khi xử lý.
- RAG retrieval luôn `WHERE user_id = auth.uid()` — không rò tài liệu giữa các user.
