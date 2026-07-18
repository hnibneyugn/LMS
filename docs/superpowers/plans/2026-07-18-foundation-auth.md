# Foundation + Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng walking skeleton React (Vite) SPA + FastAPI trên Supabase sẵn có, cho một người đã được mời đăng nhập Magic Link end-to-end và backend verify được JWT của họ.

**Architecture:** 1 repo, 2 thư mục `frontend/` (Vite SPA) + `backend/` (FastAPI). Gỡ scaffold Next.js, giữ `supabase/migrations/` + `docs/`. Frontend dùng `@supabase/supabase-js` xử lý toàn bộ luồng auth (Magic Link, session); backend chỉ verify JWT Supabase (HS256) qua FastAPI dependency, không tự quản session. Local dev qua docker-compose.

**Tech Stack:** Vite + React + TypeScript + React Router + Tailwind + Shadcn UI + `@supabase/supabase-js`; Python 3.12 + FastAPI + PyJWT + Uvicorn; Docker / docker-compose.

## Global Constraints

- Chi phí $0 (free tier); chỉ thêm phức tạp khi thực sự cần.
- Cách ly dữ liệu bằng RLS `auth.uid() = user_id` — #0 không thêm/sửa bảng nào; migrations giữ nguyên.
- Nội dung hiển thị cho user = **tiếng Việt**; code/biến/tên file/comment kỹ thuật/commit = **tiếng Anh**.
- Graceful degradation: mọi lỗi hiện ra, không nuốt lặng; không để một lỗi làm sập app.
- Không NoSQL. Mọi secret qua biến môi trường, không hardcode.
- Node 20+, Python 3.12. Frontend Docker chỉ cho local dev (`Dockerfile.dev`); backend `Dockerfile` dùng chung.
- `SUPABASE_SERVICE_ROLE_KEY` chỉ dùng server-side (không dùng trong #0).
- `callout_types.py` là nguồn duy nhất định nghĩa loại câu hỏi (đồng bộ với CHECK constraint bảng `questions`).

---

### Task 1: Repo restructure — gỡ Next.js, tạo khung 2 thư mục

**Files:**
- Delete: `app/`, `next.config.ts`, `next-env.d.ts`, `components.json`, `client/`, `server/`, `package.json`, `package-lock.json`, `tsconfig.json`, `eslint.config.mjs`, `postcss.config.mjs`, `.next/` (nếu có)
- Create: `backend/app/config/callout_types.py` (port từ `server/config/callout-types.ts`)
- Create: `frontend/` (rỗng, tạo ở Task 4 bằng `npm create vite`)
- Keep untouched: `supabase/migrations/`, `docs/`, `CLAUDE.md`, `check_list.md`, `SETUP.md`, `README.md`, `.gitignore`, `.env.local`

**Interfaces:**
- Produces: `backend/app/config/callout_types.py` với `QUESTION_TYPES: list[str]` và `is_question_type(value: str) -> bool`.

- [ ] **Step 1: Xoá scaffold Next.js**

```bash
cd "d:/test claude/LMS"
git rm -r --quiet app next.config.ts next-env.d.ts components.json client server package.json package-lock.json tsconfig.json eslint.config.mjs postcss.config.mjs 2>/dev/null || true
rm -rf .next node_modules
```

- [ ] **Step 2: Tạo file config đã port sang Python**

Create `backend/app/config/callout_types.py`:

```python
"""Single source of truth for question types the Markdown parser treats as review questions.

Must stay in sync with the `type` CHECK constraint on the `questions` table
(supabase/migrations/0002_tables.sql). The parser (later sub-project) reads
`> [!<type>]` callouts and keeps only those whose type is in QUESTION_TYPES.
"""

QUESTION_TYPES: list[str] = ["recall", "scenario", "compare", "explain"]


def is_question_type(value: str) -> bool:
    """Return True if `value` is one of the whitelisted question types."""
    return value in QUESTION_TYPES
```

Create empty package markers `backend/app/__init__.py` and `backend/app/config/__init__.py` (nội dung rỗng).

- [ ] **Step 3: Xác nhận migrations + docs còn nguyên**

Run:
```bash
ls supabase/migrations/    # phải thấy 0001..0005
ls docs/superpowers/specs/ # phải thấy 2 spec
git status
```
Expected: 5 migration files + specs còn đó; các file Next.js hiện ở "deleted".

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove Next.js scaffold, port callout types to backend/ for React+FastAPI restructure"
```

---

### Task 2: Backend skeleton + health endpoint (TDD)

**Files:**
- Create: `backend/requirements.txt`, `backend/pytest.ini`, `backend/.env.example`, `backend/Dockerfile`
- Create: `backend/app/main.py`, `backend/app/routers/__init__.py`, `backend/app/routers/health.py`
- Test: `backend/tests/__init__.py`, `backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.main:app` (FastAPI instance với CORSMiddleware); `GET /api/health` → `{"status": "ok"}`.

- [ ] **Step 1: Tạo requirements + pytest config + Dockerfile**

Create `backend/requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.32
pyjwt>=2.9
python-dotenv>=1.0
pytest>=8.3
httpx>=0.27
```

Create `backend/pytest.ini`:
```ini
[pytest]
pythonpath = .
```

Create `backend/.env.example`:
```
# --- Supabase ---
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
# Project Settings -> API -> JWT Secret (HS256). Nếu project dùng asymmetric keys, xem spec §8 (JWKS).
SUPABASE_JWT_SECRET=
# --- Admin ---
ADMIN_EMAIL=
# --- CORS: origin của frontend, phân tách bằng dấu phẩy ---
ALLOWED_ORIGINS=http://localhost:5173
```

Create `backend/Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Lập môi trường Python cục bộ để chạy test**

Run (PowerShell):
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Expected: cài xong không lỗi. (Nếu máy không có Python trên PATH: chạy test qua Docker bằng `docker compose run --rm backend pytest` sau khi có docker-compose ở Task 6 — nhưng ưu tiên venv để vòng TDD nhanh.)

Thêm `.venv/` vào `.gitignore` nếu chưa có.

- [ ] **Step 3: Viết test health (failing)**

Create `backend/tests/__init__.py` (rỗng). Create `backend/tests/test_health.py`:
```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
```

- [ ] **Step 4: Chạy test để xác nhận FAIL**

Run: `pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'` (chưa có `main.py`).

- [ ] **Step 5: Viết health router + main app**

Create `backend/app/routers/__init__.py` (rỗng). Create `backend/app/routers/health.py`:
```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health():
    """Public health check — cũng dùng cho keep-alive ping (#8)."""
    return {"status": "ok"}
```

Create `backend/app/main.py`:
```python
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health

load_dotenv()

app = FastAPI(title="Personal LMS API")

_origins = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
```

- [ ] **Step 6: Chạy test để xác nhận PASS**

Run: `pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(backend): FastAPI skeleton with CORS and /api/health"
```

---

### Task 3: Backend JWT auth dependency + `/api/me` (TDD)

**Files:**
- Create: `backend/app/dependencies/__init__.py`, `backend/app/dependencies/auth.py`
- Create: `backend/app/routers/me.py`
- Modify: `backend/app/main.py` (include me router)
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `app.main:app`.
- Produces: `app.dependencies.auth.CurrentUser(user_id: str, email: str | None)`; `get_current_user(authorization: str | None = Header(...)) -> CurrentUser` (verify Supabase JWT HS256, aud `authenticated`; 401 nếu thiếu/sai/hết hạn). `GET /api/me` → `{"user_id": str, "email": str | None}`.

- [ ] **Step 1: Viết test auth (failing)**

Create `backend/tests/test_auth.py`:
```python
import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app

SECRET = "test-secret-for-hs256"
client = TestClient(app)


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)


def _token(payload: dict) -> str:
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_me_without_header_is_401():
    res = client.get("/api/me")
    assert res.status_code == 401


def test_me_with_malformed_header_is_401():
    res = client.get("/api/me", headers={"Authorization": "Token abc"})
    assert res.status_code == 401


def test_me_with_invalid_signature_is_401():
    bad = jwt.encode({"sub": "u1", "aud": "authenticated"}, "wrong-secret", algorithm="HS256")
    res = client.get("/api/me", headers={"Authorization": f"Bearer {bad}"})
    assert res.status_code == 401


def test_me_with_wrong_audience_is_401():
    tok = _token({"sub": "u1", "email": "a@b.c", "aud": "anon"})
    res = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 401


def test_me_with_valid_token_returns_user():
    tok = _token({"sub": "user-123", "email": "a@b.c", "aud": "authenticated"})
    res = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 200
    assert res.json() == {"user_id": "user-123", "email": "a@b.c"}
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `/api/me` chưa tồn tại (404, không phải 401/200).

- [ ] **Step 3: Viết auth dependency**

Create `backend/app/dependencies/__init__.py` (rỗng). Create `backend/app/dependencies/auth.py`:
```python
import os
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException, status


@dataclass
class CurrentUser:
    user_id: str
    email: str | None


def _decode(token: str) -> dict:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        # Missing config is a server error, not a client error.
        raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET is not configured")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )


def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
        )
    token = authorization.removeprefix("Bearer ").strip()
    payload = _decode(token)
    return CurrentUser(user_id=payload["sub"], email=payload.get("email"))
