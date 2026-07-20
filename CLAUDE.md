# CLAUDE.md — Personal LMS

Hướng dẫn cho Claude khi làm việc trên codebase này. Đọc file này + `project_context.md` +
`architecture.md` + `check_list.md` trước khi code.

## Dự án là gì

Personal LMS (Learning Management System) cho nhóm nhỏ **< 10 người** (invite-only, không public).
**Mỗi user tự upload tài liệu của mình** (`.md`/`.docx`/`.pptx`/`.pdf`) → hệ thống extract sang
markdown, cắt thành chương, user duyệt → thành bài học riêng tư của người đó. AI sinh câu hỏi từ
nội dung bài, chấm điểm + phản biện (Socratic). Cả nhóm chung một bảng xếp hạng chuyên cần.

> **Lưu ý khi đọc tài liệu cũ**: Obsidian Vault → GitHub → `/api/sync` **đã bỏ hẳn** (D17), câu hỏi
> **không** parse từ callout `> [!type]` nữa mà do AI sinh (D13). Xem D13–D19 trong
> `project_context.md`.

## Nguyên tắc thiết kế (BẤT BIẾN)

1. **Đơn giản, chi phí $0** — dùng free tier. Chỉ thêm phức tạp khi thực sự cần.
2. **Cách ly dữ liệu nghiêm ngặt** — mọi dữ liệu riêng tư (câu trả lời, điểm, chat, tài liệu) phải
   được bảo vệ bằng Row Level Security (RLS) theo `auth.uid() = user_id`.
3. **Ngôn ngữ**: nội dung hiển thị cho user = **tiếng Việt**; code, tên bảng/cột/biến, comment kỹ
   thuật, commit = **tiếng Anh**.
4. **Graceful degradation** — một file/tác vụ AI lỗi KHÔNG được làm sập cả pipeline. Luôn try/catch,
   cập nhật trạng thái lỗi, cho phép retry. Không nuốt lỗi âm thầm.
5. **Không dùng NoSQL** — mọi thứ (kể cả vector, dữ liệu bán cấu trúc) lưu trong Postgres
   (`jsonb` + `pgvector`).

## Tech stack (CHỐT CỨNG — không đổi)

| Lớp | Công nghệ |
|---|---|
| Frontend | React + **Vite** + React Router (SPA thuần, không SSR), TypeScript |
| UI | Tailwind CSS, Shadcn UI |
| Charts | Tremor (ưu tiên) / Recharts |
| Backend | **Python + FastAPI**, đóng gói Docker |
| Database | Supabase (Postgres) + extension `pgvector` |
| File storage | Cloudflare R2 (S3-compatible qua `boto3`) — **KHÔNG dùng Supabase Storage** |
| Auth | Supabase Auth — Magic Link (email OTP), invite-only |
| AI | Google Gemini qua Python SDK `google-genai` |
| Ingest | User upload file → R2 (presigned) → extract → cắt chương → `lessons` |
| Hosting | Frontend: Vercel (static build) · Backend: Koyeb (Docker) |

> **Model IDs (chat + embedding) — TẠM HOÃN.** Sẽ chốt khi build feature AI. Xem `check_list.md`.

## Cấu trúc thư mục

Một repo, hai nửa tách biệt, giao tiếp qua REST API.

```
frontend/                   # React SPA (Vite)
  src/
    main.tsx  App.tsx       # entry + router
    lib/      supabase.ts   # browser client (anon key, RLS)
              api.ts        # apiFetch() — tự gắn Authorization: Bearer
              utils.ts      # cn()
    components/ ui/         # Shadcn components
                ProtectedRoute.tsx
    pages/                  # Login, AuthCallback, Home (sau: Lessons, Dashboard...)
  .env.example              # VITE_*
backend/                    # FastAPI
  app/
    main.py                 # FastAPI app + CORSMiddleware + include_router
    dependencies/auth.py    # get_current_user() — verify Supabase JWT
    routers/                # health.py, me.py (sau: files, quiz, chat, admin)
    ingest/                 # (sau) extractors/{md,docx,pptx,pdf}.py + splitter.py
    config/callout_types.py # QUESTION_TYPES — enum ép AI chọn khi sinh câu hỏi
  tests/                    # pytest
  requirements.txt  Dockerfile  .env.example
supabase/migrations/        # SQL migrations (nguồn chân lý của schema)
docker-compose.yml          # local dev (tuỳ chọn — xem "Chạy local")
```

## Quy ước code

**Frontend**
- Import alias `@` → `frontend/src` (cấu hình ở `vite.config.ts` + cả hai `tsconfig`).
- Mọi request tới backend đi qua `apiFetch()` trong `lib/api.ts` — không tự `fetch` rồi gắn token tay.
- Chuỗi hiển thị cho user viết **tiếng Việt**; comment/tên biến **tiếng Anh**.

**Backend**
- Router mỏng, logic nằm ở module riêng (parser/, ai/, rag/ khi làm tới).
- Mọi route riêng tư dùng `Depends(get_current_user)`. Backend **không tự quản session** — chỉ verify
  JWT do Supabase phát.
