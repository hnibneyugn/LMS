# Design — Sub-project #0: Foundation + Auth (React Vite + FastAPI)

Ngày: 2026-07-18 · Trạng thái: chờ duyệt · Sub-project 0/8 của đợt đổi kiến trúc

## 1. Bối cảnh

Dự án đổi kiến trúc từ **Next.js fullstack** sang **React (Vite) SPA + FastAPI**, giữ nguyên 100%
hạ tầng dữ liệu đang chạy thật (Supabase: schema + RLS + data; Cloudflare R2). Vì codebase Next.js
mới ở Pass 1 (chỉ scaffold + schema, chưa có trang/API nào), đây **không phải migrate code** mà là
**build mới app layer** theo mega-prompt, trên Supabase + R2 sẵn có.

Việc lớn được chia thành các sub-project độc lập (mỗi cái có spec → plan → build riêng):

| # | Sub-project | # | Sub-project |
|---|---|---|---|
| **0** | **Foundation + Auth** (spec này) | 5 | Socratic chat (streaming) |
| 1 | Parser (Python thuần) | 6 | Dashboard |
| 2 | Sync (`/api/sync` + webhook) | 7 | Admin invite |
| 3 | Lessons UI | 8 | Deploy (Koyeb + Vercel) |
| 4 | AI chấm điểm | — | Documents + RAG (⏸️ hoãn — D8) |

Sub-project #0 là **walking skeleton**: dựng khung frontend + backend và cho một người **đã được mời**
đăng nhập Magic Link end-to-end, route được bảo vệ, **backend verify được JWT của họ**. Mọi
sub-project sau dựng trên khung này. Không có #0 thì không test được luồng thật của bất cứ tính năng
riêng tư nào (RLS cần `auth.uid()`).

## 2. Phạm vi

**Làm:**
- Restructure repo: 1 repo, 2 thư mục `frontend/` + `backend/`; gỡ scaffold Next.js; giữ
  `supabase/migrations/`, `docs/`, các doc gốc.
- Backend FastAPI skeleton: `main.py` (app + CORS), `dependencies/auth.py` (`get_current_user` verify
  JWT Supabase), `routers/health.py` (public), `routers/me.py` (protected). Dockerfile + requirements.
- Frontend Vite SPA skeleton: React Router + Tailwind + Shadcn UI + `@supabase/supabase-js`.
  Trang `Login`, `AuthCallback`, `Home` (protected placeholder); `ProtectedRoute`; `lib/api.ts`
  (fetch wrapper gắn Bearer token). Dockerfile.dev.
- `docker-compose.yml` (root) orchestrate cả hai cho local dev.
- Login Magic Link **invite-only** chạy thật + đăng xuất.

**Không làm (sub-project sau):**
- Chức năng mời / phân quyền → #7. Không thêm cột DB lúc này.
- `/dashboard` thật → #6. Sau đăng nhập tạm về `/` (Home placeholder).
- Parser, sync, AI, documents/RAG.
- Deploy production → #8 (spec này chỉ lo local dev chạy được).

## 3. Quyết định

Các quyết định auth từ spec Next.js cũ (`2026-07-17-auth-magic-link-design.md`) **được giữ nguyên**
vì chúng thuộc về Supabase Auth, không phụ thuộc framework:

| # | Quyết định | Lý do |
|---|---|---|
| A1 | `signInWithOtp({ shouldCreateUser: false })` | Cơ chế cưỡng chế invite-only. Mặc định Supabase tự tạo user cho email lạ = public sign-up (trái ràng buộc). `auth.users` chính là danh sách mời — không cần bảng allowlist. |
| A3 | Báo thẳng "email chưa được mời" | Nhóm <10 người quen; UX rõ ràng quan trọng hơn rủi ro dò email. |
| A5 | Admin bootstrap thủ công qua Supabase Dashboard | Chưa có UI mời (#7). Không ai vào được nếu chưa có trong `auth.users`, kể cả admin. |

Quyết định mới cho kiến trúc SPA + FastAPI:

| # | Quyết định | Lý do |
|---|---|---|
| B1 | Bảo vệ route bằng `ProtectedRoute` component (client-side), thay middleware SSR | SPA không có server middleware. Component check `getSession()` + subscribe `onAuthStateChange`, chưa đăng nhập → `<Navigate to="/login">`. |
| B2 | Backend verify JWT bằng `SUPABASE_JWT_SECRET` (HS256, `pyjwt`), audience `authenticated` | Đúng với biến `SUPABASE_JWT_SECRET` trong mega-prompt §11. Verify cục bộ, không gọi mạng mỗi request. **Rủi ro:** nếu project bật asymmetric signing keys (ES256/RS256), phải đổi sang verify qua JWKS — kiểm chứng bằng token thật lúc build (mục 7), không tin mù giá trị ở đây. |
| B3 | 1 repo, `frontend/` + `backend/` + `supabase/` + `docs/`; `docker-compose.yml` ở root | Đơn giản cho nhóm nhỏ, giữ git history + migrations + docs. Vercel build từ `frontend/`, Koyeb build từ `backend/` (ở #8). |
| B4 | Frontend Docker chỉ cho local dev (`Dockerfile.dev`, Vite server + hot-reload); production = Vercel static | Production frontend không cần Docker; giữ $0. Backend `Dockerfile` dùng chung local + prod. |
| B5 | CORS whitelist origin cụ thể (`ALLOWED_ORIGINS`), không dùng `*` | Có Bearer token nhạy cảm; `*` không cho gửi kèm credentials/headers an toàn. |
| B6 | Home sau đăng nhập là placeholder có nút gọi thử `/api/me` | Bằng chứng luồng Bearer token xuyên suốt FE→BE chạy đúng ngay ở #0, không đợi tới feature. |

## 4. Cấu trúc repo sau restructure

**Giữ nguyên:** `supabase/migrations/`, `docs/`, `.gitignore`, `CLAUDE.md`, `check_list.md`,
`SETUP.md`, `README.md` (các doc sẽ cập nhật theo kiến trúc mới ở cuối đợt, không phải trong #0).

**Gỡ (Next.js-specific):** `app/`, `next.config.ts`, `next-env.d.ts`, `components.json`, `client/`,
`server/`, `package.json` + `package-lock.json` + `tsconfig.json` ở root.

**Port:** `server/config/callout-types.ts` → `backend/app/config/callout_types.py`;
`server/types/database.types.ts` → `frontend/src/lib/database.types.ts`.

```
backend/
  Dockerfile
  requirements.txt              # fastapi, uvicorn, pyjwt, python-dotenv, supabase (dùng ở # sau)
  .env.example
  app/
    __init__.py
    main.py                     # FastAPI(), CORSMiddleware, include_router(health, me)
    config/
      __init__.py
      callout_types.py          # QUESTION_TYPES = ["recall","scenario","compare","explain"]
    dependencies/
      __init__.py
      auth.py                   # get_current_user(): verify JWT -> CurrentUser(user_id, email)
    routers/
      __init__.py
      health.py                 # GET /api/health -> {"status":"ok"}  (public)
      me.py                     # GET /api/me -> {user_id, email}      (Depends get_current_user)
frontend/
  Dockerfile.dev
  package.json  vite.config.ts  tsconfig.json  index.html
  tailwind.config / postcss  + components.json (shadcn)
  .env.example
  src/
    main.tsx                    # createRoot + <BrowserRouter>
    App.tsx                     # <Routes>: /login, /auth/callback, /* (protected)
    lib/
      supabase.ts               # createClient(VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY)
      api.ts                    # apiFetch(): gắn Authorization: Bearer <session token>
      utils.ts                  # cn()
      database.types.ts         # (ported)
    components/
      ProtectedRoute.tsx
      ui/                       # shadcn: button, input, ... (shadcn add đổ vào đây)
    pages/
      Login.tsx
      AuthCallback.tsx
      Home.tsx                  # protected placeholder
docker-compose.yml              # services: frontend (5173), backend (8000)
supabase/migrations/            # (giữ nguyên)
docs/                           # (giữ nguyên)
```

## 5. Kiến trúc chi tiết

### 5.1 Backend

| File | Vai trò |
|---|---|
| `app/main.py` | Tạo `FastAPI()`; `CORSMiddleware` với `allow_origins=ALLOWED_ORIGINS.split(",")`, `allow_credentials=True`, `allow_headers=["*"]` (gồm Authorization), `allow_methods=["*"]`; `include_router` health + me. |
| `app/dependencies/auth.py` | `get_current_user(authorization: str = Header(...))`: tách `Bearer <token>`; `jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")`; trả `CurrentUser(user_id=payload["sub"], email=payload.get("email"))`. Thiếu header / sai / hết hạn → `HTTPException(401)`. Không nuốt lỗi âm thầm. |
| `app/routers/health.py` | `GET /api/health` → `{"status":"ok"}`. Public, cho keep-alive ở #8. |
| `app/routers/me.py` | `GET /api/me`, `Depends(get_current_user)` → trả `{user_id, email}`. |
| `Dockerfile` | `python:3.12-slim`, cài requirements, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`. |

### 5.2 Frontend

| File | Vai trò |
|---|---|
| `lib/supabase.ts` | Browser Supabase client (anon key, RLS). Nguồn session duy nhất. |
| `lib/api.ts` | `apiFetch(path, opts)`: lấy token từ `supabase.auth.getSession()`, thêm `Authorization: Bearer`, gọi `${VITE_API_BASE_URL}${path}`. Ném lỗi rõ ràng nếu chưa có session. |
| `App.tsx` | Router: `/login` → `Login`; `/auth/callback` → `AuthCallback`; còn lại bọc trong `ProtectedRoute` → `Home`. |
| `pages/Login.tsx` | Form email → `signInWithOtp({ email, options:{ shouldCreateUser:false, emailRedirectTo: \`${location.origin}/auth/callback\` }})`. 3 trạng thái: idle / đã gửi / lỗi. Map lỗi theo mục 6. Đã có session → `<Navigate to="/">`. |
| `pages/AuthCallback.tsx` | On mount: supabase-js `detectSessionInUrl` tự đổi code→session; chờ session sẵn sàng rồi `navigate("/")`. Thiếu/lỗi code → `navigate("/login?error=...")`. |
| `components/ProtectedRoute.tsx` | State `session`; `getSession()` + `onAuthStateChange`; đang load → spinner; không session → `<Navigate to="/login">`; có → render children. |
| `pages/Home.tsx` | Hiện email user; nút **Đăng xuất** (`signOut()` → về `/login`); nút **Gọi `/api/me`** hiện kết quả (bằng chứng Bearer token chạy). |

## 6. Luồng & xử lý lỗi

**Đăng nhập thành công**
```
/ (chưa login) → ProtectedRoute → /login
  → nhập email → signInWithOtp({ shouldCreateUser:false })
  → Supabase gửi mail → bấm link → /auth/callback#...  (hoặc ?code=)
  → detectSessionInUrl đổi ra session → navigate("/") → Home
/api/me: Home bấm nút → apiFetch gắn Bearer → backend get_current_user verify → 200 {user_id,email}
```

Giữ nguyên tắc graceful degradation — mọi lỗi hiện ra, không nuốt lặng:

| Tình huống | Xử lý |
|---|---|
| Email chưa được mời | "Email này chưa được mời vào hệ thống." (mã lỗi thật xác minh lúc implement — dự kiến 422 `otp_disabled`, phải log `error.code`/`error.status` rồi mới map, không tin mù) |
| Quá nhiều lần thử (429) | "Bạn thử lại quá nhiều lần. Đợi một phút rồi thử lại." |
| Lỗi khác khi gửi link | Hiện `error.message` kèm "Không gửi được link đăng nhập." |
| `/auth/callback` thiếu/lỗi code (link hết hạn / đã dùng) | `navigate("/login?error=invalid_code")` → "Link đăng nhập đã hết hạn hoặc đã được dùng. Xin link mới." |
| Backend: thiếu/sai/hết hạn JWT | `401`; frontend `apiFetch` hiện lỗi rõ ràng, không crash |
| Backend/Supabase chết khi check session | Coi như chưa đăng nhập → về `/login`, không sập app |

## 7. Verify (luồng thật, không chỉ typecheck)

Chưa có test framework (thêm ở #1 Parser). Verify #0 bằng luồng thật:

**Backend** (`docker-compose up backend` hoặc `uvicorn` local):
1. `curl /api/health` → `{"status":"ok"}`.
2. `curl /api/me` **không** token → `401`.
3. `curl /api/me` với **token thật** (copy access_token từ session sau khi login ở FE) → `200` đúng
   `user_id` + `email`. **Đây là bằng chứng B2 (verify JWT) chạy đúng** — nếu 401 với token hợp lệ,
   nghi thuật toán/secret (HS256 vs asymmetric).

**Frontend** (`docker-compose up`, hoặc cả hai):
4. **Bootstrap**: Supabase Dashboard → Authentication → Add user → email admin (`ADMIN_EMAIL`).
5. **Chặn route**: mở `/` khi chưa login → bị đẩy sang `/login`.
6. **Invite-only** (quan trọng nhất): nhập email **không** có trong `auth.users` → hiện "chưa được
   mời", và **kiểm tra Dashboard xác nhận KHÔNG có user mới** (bằng chứng A1 chạy).
7. **Login thật**: email admin → nhận mail → bấm link → về `/` thấy Home + email.
8. **Session bền**: F5 `/` → vẫn đăng nhập.
9. **Bearer xuyên suốt**: bấm nút "Gọi /api/me" → hiện đúng user (nối FE↔BE).
10. **Đăng xuất** → về `/login`; mở `/` → bị chặn lại.
11. `docker-compose up` cả hai service không lỗi; frontend gọi được backend qua CORS (không lỗi
    CORS trên console).

## 8. Rủi ro

- **Sai thuật toán verify JWT**: nếu project dùng asymmetric signing keys, HS256 + shared secret sẽ
  fail toàn bộ `/api/me`. Bước verify 3 bắt được ngay; fallback: verify qua JWKS
  (`https://<project>.supabase.co/auth/v1/.well-known/jwks.json`).
- **Magic Link redirect (Site URL)**: GoTrue chấp nhận redirect khi **scheme+host+port** khớp Site
  URL (path không kiểm tra). Dev Vite chạy port **5173**, nên **Site URL phải đổi từ `localhost:3000`
  → `http://localhost:5173`**, nếu không link đưa về sai origin và session không được lập → user bị
  đá về `/login` **im lặng**. Triệu chứng "bấm link xong quay lại trang đăng nhập" ⇒ nghi chỗ này.
  (Ở #8 khi đổi Site URL sang domain Vercel, phải thêm `http://localhost:5173/**` vào Redirect URLs
  để dev local không gãy.)
- **CORS**: thiếu origin frontend trong `ALLOWED_ORIGINS` → mọi call `/api/me` bị chặn ở trình duyệt.
  Bước verify 11 bắt được.
- **Session chưa sẵn khi AuthCallback navigate**: nếu `navigate("/")` chạy trước khi
  `detectSessionInUrl` lập xong session, ProtectedRoute đá về `/login`. Phải chờ `onAuthStateChange`
  báo `SIGNED_IN` (hoặc `getSession()` có giá trị) rồi mới navigate.

## 9. Blocker cần user

1. **`SUPABASE_JWT_SECRET`** — Supabase Dashboard → Project Settings → API → *JWT Secret* (hoặc *JWT
   Keys* nếu project dùng asymmetric). Điền vào `backend/.env` khi test. (Nếu asymmetric → dùng
   fallback JWKS ở mục 8, không cần secret.)
2. **Đổi Site URL** trong Supabase Dashboard → Authentication → URL Configuration → Site URL =
   `http://localhost:5173`.