```

- [ ] **Step 4: Viết me router + đăng ký vào app**

Create `backend/app/routers/me.py`:
```python
from fastapi import APIRouter, Depends

from app.dependencies.auth import CurrentUser, get_current_user

router = APIRouter()


@router.get("/api/me")
def read_me(user: CurrentUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "email": user.email}
```

Modify `backend/app/main.py` — thêm import và include router. Đổi dòng import routers thành:
```python
from app.routers import health, me
```
và thêm sau `app.include_router(health.router)`:
```python
app.include_router(me.router)
```

- [ ] **Step 5: Chạy test để xác nhận PASS**

Run: `pytest -v`
Expected: tất cả test (health + auth) PASS.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(backend): verify Supabase JWT via get_current_user and add protected /api/me"
```

---

### Task 4: Frontend scaffold (Vite + Router + Tailwind + Shadcn + Supabase client)

**Files:**
- Create: toàn bộ `frontend/` qua `npm create vite`
- Create: `frontend/.env.example`, `frontend/Dockerfile.dev`
- Create: `frontend/src/lib/supabase.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/database.types.ts` (port)
- Modify: `frontend/vite.config.ts`, `frontend/tsconfig.json` + `tsconfig.app.json` (alias `@`)

**Interfaces:**
- Produces: `@/lib/supabase` export `supabase` (browser client); `@/lib/api` export `apiFetch(path, options?) -> Promise<any>` (gắn Bearer token, gọi `VITE_API_BASE_URL`). Alias `@` → `frontend/src`. Shadcn `Button`, `Input` ở `@/components/ui`.

