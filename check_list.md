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

### #1a — Upload → Extract → Cắt chương (backend) — ✅ XONG (2026-07-19, nhánh `feature/upload-extract`)
Spec: `docs/superpowers/specs/2026-07-18-upload-extract-design.md`
Plan: `docs/superpowers/plans/2026-07-19-upload-extract-chapters.md`
- [x] Migration `0006`: `lessons` + `user_id`/`source_file_id`/`order_index`, RLS, unique
      `(user_id, slug)`; `user_files` + `draft_outline`, nới CHECK `file_type`/`processing_status`
      (kèm `drop policy lessons_select` — policy cũ cho mọi user đọc chung, không bỏ thì RLS vô nghĩa)
- [x] R2 qua `boto3` + `POST /api/files/presign` (≤20MB, hết hạn 15 phút)
- [x] `POST /api/files/{id}/process` → `BackgroundTasks`; `GET /api/files/{id}`, `GET /api/files`
- [x] 4 extractor `.md`/`.docx`/`.pptx`/`.pdf` (không OCR — PDF scan báo lỗi rõ, D19)
- [x] `splitter.py` cắt chương theo heading, trần 8000 ký tự/chương
- [x] 76/76 pytest xanh, output sạch

**Verify thật (chạy trên R2 thật + Supabase thật, qua đúng 4 endpoint HTTP):**
- [x] `.docx` 6MB → presign 200 → PUT R2 200 → process 202 → `ready_for_review`, 7 chương
- [x] `.pdf` 30 trang có text → 4 chương (`Phần 1..3`, phần dài tự cắt đôi), không chương nào >8000
- [x] PDF scan (14 trang, 0 ký tự text) → `error` + thông báo tiếng Việt gợi ý dùng bản có text
- [x] File hỏng → `error` + tiếng Việt; gọi lại `/process` → 202, chạy lại được (retry OK)
- [x] Token sai/không có → 401; file id lạ → 404
- [x] RLS thật: `user_files` có 3 dòng nhưng anon key đọc ra 0; `lessons` cũng 0

> **Lưu ý cho #1b (phát hiện từ dữ liệu thật):** tài liệu Word tiếng Việt thường **không gán heading
> style** — file mẫu có 110/114 đoạn là `Normal`, chỉ 4 đoạn `Heading 2`. Hệ quả: 19k ký tự đầu
> không có cấu trúc nào máy đọc được, bị cắt cứng thành 3 cục "Mở đầu (1)(2)(3)". Extractor xử lý
> đúng, nhưng **pha duyệt chương ở #1b gánh rất nặng**. Cân nhắc heuristic nhận diện tiêu đề đánh
> số (`Chương N`, `1.1`) trong đoạn `Normal`.

### #1b — UI upload + duyệt chương — ✅ XONG (2026-07-20, merge `0240aff`)
Spec: `docs/superpowers/specs/2026-07-19-upload-review-ui-design.md`
Plan: `docs/superpowers/plans/2026-07-19-upload-review-ui.md`
- [x] Trang upload (presign → PUT thẳng R2 → process → poll trạng thái)
- [x] Trang duyệt chương: sửa tên / gộp / bỏ → `POST /api/files/{id}/confirm` → ghi `lessons`
- [x] Nút "Xử lý lại" cho file `error`, và cho file kẹt `processing` quá 10 phút

**Verify thật (qua HTTP thật, R2 thật, Supabase thật — `backend/scripts/verify_1b.py`):**
- [x] **PUT presigned kiểu browser** (không tự set `Content-Length`, có `Content-Type` trình duyệt
      suy ra) → **200**. Đây là rủi ro lớn nhất vì `ContentLength` được ký vào URL — nếu sai thì
      mọi upload hỏng ở production mà không test nào bắt được
- [x] `.docx` 6.1MB thật → `ready_for_review`, **9 chương**; heuristic #1b nhận đúng `CHƯƠNG 1..4`
      và `4.2`/`5.1`/`5.2`/`5.3` trong đoạn `Normal` (trước heuristic, #1a chỉ ra 7 chương và
      19k ký tự đầu là 3 cục "Mở đầu")
- [x] `.pdf` 30 trang → 4 chương
- [x] Confirm gộp `[0,1]` + bỏ chương 2 + đổi tên → `lessons` đúng số dòng, nội dung gộp đúng thứ
      tự, chương đã bỏ vắng mặt, `order_index` liên tục từ 0
