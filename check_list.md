# Checklist — Personal LMS (sub-project #0 → #8)

Trạng thái: `[ ]` chưa làm · `[~]` đang làm · `[x]` xong · `[!]` cần user (key/quyết định)

Việc chia thành các **sub-project độc lập**, mỗi cái đi trọn vòng spec → plan → build → review →
merge. Cập nhật file này mỗi khi hoàn thành một mục.

---

## Nền tảng dữ liệu — ✅ XONG (giữ nguyên qua pivot)

Schema Supabase dựng từ pass Next.js cũ và **được giữ lại 100%** khi đổi kiến trúc — không đụng dữ liệu.

- [x] `0001_extensions.sql` — `CREATE EXTENSION vector`
- [x] `0002_tables.sql` — 9 bảng + HNSW index trên `document_chunks.embedding`
- [x] `0003_rls.sql` — bật RLS mọi bảng riêng tư + policies
- [x] `0004_leaderboard_view.sql` — view + GRANT SELECT (bypass RLS có chủ đích)
- [x] `0005_profile_trigger.sql` — trigger tạo `user_profiles` khi có user mới
- [x] Đã apply 5 migration lên Supabase thật, verify 9 bảng + `leaderboard_view` tồn tại (10/10)
- [x] Verify RLS thật: anon key chưa đăng nhập → đọc bảng riêng tư ra 0 dòng; ghi `quiz_attempts`
      bị chặn 401
- [x] Verify trigger `0005` chạy: sau đăng nhập thật, `user_profiles` có đúng 1 dòng

---

## #0 — Foundation + Auth — ✅ XONG (merge `fa6f7e8`, 2026-07-18)

Spec/plan: `docs/superpowers/{specs,plans}/2026-07-18-foundation-auth*`

- [x] Gỡ scaffold Next.js, restructure repo thành `frontend/` + `backend/`
- [x] Backend FastAPI: `main.py` + CORS (từ `ALLOWED_ORIGINS`, không dùng `*`), `/api/health`
- [x] `get_current_user()` verify JWT Supabase + `/api/me` protected — **JWKS/ES256** (đo thực tế:
      project ký bất đối xứng, HS256 sẽ fail)
- [x] Frontend Vite + React Router + Tailwind + Shadcn + `supabase.ts` + `apiFetch()`
- [x] Magic Link login invite-only, AuthCallback, `ProtectedRoute`, Home placeholder
- [x] `docker-compose.yml` cho local dev (dev thường ngày dùng venv — xem D12)
- [x] Backend `pytest` 7/7 xanh, output sạch · frontend `npm run build` sạch

**Verify thật (có bằng chứng khách quan):**
- [x] Chưa đăng nhập vào `/` → bị đẩy sang `/login`
- [x] Invite-only: email chưa mời → báo "chưa được mời"; admin API xác nhận **không tạo user mới**
      (tổng user vẫn = 1)
- [x] Đăng nhập thật qua magic link: `last_sign_in_at` cập nhật đúng thời điểm
- [x] `/api/me` trả đúng user → chứng minh verify ES256 chạy end-to-end
- [x] Session bền qua F5; đăng xuất → về `/login`, route bị chặn lại

---

## Sub-project còn lại

### ~~#1 — Parser Markdown/Callout~~ · ~~#2 — `/api/sync` + GitHub Webhook~~ — ĐÃ BỎ
Bỏ hẳn 2026-07-18 (D17). Câu hỏi giờ do AI sinh chứ không parse từ callout (D13), và nội dung
vào bằng upload file chứ không qua Obsidian/GitHub (D16). Parser markdown vẫn sống, nhưng chỉ
còn là **một trong bốn** extractor của #1a. `GITHUB_WEBHOOK_SECRET` không cần nữa.

### #1a — Upload → Extract → Cắt chương (backend)
Spec: `docs/superpowers/specs/2026-07-18-upload-extract-design.md`
- [ ] Migration `0006`: `lessons` + `user_id`/`source_file_id`/`order_index`, RLS, unique
      `(user_id, slug)`; `user_files` + `draft_outline`, nới CHECK `file_type`/`processing_status`
- [ ] R2 qua `boto3` + `POST /api/files/presign` (≤20MB, hết hạn 15 phút)
- [ ] `POST /api/files/{id}/process` → `BackgroundTasks`; `GET /api/files/{id}`, `GET /api/files`
- [ ] 4 extractor `.md`/`.docx`/`.pptx`/`.pdf` (không OCR — PDF scan báo lỗi rõ, D19)
- [ ] `splitter.py` cắt chương theo heading, trần 8000 ký tự/chương
- [ ] Verify thật: upload `.docx` + `.pdf` nhiều chương lên R2 thật, kiểm `draft_outline`

### #1b — UI upload + duyệt chương
- [ ] Trang upload (presign → PUT thẳng R2 → process → poll trạng thái)
- [ ] Trang duyệt chương: sửa tên / gộp / bỏ → `POST /api/files/{id}/confirm` → ghi `lessons`
- [ ] Nút "Xử lý lại" cho file `error`, và cho file kẹt `processing` quá 10 phút