- [ ] **Step 1: Tạo app Vite + cài deps**

Run (PowerShell, ở root repo):
```powershell
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install @supabase/supabase-js react-router-dom
npm install -D @tailwindcss/vite
```

- [ ] **Step 2: Cấu hình Tailwind v4 + alias `@`**

Sửa `frontend/vite.config.ts` thành:
```ts
import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { host: true, port: 5173 },
})
```

Thay toàn bộ `frontend/src/index.css` bằng:
```css
@import "tailwindcss";
```

Thêm alias vào `frontend/tsconfig.json` — trong `compilerOptions` (tạo mục nếu chưa có):
```json
"baseUrl": ".",
"paths": { "@/*": ["./src/*"] }
```
và tương tự trong `frontend/tsconfig.app.json` (`compilerOptions.baseUrl = "."`, `compilerOptions.paths = { "@/*": ["./src/*"] }`).

- [ ] **Step 3: Khởi tạo Shadcn + thêm Button, Input**

Run (trong `frontend/`):
```powershell
npx shadcn@latest init -d
npx shadcn@latest add button input
```
Expected: sinh `components.json`, `src/lib/utils.ts` (có `cn()`), `src/components/ui/button.tsx`, `src/components/ui/input.tsx`. (Nếu init hỏi, chọn base color mặc định; `-d` dùng default.)