- `callout_types.py` là nguồn duy nhất định nghĩa loại câu hỏi — prompt sinh câu hỏi và DB CHECK
  constraint phải đồng bộ với nó.
- `ingest/`: extractor (phụ thuộc định dạng) tách khỏi splitter (chỉ ăn markdown) — thêm định dạng
  mới chỉ phải viết một hàm `extract(bytes) -> str`.

**Chung**
- Tất cả secret qua biến môi trường. KHÔNG hardcode key. Chỉ commit `.env.example`.
- `SUPABASE_SERVICE_ROLE_KEY` chỉ dùng ở backend (bypass RLS) — không bao giờ lộ ra frontend.
- Frontend chỉ dùng **anon key** (bị RLS ràng buộc).

## Auth (đã chạy thật)

- Hai cách đăng nhập, cùng một tài khoản:
  - **Mật khẩu** (`signInWithPassword`) — đường chính, vào thẳng không cần mở mail.
  - **Magic Link / mã OTP** (`signInWithOtp` → `verifyOtp`) — đường lui khi quên mật khẩu, và là
    lối vào duy nhất cho thành viên chưa được đặt mật khẩu. Mail mang **cả link và mã 8 số**;
    nhập mã sẽ đăng nhập **chính thiết bị đang gõ**, nên mở mail trên điện thoại vẫn vào được ở
    máy tính. Bấm link chỉ tạo phiên trên đúng thiết bị bấm — không thể "reload" máy còn lại để
    nhận phiên hộ.
- **Email template trong Supabase phải chứa `{{ .Token }}`**, nếu không mail chỉ có link và ô nhập
  mã trở nên vô dụng. Dashboard → Authentication → Email Templates → Magic Link.
- **Invite-only** cưỡng chế bằng `shouldCreateUser: false` ở luồng OTP; luồng mật khẩu **không bao
  giờ gọi `signUp`**, nên cũng không tạo được user mới. Thêm thành viên = mời qua Supabase.
- **Thêm thành viên**: `python backend/scripts/invite_user.py <email>` — tạo tài khoản **không đặt
  mật khẩu**, gắn `user_metadata.password_set = false`. Người đó vào trang đăng nhập → "Chưa có
  mật khẩu? Gửi mã qua email" → nhập mã → **buộc đặt mật khẩu** rồi mới vào được.
- **Quên mật khẩu**: "Quên mật khẩu? Đặt lại bằng mã qua email" → nhập mã → đặt mật khẩu mới. Cùng
  một luồng OTP, khác nhau ở `otpPurpose`: `reset` luôn dừng ở màn đặt mật khẩu, `login` chỉ dừng
  khi `password_set` chưa true.
- `user_metadata.password_set` là cờ quyết định có ép đặt mật khẩu hay không. **Cờ này chỉ gác
  luồng OTP** — ai đã biết mật khẩu vẫn đăng nhập thẳng được, kể cả khi cờ chưa bật.
- Đặt hộ mật khẩu (ít dùng): `python backend/scripts/set_password.py <email>` — cũng bật cờ, để
  người đó không bị hỏi lại. Script từ chối nếu email chưa được mời.
- Thông báo lỗi khi sai mật khẩu và khi email không tồn tại **giống hệt nhau** ("Email hoặc mật khẩu
  không đúng.") — Supabase trả cùng một `invalid_credentials` cho cả hai, đừng tách ra thành hai
  thông báo khác nhau vì như vậy là để lộ ai đang là thành viên.
- Bảo vệ route ở frontend bằng component `ProtectedRoute` (SPA không có middleware SSR).
- Backend verify JWT qua **JWKS / ES256** (project này ký bất đối xứng), lấy từ
  `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`. **Không cần shared JWT secret.**
- Local dev: Supabase **Site URL phải là `http://localhost:5173`** thì magic link mới redirect đúng.

## Chạy local

```bash
# Backend — dùng venv, KHÔNG dùng Docker cho dev (RAG sau này cần venv)
cd backend
python -m venv .venv && .venv/Scripts/Activate.ps1   # Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000

# Frontend
cd frontend && npm install && npm run dev            # http://localhost:5173
```

`docker-compose.yml` có sẵn nếu muốn chạy cả hai bằng container, nhưng dev thường ngày dùng venv +
`npm run dev` cho nhẹ.

## Verify sau mỗi thay đổi

- Backend: `pytest` từ `backend/` — phải xanh và **output sạch** (không warning).
- Frontend: `npm run build` từ `frontend/` — không lỗi TypeScript.
- Với thay đổi có runtime: **chạy thử luồng thật**, đừng chỉ dựa vào typecheck.
- SQL: đọc lại migration theo thứ tự, đảm bảo RLS bật cho mọi bảng riêng tư.

## Trạng thái hiện tại

**Sub-project #0 (Foundation + Auth) — XONG**, verify end-to-end thật và đã merge vào `main`.
Việc được chia thành các sub-project độc lập (#0–#8), mỗi cái có spec → plan → build riêng.
Xem `check_list.md` để biết đã/đang/sẽ làm gì.
