# Checklist — Personal LMS (14 bước)

Trạng thái: `[ ]` chưa làm · `[~]` đang làm · `[x]` xong · `[!]` cần user (key/quyết định)

Cập nhật file này mỗi khi hoàn thành một mục.

---

## Pass 1 — Scaffold + Schema (bước 1–2) — ✅ Code + schema XONG · ⏳ verify treo (chưa `npm install`)

### Bước 1 — Setup Next.js + Tailwind + Shadcn
- [x] `create-next-app` (App Router, TS, Tailwind v4, ESLint, no `src/`, alias `@/*`) — Next 16 + React 19
- [x] Shadcn UI init (`components.json`, `lib/utils.ts` với `cn()`, `components/ui/button.tsx`)
- [x] Placeholder home page (`app/page.tsx`) build sạch
- [x] Cài deps nền: `@supabase/supabase-js`, `@supabase/ssr`, `zod`, `server-only`

### Bước 2 — Supabase schema + RLS (migrations)
- [x] `0001_extensions.sql` — `CREATE EXTENSION vector`
- [x] `0002_tables.sql` — 9 bảng + HNSW index trên `document_chunks.embedding`
- [x] `0003_rls.sql` — bật RLS mọi bảng riêng tư + policies (đủ CRUD theo nhu cầu thật)
- [x] `0004_leaderboard_view.sql` — view + GRANT SELECT (ghi chú bypass RLS có chủ đích)
- [x] `0005_profile_trigger.sql` — trigger tạo `user_profiles` khi có user mới

### Config + docs (kèm Pass 1)
- [x] `config/callout-types.ts` — `QUESTION_TYPES` whitelist + type guard
- [x] `lib/supabase/{client,server,admin}.ts`
- [x] `types/database.types.ts`
- [x] `.env.example` (10 biến) + exception trong `.gitignore`
- [x] `SETUP.md` — hướng dẫn provision Supabase/R2/Gemini/GitHub/Vercel
- [x] `README.md` — overview + cách chạy

### Verify Pass 1
- [ ] `npm install` — `node_modules` chưa có trong workspace, nên lint/build hiện không chạy được
      (`'next' is not recognized`)
- [~] `npm run lint` sạch — đã pass lúc viết Pass 1; chạy lại sau `npm install` để xác nhận
- [~] `npm run build` sạch (TypeScript pass) — như trên
- [x] Review SQL: mọi bảng riêng tư có RLS; `vector(768)` + HNSW; trigger populate `display_name`
- [ ] Apply 5 migrations lên Supabase thật — key đã có trong `.env.local`, làm được ngay

---

## Pass sau (hoãn — chưa làm)

### Bước 3 — Auth
- [ ] Magic Link (Supabase Auth), tắt public sign-up
- [ ] Middleware bảo vệ route (trừ `/login`, `/auth/callback`)
- [ ] `/login`, `/auth/callback`

### Bước 4 — Parser Markdown/Callout
- [ ] Module thuần túy `parseLesson(md) -> { frontmatter, content, questions[] }`
- [ ] Test độc lập trước khi nối webhook
- Deps còn thiếu: test runner (chưa cài gì) + thư viện parse frontmatter

### Bước 5 — `/api/sync` + GitHub Webhook
- [ ] Verify HMAC `GITHUB_WEBHOOK_SECRET` — ⚠️ secret hiện tại chỉ 5 ký tự, phải thay trước (xem blocker)
- [ ] Đọc file .md trong diff qua GitHub API
- [ ] Upsert `lessons` / `questions` (service-role)

### Bước 6 — Lessons UI
- [ ] `/lessons` (list + tab lọc Tuần/Chủ đề + checkbox Đã học)
- [ ] `/lessons/[slug]` (render markdown + sidebar chat + câu hỏi tự luận)
- Deps còn thiếu: thư viện render markdown. Shadcn mới có mỗi `button.tsx` — cần thêm component khi làm

### Bước 7 — AI chấm điểm
- [ ] `generateObject` schema `{ score, missing_points[], comment }`
- [ ] Lưu `quiz_attempts` + upsert `daily_activity`
- [!] **Chốt model chat ID** (spec: `gemini-2.5-pro`/`gemini-2.0-flash`)
- Deps còn thiếu (chung với bước 8): `ai` + `@ai-sdk/google`

### Bước 8 — Socratic Chatbot
- [ ] `streamText`, sidebar cạnh lý thuyết
- [ ] Lưu `chat_sessions.messages`

### ⏸️ HOÃN (D8) — RAG / tài liệu cá nhân. Xây LÕI thuần Next.js trước. Chỉ làm khi nhóm thật sự cần.

### Bước 9 — R2 + Upload + `/documents` ⏸️ HOÃN
- [ ] Bucket private `user-documents`, S3 SDK
- [ ] Presigned URL, giới hạn 20MB/50 trang
- [ ] Trang `/documents` (kéo-thả, trạng thái, xem/tải, gắn lesson)

### Bước 10 — RAG pipeline ⏸️ HOÃN
- [ ] Extract (KHÔNG dùng Gemini — công cụ chọn sau); Chunk; Embedding (model + số chiều chọn sau)
- [ ] Insert `document_chunks`; xử lý lỗi → `processing_status='error'` + retry
- Lưu ý: bảng `user_files`/`document_chunks` giữ trong schema (vô hại), chỉ chưa build pipeline;
  `VECTOR(768)` là placeholder, chỉnh số chiều theo model khi làm.

### Bước 11 — Nối RAG vào AI ⏸️ HOÃN
- [ ] Retrieval top 5 cosine, filter `user_id`; inject chunks vào prompt grading + chat

### Bước 12 — Dashboard
- [ ] Streak (từ `daily_activity`)
- [ ] BarChart câu hỏi theo tuần (Tremor)
- [ ] % hoàn thành bài học
- [ ] Leaderboard (từ `leaderboard_view`)
- Deps còn thiếu: Tremor (hoặc Recharts)

### Bước 13 — `/admin/invite`
- [ ] Chỉ admin (`ADMIN_EMAIL`), thêm email thành viên

### Bước 14 — Deploy
- [ ] Vercel + env vars
- [ ] Test end-to-end

---

## Việc cần user (blocker)
- [x] Key LÕI đã có trong `.env.local`: Supabase (URL/anon/service-role), Gemini,
      GitHub webhook secret, `ADMIN_EMAIL` — hết blocker này
- [!] `GITHUB_WEBHOOK_SECRET` hiện chỉ 5 ký tự — quá yếu cho HMAC. Thay bằng chuỗi ngẫu nhiên
      32+ ký tự (và cập nhật cả webhook trên GitHub) trước bước 5
- [!] Chốt model AI Gemini (chat/grading) trước Pass build AI
- (HOÃN cùng RAG) R2 keys + embedding model — chỉ cần khi làm RAG sau này