- [ ] **Step 4: Tạo Supabase client + API wrapper + env + Dockerfile**

Create `frontend/src/lib/supabase.ts`:
```ts
import { createClient } from "@supabase/supabase-js"

const url = import.meta.env.VITE_SUPABASE_URL as string
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string

if (!url || !anonKey) {
  throw new Error("Thiếu VITE_SUPABASE_URL hoặc VITE_SUPABASE_ANON_KEY")
}

// detectSessionInUrl (default true) handles the magic-link callback; persistSession keeps the session across reloads.
export const supabase = createClient(url, anonKey)
```

Create `frontend/src/lib/api.ts`:
```ts
import { supabase } from "./supabase"

const BASE = import.meta.env.VITE_API_BASE_URL as string

/** Call the FastAPI backend, attaching the Bearer token from the Supabase session. */
export async function apiFetch(path: string, options: RequestInit = {}) {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error("Chưa đăng nhập")

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...(options.headers ?? {}), Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`API ${path} lỗi ${res.status}`)
  return res.json()
}
```

Create `frontend/src/lib/database.types.ts` — copy nội dung từ file cũ đã xoá. Nếu không còn bản cũ, dùng nội dung tối thiểu sau (mở rộng ở sub-project sau):
```ts
// Generated/maintained to match supabase/migrations. Expand when building features that use the relevant tables.
export type Database = Record<string, unknown>
```

Create `frontend/.env.example`:
```
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_BASE_URL=http://localhost:8000
```

Create `frontend/Dockerfile.dev`:
```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json .
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]
```

- [ ] **Step 5: Tạo `.env.local` cho frontend từ giá trị thật**

Tạo `frontend/.env.local` (không commit) với `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` lấy từ `.env.local` cũ ở root (giá trị `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`), và `VITE_API_BASE_URL=http://localhost:8000`.

- [ ] **Step 6: Verify build sạch**

Run (trong `frontend/`): `npm run build`
Expected: build thành công, không lỗi TypeScript (App mặc định của Vite vẫn còn — sẽ thay ở Task 5).

- [ ] **Step 7: Commit**

```bash
cd ..
git add frontend .gitignore
git commit -m "feat(frontend): Vite + React Router + Tailwind + Shadcn scaffold with Supabase client and apiFetch"
```

---

### Task 5: Frontend auth — Login, AuthCallback, ProtectedRoute, Home, Router

**Files:**
- Create: `frontend/src/components/ProtectedRoute.tsx`
- Create: `frontend/src/pages/Login.tsx`, `frontend/src/pages/AuthCallback.tsx`, `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`

**Interfaces:**
- Consumes: `@/lib/supabase`, `@/lib/api` (apiFetch), `@/components/ui/button`, `@/components/ui/input`.
- Produces: routes `/login`, `/auth/callback`, và `/*` (protected → Home).

- [ ] **Step 1: ProtectedRoute**

Create `frontend/src/components/ProtectedRoute.tsx`:
```tsx
import { useEffect, useState } from "react"
import { Navigate } from "react-router-dom"
import type { Session } from "@supabase/supabase-js"
import { supabase } from "@/lib/supabase"

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  if (loading) return <div className="p-8">Đang tải…</div>
  if (!session) return <Navigate to="/login" replace />
  return <>{children}</>
}
```

- [ ] **Step 2: Login page (invite-only + map lỗi)**