- [x] **Gộp không liền kề `[0,2]`** (quy tắc vừa nới) → 200, nối đúng, chương 1 vắng mặt
- [x] File hỏng → `error` + "Không mở được file .docx…"; gọi lại `/process` → **202** (retry được);
      `/confirm` trên file `error` → 409
- [x] `/confirm` và `/process` trên file `done` → 409 "File đã được duyệt."
- [x] `GET /api/files` không còn lộ `storage_path`/`user_id`
- [x] RLS thật: `lessons` có 7 dòng, anon key đọc ra **0**; `user_files` cũng 0
- [x] `uploaded_at` trả về kèm offset `+00:00` → `new Date()` parse đúng, ngưỡng "kẹt 10 phút" an toàn
- [x] Dọn sạch: 6 file + 10 lesson tạo lúc verify đã xoá khỏi DB và R2; giữ nguyên 2 mẫu của #1a

**Còn lại — chỉ trình duyệt mới kiểm được (chưa làm):** trạng thái tự nhảy `pending → processing →
`ready_for_review` không cần F5; poll dừng khi tab ẩn; thao tác gộp/bỏ/hoàn tác trên UI thật.
Backend và hợp đồng API đã verify hết; phần còn lại là hành vi React.

### #3 — Lessons UI — ✅ XONG (2026-07-21, nhánh `feature/lessons-ui`)
Spec: `docs/superpowers/specs/2026-07-20-lessons-ui-design.md`
- [x] `app/routers/lessons.py`: `GET /api/lessons` (danh sách phẳng, sắp theo
      `(source_file_name, order_index)`, `done` ghép từ `lesson_progress`), `GET
      /api/lessons/{slug}` (tra theo `(user_id, slug)`, kèm `prev`/`next` trong cùng
      `source_file_id`), `PUT /api/lessons/{id}/progress` (upsert `lesson_progress`
      theo `(user_id, lesson_id)`) — theo đúng khuôn `_Repo` của `files.py`, mọi truy
      vấn lọc `user_id` tường minh, bài của người khác → 404 (không 403)
- [x] Trang `/lessons`: gom bài theo `source_file_id` (nhóm mồ côi → "Khác", xếp
      cuối), tiến độ `x/y`, bộ lọc Tất cả/Chưa học/Đã học lọc phía client
- [x] Trang `/lessons/:slug`: render `content_md` bằng `react-markdown` +
      `remark-gfm` trong `<article class="prose">`, checkbox "Đã học" cập nhật lạc
      quan, điều hướng chương trước/sau (ẩn ở đầu/cuối file)
- [x] **D20** — nhóm theo file nguồn (`source_file_id`) chứ không theo `topic`/`week`
      vì hai cột đó luôn NULL (`_build_lesson_rows` không ghi); không cần migration
- [x] **D21** — dữ liệu đi qua backend (`routers/lessons.py`), không đọc thẳng
      Supabase bằng anon key, để #4a/#5/#6 mở rộng cùng một router
- [x] **D22** — backend trả mảng phẳng, gom nhóm là việc của frontend
- [x] **D23** — `react-markdown` giữ mặc định không render HTML thô (không
      `rehype-raw`); thêm `remark-gfm` + `@tailwindcss/typography` (khai báo qua
      `@plugin` vì dự án dùng Tailwind v4)
- [x] `backend` pytest 173/173 xanh, output sạch (gồm `test_lessons_api.py`,
      `test_lessons_repo.py`)
- Deps mới: `react-markdown`, `remark-gfm`, `@tailwindcss/typography` (frontend);
      không thêm dependency backend

**Verify thật (2026-07-21, `backend/scripts/verify_3.py` — HTTP thật + Supabase thật, session
mint trong tiến trình):**
- [x] `GET /api/lessons` → 5 bài thật, cả 5 gom đúng dưới một file nguồn
      (`FC36_BaoCao_DoAn - DHMT.docx`), `done=False`
- [x] `GET /api/lessons/{slug}` chương đầu → 19370 ký tự, `content_md` **khớp đúng dòng DB** (so
      trực tiếp với `/rest/v1/lessons`, không để bug tự khớp với chính nó), `prev=None`,
      `next` trỏ đúng chương `#1`