### #3 — Lessons UI
- [ ] `/lessons` (list + tab lọc Chủ đề + checkbox Đã học → `lesson_progress`)
- [ ] `/lessons/:slug` (render markdown + sidebar chat + câu hỏi tự luận)
- Deps còn thiếu: thư viện render markdown; thêm Shadcn component khi cần

### #4a — Sinh câu hỏi bằng AI (MỚI, thay cho parse callout — D13)
- [ ] Migration `0006`: thêm `questions.user_id` + RLS `auth.uid() = user_id`
      (bảng đang là dùng chung, không có `user_id`)
- [ ] Đổi vai trò `backend/app/config/callout_types.py`: từ whitelist parser → enum ép AI chọn
      khi sinh câu hỏi (structured output). Cột `type` + CHECK constraint giữ nguyên.
- [ ] Sinh câu hỏi **riêng từng user** khi user mở bài, context = nguyên `lessons.content_md`
      (KHÔNG dùng RAG — bài học đủ nhỏ để nhét cả vào prompt)
- [!] Phụ thuộc: chốt model chat ID

### #4 — AI chấm điểm
- [ ] `POST /api/quiz/grade` — structured output Pydantic `{ score, missing_points[], comment }`
- [ ] Lưu `quiz_attempts` + upsert `daily_activity`
- [!] **Chốt model chat ID** (spec gợi ý `gemini-2.5-pro` / `gemini-2.0-flash`)
- Deps còn thiếu: `google-genai`

### #5 — Socratic Chatbot
- [ ] `POST /api/chat/{lesson_id}` — `StreamingResponse`, sidebar cạnh lý thuyết
- [ ] Lưu `chat_sessions.messages`

### #6 — Dashboard
- [ ] Streak (từ `daily_activity`), BarChart câu hỏi theo tuần
- [ ] % hoàn thành bài học
- [ ] Leaderboard xếp theo **số ngày học** (count distinct `daily_activity.activity_date`),
      không xếp theo điểm — cần sửa `leaderboard_view` (migration mới). Xếp theo **giờ học**
      tạm hoãn: web không có cách đo thời gian đáng tin (heartbeat, tab bỏ quên) — xem D15
- [ ] Thay Home placeholder bằng dashboard thật (kèm logout tử tế)
- Deps còn thiếu: Tremor (hoặc Recharts)

### #7 — `/admin/invite`
- [ ] Endpoint chỉ admin (`ADMIN_EMAIL`) + trang thêm email thành viên

### #8 — Deploy
- [ ] Backend → Koyeb (Docker), keep-alive ping `/api/health` mỗi 10 phút
- [ ] Frontend → Vercel (static build)
- [ ] Đổi Supabase Site URL sang domain thật **và thêm `http://localhost:5173/**` vào Redirect URLs**
      (nếu không, dev local sẽ gãy)
- [ ] Cập nhật `ALLOWED_ORIGINS` cho domain production
- [ ] Test end-to-end trên production

### ⏸️ HOÃN (D8) — RAG / tài liệu cá nhân
Chỉ làm khi nhóm thật sự cần. Bảng `user_files`/`document_chunks` đã có sẵn trong schema.
- [ ] R2 + `/api/documents/upload` + trang `/documents` (presigned URL, giới hạn 20MB/50 trang)
- [ ] Pipeline extract → chunk → embed → `document_chunks`; lỗi → `processing_status='error'` + retry
- [ ] Nối RAG vào chấm điểm + chat (retrieval top 5 cosine, filter cứng `user_id`)
- Lưu ý: `VECTOR(768)` là placeholder — chỉnh số chiều theo model embedding khi chốt.
- Ràng buộc: doc processing **KHÔNG dùng Gemini** (D9).

---

## Nợ kỹ thuật / dọn dẹp (không chặn việc gì)

- [ ] `backend/app/dependencies/auth.py`: `payload["sub"]` truy cập trực tiếp → `KeyError`→500 nếu
      token hợp lệ mà thiếu `sub` (không xảy ra với token Supabase thật). Cân nhắc `.get()` + 401.
- [ ] JWKS fetch lỗi mạng đang trả 401; đúng ra nên 503 (lỗi phía server, không phải lỗi client).
- [ ] `frontend/src/pages/Home.tsx`: `handleSignOut` nuốt lỗi `signOut()` — Home là placeholder, sẽ
      thay ở #6, nhớ làm tử tế lúc đó.
- [ ] `backend/pytest.ini` đang suppress `StarletteDeprecationWarning` (dep transitive) — xem lại khi
      nâng dependency.
- [ ] `lucide-react` chưa được import ở đâu (giữ lại vì Shadcn sẽ cần khi thêm component ở #3).

## Việc cần user (blocker)

- [x] Key Supabase (URL/anon/service-role), Gemini, GitHub webhook secret, `ADMIN_EMAIL` — đã có
- [x] Supabase Site URL = `http://localhost:5173` cho dev — đã đổi
- [x] Không cần `SUPABASE_JWT_SECRET` nữa (verify bằng JWKS)
- [!] Chốt model AI Gemini (chat) trước #4a/#4
- [!] **R2 keys** (`R2_ACCOUNT_ID`, access key, secret, bucket) — cần cho #1a, user báo đã có
- Không cần `GITHUB_WEBHOOK_SECRET` nữa (D17 bỏ Obsidian sync)
- (HOÃN cùng RAG) embedding model