Create `frontend/src/pages/Login.tsx`:
```tsx
import { useEffect, useState } from "react"
import { Navigate } from "react-router-dom"
import { supabase } from "@/lib/supabase"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function Login() {
  const [email, setEmail] = useState("")
  const [state, setState] = useState<"idle" | "sent" | "error">("idle")
  const [message, setMessage] = useState("")
  const [checking, setChecking] = useState(true)
  const [hasSession, setHasSession] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setHasSession(!!data.session)
      setChecking(false)
    })
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        shouldCreateUser: false,
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    })
    if (error) {
      // Log the real error code to verify the mapping (spec §6) before trusting it.
      console.error("signInWithOtp", error.status, error.code, error.message)
      setState("error")
      if (error.status === 422 || error.code === "otp_disabled") {
        setMessage("Email này chưa được mời vào hệ thống.")
      } else if (error.status === 429) {
        setMessage("Bạn thử lại quá nhiều lần. Đợi một phút rồi thử lại.")
      } else {
        setMessage(`Không gửi được link đăng nhập. ${error.message}`)
      }
      return
    }
    setState("sent")
  }

  if (checking) return null
  if (hasSession) return <Navigate to="/" replace />

  return (
    <div className="mx-auto max-w-sm p-8">
      <h1 className="mb-4 text-xl font-semibold">Đăng nhập</h1>
      {state === "sent" ? (
        <p>
          Đã gửi link đăng nhập tới <b>{email}</b>. Kiểm tra hộp thư.
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@example.com"
          />
          <Button type="submit" className="w-full">
            Gửi link đăng nhập
          </Button>
          {state === "error" && <p className="text-sm text-red-600">{message}</p>}
        </form>
      )}
    </div>
  )
}
```

- [ ] **Step 3: AuthCallback**

Create `frontend/src/pages/AuthCallback.tsx`:
```tsx
import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { supabase } from "@/lib/supabase"

export function AuthCallback() {
  const navigate = useNavigate()

  useEffect(() => {
    // supabase-js (detectSessionInUrl) exchanges the URL token for a session on load.
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
      if (session) navigate("/", { replace: true })
    })
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) navigate("/", { replace: true })
    })
    // No session after a few seconds => the link is broken/expired.
    const timer = setTimeout(() => {
      supabase.auth.getSession().then(({ data }) => {
        if (!data.session) navigate("/login?error=invalid_code", { replace: true })
      })
    }, 3000)

    return () => {
      sub.subscription.unsubscribe()
      clearTimeout(timer)
    }
  }, [navigate])

  return <div className="p-8">Đang đăng nhập…</div>
}
```

- [ ] **Step 4: Home (placeholder protected, gọi thử /api/me)**

Create `frontend/src/pages/Home.tsx`:
```tsx
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { supabase } from "@/lib/supabase"
import { apiFetch } from "@/lib/api"
import { Button } from "@/components/ui/button"

export function Home() {
  const navigate = useNavigate()
  const [email, setEmail] = useState<string | null>(null)
  const [apiResult, setApiResult] = useState("")

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setEmail(data.user?.email ?? null))
  }, [])

  async function handleSignOut() {
    await supabase.auth.signOut()
    navigate("/login", { replace: true })
  }

  async function pingApi() {
    try {
      const data = await apiFetch("/api/me")
      setApiResult(JSON.stringify(data))
    } catch (e) {
      setApiResult(`Lỗi: ${(e as Error).message}`)
    }
  }

  return (
    <div className="space-y-4 p-8">
      <h1 className="text-xl font-semibold">Personal LMS</h1>
      <p>
        Đăng nhập với: <b>{email}</b>
      </p>
      <div className="flex gap-2">
        <Button onClick={pingApi}>Gọi /api/me</Button>
        <Button variant="outline" onClick={handleSignOut}>
          Đăng xuất
        </Button>
      </div>
      {apiResult && <pre className="rounded bg-gray-100 p-2 text-sm">{apiResult}</pre>}
    </div>
  )
}
```

- [ ] **Step 5: Router**

Replace `frontend/src/App.tsx`:
```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Login } from "@/pages/Login"
import { AuthCallback } from "@/pages/AuthCallback"
import { Home } from "@/pages/Home"
import { ProtectedRoute } from "@/components/ProtectedRoute"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
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

Replace `frontend/src/main.tsx`:
```tsx
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App.tsx"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 6: Verify build sạch**