- [x] `PUT` progress `done=true` → `{done:true, completed_at:'2026-07-21T02:46:11+00:00'}`;
      `done=false` → `{done:false, completed_at:null}`
- [x] **RLS thật:** anon key đọc `lesson_progress` ra **0 dòng**
- [x] Dọn sạch: dòng `lesson_progress` script tạo đã xoá, tài khoản về nguyên trạng

**Kiểm trình duyệt (2026-07-21, thủ công):** render markdown bài `.docx` đã cắt, ba bộ lọc đổi danh
sách, cập nhật lạc quan của checkbox (bền qua F5) và điều hướng prev/next — tất cả OK. Backend và hợp
đồng API đã verify tự động.

> **Nợ nhỏ (không chặn):** `verify_3.py` in tiêu đề chương tiếng Việt ra stdout, nên trên console
> Windows (cp1252) phải chạy kèm `PYTHONIOENCODING=utf-8`; và script cần `SUPABASE_ANON_KEY` trong
> môi trường (backend/.env chỉ có service-role — anon key nằm ở `frontend/.env.local`).

### #4a — Sinh câu hỏi bằng AI (MỚI, thay cho parse callout — D13) — ✅ XONG (2026-07-21, nhánh `feature/ai-question-generation`)

- [x] Migration `0007`: thêm `questions.user_id` + RLS `auth.uid() = user_id`
      (bảng đang là dùng chung, không có `user_id`)
- [x] Đổi vai trò `backend/app/config/callout_types.py`: từ whitelist parser → enum ép AI chọn
      khi sinh câu hỏi (structured output). Cột `type` + CHECK constraint giữ nguyên.
- [x] Sinh câu hỏi **riêng từng user** khi user mở bài, context = nguyên `lessons.content_md`
      (KHÔNG dùng RAG — bài học đủ nhỏ để nhét cả vào prompt)
- [x] Model chat: **`gemini-3.5-flash`** (đổi từ `gemini-2.5-flash` khi verify — xem dưới)
- [x] `app/ai/` (client + `generate_questions` structured output, graceful degradation → 502),
      2 endpoint trong `routers/lessons.py` (`GET /{slug}/questions` cache-or-generate,
      `POST /{slug}/questions/regenerate`), section read-only `ReviewQuestions` ở trang bài học
- [x] `backend` pytest 195/195 xanh, output sạch · frontend `npm run build` sạch

**Verify thật (2026-07-21, `backend/scripts/verify_4a.py` — HTTP thật + Gemini thật + Supabase thật,
session mint trong tiến trình, chạy trên bài `.docx` thật của tài khoản ADMIN):**
- [x] `GET /{slug}/questions` (cache miss) → **5 câu, phủ đủ 4 loại** (recall/explain/compare/scenario),
      tiếng Việt, bám sát nội dung bài
- [x] `GET` lần 2 → **cùng id** (cache hit, không sinh lại, không thêm dòng DB); DB có đúng 5 dòng
- [x] `POST /{slug}/questions/regenerate` → 5 câu mới (id khác)
- [x] **RLS thật:** anon key đọc `questions` ra **0 dòng**
- [x] Dọn sạch: các dòng `questions` script tạo đã xoá, tài khoản về nguyên trạng

> **Đổi model khi verify (2026-07-21):** `gemini-2.5-flash` trả `404 NOT_FOUND — no longer available
> to new users` với API key mới (free tier). Đã test thật nhiều model rồi chốt **`gemini-3.5-flash`**
> (chạy được + structured output OK trên chính key này). `response_schema` dạng dict được google-genai
> chấp nhận — xác nhận qua lần chạy thật.
>
> **Sửa DB phát hiện khi verify:** bảng `questions` có sẵn constraint cũ `questions_lesson_order_unique
> (lesson_id, order_index)` từ thời câu hỏi dùng chung — **không nằm trong migration nào**, chỉ có
> trong DB thật. Nó chặn người thứ hai sinh câu hỏi cho cùng một bài. Đã thêm `drop constraint if
> exists` vào `0007` và apply.


### #4 — AI chấm điểm — ✅ XONG (2026-07-21)

- [x] `POST /api/quiz/grade` — structured output Pydantic `{ score, missing_points[], comment }`,
      lưu `quiz_attempts` (id/created_at mint ở backend), tăng `daily_activity` **mỗi câu 1 lần/ngày**