Run (trong `frontend/`): `npm run build`
Expected: build thành công, không lỗi TypeScript (không còn import mặc định của Vite).

- [ ] **Step 7: Commit**

```bash
cd ..
git add frontend
git commit -m "feat(frontend): Magic Link login, auth callback, ProtectedRoute, protected Home"
```

---

### Task 6: docker-compose + verify end-to-end luồng thật

**Files:**
- Create: `docker-compose.yml` (root)
- Modify: `.gitignore` (thêm `.env`, `.env.local`, `.venv/`, `node_modules/` nếu chưa có)

**Interfaces:**
- Consumes: `backend/Dockerfile`, `frontend/Dockerfile.dev`, `backend/.env`, `frontend/.env` (hoặc `.env.local`).

- [ ] **Step 1: docker-compose.yml**

Create `docker-compose.yml`:
```yaml
services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    env_file: ./frontend/.env.local

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
    env_file: ./backend/.env
```

- [ ] **Step 2: Chuẩn bị env thật + blocker**

- Tạo `backend/.env` từ `backend/.env.example` với giá trị thật: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ADMIN_EMAIL`, `ALLOWED_ORIGINS=http://localhost:5173`, và **`SUPABASE_JWT_SECRET`** (Dashboard → Project Settings → API → JWT Secret). *(Nếu project dùng asymmetric keys → dừng, báo user để đổi auth.py sang JWKS theo spec §8.)*
- Đảm bảo `frontend/.env.local` đã có (Task 4 Step 5).
- **Supabase Dashboard → Authentication → URL Configuration → Site URL = `http://localhost:5173`** (spec §8/§9).
- **Supabase Dashboard → Authentication → Add user → `ADMIN_EMAIL`** (bootstrap, spec §7).

- [ ] **Step 3: Chạy cả hai service**

Run (root): `docker compose up --build`
Expected: backend log Uvicorn `:8000`, frontend log Vite `:5173`, không lỗi.

- [ ] **Step 4: Verify backend (curl)**

```bash
curl http://localhost:8000/api/health        # {"status":"ok"}
curl -i http://localhost:8000/api/me          # HTTP 401
```
Expected: health 200; me 401 (thiếu token).

- [ ] **Step 5: Verify luồng frontend thật (thủ công, spec §7)**

Mở `http://localhost:5173`:
1. Chưa login → bị đẩy sang `/login`.
2. **Invite-only**: nhập email KHÔNG có trong `auth.users` → hiện "Email này chưa được mời"; mở Dashboard xác nhận **không có user mới** (console log `error.status`/`error.code` để xác minh mapping).
3. Nhập email `ADMIN_EMAIL` → nhận mail → bấm link → về `/` thấy Home + đúng email.
4. F5 `/` → vẫn đăng nhập (session bền).
5. Bấm **Gọi /api/me** → hiện `{"user_id":...,"email":...}` đúng (bằng chứng Bearer token + verify JWT chạy; nếu 401 với token hợp lệ → nghi HS256 vs asymmetric, xử lý theo spec §8).
6. Bấm **Đăng xuất** → về `/login`; mở `/` → bị chặn.
7. Console không có lỗi CORS.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml .gitignore
git commit -m "chore: docker-compose for local dev; verify auth end-to-end"
```

---

## Ghi chú thực thi

- Task 2–3 chạy TDD thật với pytest (backend có test framework riêng, độc lập với frontend). Task 4–5 chưa có test runner frontend (thêm ở sub-project #1 Parser nếu cần) → verify bằng `npm run build` + luồng thật ở Task 6.
- Nếu máy không có Python/Node trên PATH, chạy test/build qua Docker; nhưng ưu tiên chạy cục bộ cho vòng lặp nhanh.
- Blocker phải có trước Task 6 Step 5: `SUPABASE_JWT_SECRET`, Site URL `localhost:5173`, đã Add user admin.