- [x] `GET /api/quiz/attempts/{slug}` — attempt mới nhất mỗi câu (mở lại bài vẫn thấy điểm)
- [x] `app/ai/grading.py` (`grade_answer`, structured output, clamp score [0,10], graceful degradation
      → 502) + frontend: ô trả lời + "Nộp bài" + điểm/nhận xét/ý thiếu inline ở `ReviewQuestions`
- [x] Model chat: **`gemini-3.5-flash`** · `google-genai` client dùng chung `app/ai/client.py`
- [x] `backend` pytest 219/219 xanh, output sạch (test_grading/test_quiz_api/test_quiz_repo) ·
      frontend `npm run build` + `oxlint` sạch · **không cần migration** (bảng + RLS đã có)

**Verify thật (2026-07-21, `backend/scripts/verify_4.py` — HTTP thật + Gemini thật + Supabase thật,
session mint trong tiến trình, trên câu hỏi thật của #4a):**
- [x] `POST grade` → điểm hợp lệ 0–10 + `missing_points` (ý thật rút từ bài) + `comment` tiếng Việt
      (câu trả lời thử nghiệm bị chấm **0.0** kèm ý còn thiếu — AI chấm đúng chất lượng)
- [x] `daily_activity` hôm nay **0 → 1** ở lần chấm đầu; nộp lại **cùng câu** trong ngày → **giữ 1**
      (đếm mỗi câu 1 lần/ngày hoạt động đúng)
- [x] `GET attempts/{slug}` → trả **bản mới nhất** ("Nộp lại lần hai.")
- [x] **RLS thật:** anon key đọc `quiz_attempts` và `daily_activity` đều ra **0 dòng**
- [x] Dọn sạch: các dòng script tạo đã xoá, `daily_activity` hôm nay khôi phục nguyên trạng

**Kiểm trình duyệt (chưa làm — chỉ React behavior):** nộp bài trên UI thật, F5 vẫn thấy điểm, "Làm lại".
Backend + hợp đồng API đã verify tự động.

### #5 — Socratic Chatbot — ✅ XONG (2026-07-21, nhánh `feature/socratic-chatbot`)
Spec: `docs/superpowers/specs/2026-07-21-socratic-chatbot-design.md`
Plan: `docs/superpowers/plans/2026-07-21-socratic-chatbot.md`
- [x] Migration `0008`: unique index `(user_id, lesson_id)` trên `chat_sessions` — cưỡng chế "một
      cuộc bền vững / (user, bài)", load-or-create không tạo hai dòng khi hai request đua nhau
- [x] `app/ai/chat.py`: `stream_socratic_reply` (Gemini `generate_content_stream`, model
      `gemini-3.1-flash-lite`), **system prompt Socratic thuần** — không đưa đáp án thẳng, chỉ gợi mở
      bằng câu hỏi; graceful degradation → `ChatError` (tiếng Việt)
- [x] `POST /api/chat/{lesson_id}` — `StreamingResponse` (`text/plain`); lưu tin user **trước** khi
      stream (không mất nếu lỗi), append tin trợ giảng sau khi stream xong; lỗi up-front → 502, lỗi
      giữa chừng → dừng êm nhưng vẫn lưu phần đã nhận. `GET` trả lịch sử, `DELETE` xóa hội thoại
- [x] Lưu `chat_sessions.messages` (mảng `{role, content}`), một dòng / (user, bài); `updated_at`
      đóng dấu bằng ISO timestamp (không dùng chuỗi `"now()"`)
- [x] Frontend: `apiStream` (đọc body stream, khác `apiFetch` luôn `.json()`) + `lib/chat.ts`;
      `ChatPanel.tsx` **panel trượt từ phải** (D-chat-2, giữ cột đọc `max-w-3xl`), nút "Hỏi đáp
      Socratic" trên trang bài, stream token, nút "Xóa hội thoại", reply render markdown (không rehype-raw)
- [x] `backend` pytest 236/236 xanh, output sạch (`test_chat.py`, `test_chat_api.py`) · frontend
      `npm run build` + `oxlint` sạch
- **D-chat-1** Socratic thuần · **D-chat-2** panel trượt phải · **D-chat-3** một cuộc bền vững + nút xóa

**Verify thật (2026-07-21, `backend/scripts/verify_5.py` — HTTP thật + Gemini thật + Supabase thật,
session mint trong tiến trình, trên bài `.docx` thật của tài khoản admin):**
- [x] `POST /api/chat/{lesson_id}` → reply **stream 301 ký tự, tiếng Việt, kiểu Socratic** (hỏi lại
      "theo bạn, tại sao DevOps lại tin…" thay vì giải đáp)
- [x] `GET` sau 1 lượt → đúng 2 message (user + assistant); sau lượt 2 → 4 message (ngữ cảnh được nối)
- [x] `DELETE` → `GET` trả `messages: []`
- [x] **RLS thật:** anon key đọc `chat_sessions` → **0 dòng**
- [x] Dọn sạch: dòng `chat_sessions` script tạo đã xoá, tài khoản về nguyên trạng

**Kiểm trình duyệt (chưa làm — chỉ React behavior):** panel trượt ra/đóng, stream hiển thị dần, F5 mở
lại panel thấy lịch sử, "Xóa hội thoại", điều hướng prev/next reset đúng hội thoại. Backend + hợp đồng
API đã verify tự động.

### #6 — Dashboard — ✅ XONG (2026-07-22, nhánh `feature/dashboard`)
Spec: `docs/superpowers/specs/2026-07-22-dashboard-design.md`
Plan: `docs/superpowers/plans/2026-07-22-dashboard.md`
- [x] Streak (từ `daily_activity`) + BarChart câu hỏi **7 ngày gần nhất** (mỗi ngày 1 cột, zero-fill)
- [x] % hoàn thành bài học (`lesson_progress` done / tổng `lessons` của user)
- [x] Leaderboard xếp theo **số ngày học** (`count(distinct daily_activity.activity_date)`),
      không xếp theo điểm — migration `0009` thêm `active_days` cho `leaderboard_view` **và sửa
      lỗi fan-out** của `0004` (join hai bảng riêng tư trong một truy vấn làm `sum(questions_done_count)`
      bị nhân theo số bài done). Xếp theo **giờ học** vẫn hoãn (D15). Xem D-dash-1/D-dash-4.
- [x] Thay Home placeholder bằng `Dashboard.tsx` thật, **logout tử tế** (bắt lỗi `signOut()`, không nuốt)
- [x] `app/routers/dashboard.py`: `GET /api/dashboard/me` (streak hiện tại + dài nhất, weekly 7
      ngày, completion; lọc `user_id` tường minh) và `GET /api/dashboard/leaderboard` (đọc
      `leaderboard_view`, gắn `is_me`) — theo khuôn `_Repo` của `quiz.py`
- [x] **D-dash-2** Recharts (không Tremor — Tailwind v4 + React 19); dep mới `recharts`
- [x] **D-dash-5** Mốc ngày = **giờ VN (UTC+7)** qua helper chung `app/util/dates.py`
      (`vn_today`/`vn_date_of`); `quiz.py` (#4) đổi bucket `daily_activity` từ UTC sang ngày VN.
      Streak reset khi qua 0h VN mà chưa học. `created_at` vẫn lưu UTC.
- [x] Dọn nợ kèm theo: `Home.handleSignOut` nuốt lỗi → đã sửa ở `Dashboard.tsx` (nợ kỹ thuật cũ)
- [x] `backend` pytest 256/256 xanh, output sạch (`test_dates`, `test_dashboard_stats`,
      `test_dashboard_api`, `test_dashboard_repo`) · frontend `npm run build` + `oxlint` sạch

**Verify thật (2026-07-22, `backend/scripts/verify_6.py` — HTTP thật + Supabase thật, session mint
trong tiến trình, seed 1 dòng `daily_activity` ngày VN rồi khôi phục nguyên trạng):**
- [x] `GET /api/dashboard/me` → `current_streak=1`, `longest_streak=1`, `weekly_questions` **đúng 7
      ngày** cột cuối = hôm nay = 3, `completion_pct=9` (1/11 bài)
- [x] `GET /api/dashboard/leaderboard` → 1 dòng, `is_me=true`, `active_days=1`
- [x] Dọn sạch: dòng `daily_activity` seed đã xoá, tài khoản về nguyên trạng

**Kiểm trình duyệt (chưa làm — chỉ React behavior):** render 3 thẻ + BarChart 7 cột + bảng xếp hạng
tô đậm dòng mình, nav + đăng xuất, F5 giữ trang. Backend + hợp đồng API đã verify tự động.

### #7 — `/admin/invite` — ✅ XONG (2026-07-22, nhánh `feature/admin-invite`)
Spec: `docs/superpowers/specs/2026-07-22-admin-invite-design.md`
Plan: `docs/superpowers/plans/2026-07-22-admin-invite.md`
- [x] Cổng admin: `settings.admin_email()` + dependency `require_admin` (so email JWT với
      `ADMIN_EMAIL`, **không phân biệt hoa/thường**) — ranh giới bảo mật thật, mọi route
      `/api/admin/*` phụ thuộc nó (non-admin → 403, thiếu token → 401). **Không tin frontend.**
- [x] `GET /api/me` thêm cờ `is_admin` → frontend gác UI admin mà `ADMIN_EMAIL` **không lộ ra browser**
- [x] `app/admin/members.py`: gọi Supabase Admin API — `invite_member` (payload y hệt
      `scripts/invite_user.py`: `email_confirm:true` + `user_metadata.password_set:false`, **không
      gửi email mời**), `list_members`, `find_member`; `AlreadyMemberError`/`InviteError`; `_summarize`
      chỉ trả `{email, password_set, created_at}` (không lộ id/token)
- [x] `app/routers/admin.py`: `POST /api/admin/invite` (422 email sai / 409 trùng / 502 upstream /
      201 kèm member) + `GET /api/admin/members` (502 khi Admin API lỗi) — router mỏng, đều
      `Depends(require_admin)`
- [x] Trang `/admin/invite` (`AdminInvite.tsx`): gác `is_admin` từ `/api/me` → non-admin **redirect
      `/` trước khi fetch/hiện member nào**; danh sách thành viên (email + "Đã/Chưa đặt mật khẩu") +
      form mời (cập nhật lạc quan, dedupe theo email, lỗi tiếng Việt). Nút "Mời thành viên" trên
      Dashboard **chỉ hiện với admin** (mặc định ẩn, không nhấp nháy)
- [x] **Không cần migration** — chỉ thao tác trên Supabase Auth users, không đụng bảng ứng dụng
- [x] `backend` pytest **278/278 xanh**, output sạch (`test_admin_members`, `test_admin_api`,
      `test_me_api`, + `require_admin` trong `test_auth`) · frontend `npm run build` + `oxlint` sạch
      (chỉ còn cảnh báo `button.tsx` fast-refresh có sẵn, không liên quan)

**Verify thật (2026-07-22, `backend/scripts/verify_7.py` — HTTP thật + Supabase Auth thật, session
admin mint trong tiến trình):**
- [x] `POST /api/admin/invite` email dùng-một-lần → **201**, `password_set:false`; Admin API xác nhận
      user tồn tại với `user_metadata.password_set == false`
- [x] Mời lại cùng email → **409**
- [x] `GET /api/admin/members` → có email vừa mời
- [x] Non-admin → **403** (pytest `test_admin_api.py`; mint session non-admin thật cần tài khoản thứ
      hai đã đặt mật khẩu nên để pytest gánh)
- [x] Dọn sạch: xoá user dùng-một-lần qua Admin API, tổng user về **1** (nguyên trạng)

**Kiểm trình duyệt (chưa làm — chỉ React behavior):** nút admin ẩn/hiện đúng vai, mời trên UI thật,
redirect non-admin. Backend + hợp đồng API đã verify tự động.

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
- [x] ~~`frontend/src/pages/Home.tsx`: `handleSignOut` nuốt lỗi `signOut()`~~ — đã xử lý ở #6:
      `Home.tsx` bị thay bằng `Dashboard.tsx`, logout nay bắt lỗi và báo tiếng Việt.
- [ ] `backend/pytest.ini` đang suppress `StarletteDeprecationWarning` (dep transitive) — xem lại khi
      nâng dependency.
- [ ] `lucide-react` chưa được import ở đâu (giữ lại vì Shadcn sẽ cần khi thêm component ở #3).

Từ review #1a (đã triage, không chặn gì):
- [ ] `settings.ALLOWED_FILE_TYPES` **không có chỗ nào trong production dùng** — danh sách định dạng
      đang tồn tại 3 bản (Literal ở `files.py`, CHECK trong DB, biến này). Xoá hoặc derive Literal từ nó.
- [ ] `md.py` parse `title`/`topic` trong frontmatter rồi vứt đi (spec §5.1 có yêu cầu) — file `.md`
      không heading sẽ lấy tên file làm tiêu đề chương thay vì title trong frontmatter.
- [ ] Deck chỉ có tiêu đề slide (không body) báo "không trích xuất được nội dung" — thông báo sai
      nguyên nhân, thực ra extractor có lấy được tiêu đề.
- [ ] `_FakeTable` bị lặp giữa `test_files_api.py` và `test_pipeline.py` — gom vào `conftest.py` khi
      có file thứ ba cần.

Từ review #1b (đã triage, không chặn gì):
- [ ] `apiFetch` trả `Promise<any>`, nên mọi wrapper có kiểu trong `frontend/src/lib/files.ts` chỉ là
      ép kiểu không được kiểm chứng — backend đổi field sẽ compile qua mà không báo lỗi.
- [ ] PUT lên R2 lỗi sẽ để lại một dòng `pending` mồ côi; chưa có endpoint xoá.
- [ ] `refresh()` trong `Files.tsx` không có cơ chế chặn các lần gọi chồng nhau, nên fetch chồng chéo
      có thể thoáng hiện dữ liệu cũ.
- [x] ~~Lỗi tầng mạng lọt ra nguyên văn tiếng Anh `Failed to fetch`~~ — đã bọc try/catch ở `apiFetch`
      và ở bước PUT lên R2, giờ báo tiếng Việt. (Phát hiện khi chạy thật: quên bật backend.)
- [ ] Ngưỡng 10 phút kẹt `processing` tính từ `uploaded_at` vì chưa có cột đánh dấu thời điểm bắt đầu xử lý.
- [ ] Độ dài slug có thể vượt quá 80 ký tự đã tài liệu hoá một khi nối thêm `-{order_index}` và hậu tố
      `-N` (vô hại: cột DB là `text` không giới hạn).

Từ review #5 (đã triage, không chặn merge — bối cảnh < 10 người, mỗi bài một user):
- [ ] **Lost-update** khi hai POST `/api/chat/{lesson_id}` cùng bài chạy song song: mỗi request ghi đè
      cả mảng `messages` theo `history` đọc lúc vào → lượt của request kết thúc sau nuốt lượt kia. Cần
      atomic append hoặc advisory lock theo session (frontend `sending` guard đã chặn trong một panel).
- [ ] Stream Gemini rỗng (0 chunk) để lại tin user mồ côi không có phản hồi → lượt sau `contents` thành
      `[user, user]`. Xác suất thấp; nhánh này chưa có test. Cân nhắc lưu tin trợ giảng fallback hoặc
      hoàn tác tin user khi reply rỗng.
- [ ] `ChatPanel` khi đóng: các control con (textarea/nút) vẫn focus được (mới chỉ `aria-hidden`) — dùng
      `inert` trên `<aside>` khi `!open` để chặn cả focus lẫn ARIA.
- [ ] Nút "Xóa hội thoại" không `disabled` khi đang stream (bị chặn bằng early-return trong `reset()`,
      nên bấm giữa chừng là no-op thầm lặng) — thêm `disabled={sending}` cho đúng affordance.

## Việc cần user (blocker)

- [x] Key Supabase (URL/anon/service-role), Gemini, GitHub webhook secret, `ADMIN_EMAIL` — đã có
      (lưu ý: `GEMINI_API_KEY` phải nằm trong `backend/.env` — thiếu ở đó thì generate sẽ 502)
- [x] Supabase Site URL = `http://localhost:5173` cho dev — đã đổi
- [x] Không cần `SUPABASE_JWT_SECRET` nữa (verify bằng JWKS)
- [x] Model AI Gemini (chat) đã chốt: **`gemini-3.5-flash`** (2026-07-21; `gemini-2.5-flash` bị Google
      khóa với key mới). Embedding vẫn hoãn cùng RAG.
- [x] **R2 keys** (`R2_ACCOUNT_ID`, access key, secret, bucket) — đã có và đã verify ghi được lên
      bucket `binh` thật (token ban đầu chỉ có quyền đọc, đã đổi sang Object Read & Write)
- Không cần `GITHUB_WEBHOOK_SECRET` nữa (D17 bỏ Obsidian sync)
- (HOÃN cùng RAG) embedding model
