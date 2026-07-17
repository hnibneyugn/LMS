# Auth (Magic Link, invite-only) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép thành viên đã được mời đăng nhập bằng Magic Link, và chặn mọi route với người chưa đăng nhập.

**Architecture:** Middleware ở gốc gọi `updateSession()` trong `server/`, vừa refresh token vừa chặn route (mặc định-đóng). `/login` là Server Component bọc một Client Component gọi `signInWithOtp({ shouldCreateUser: false })` — đây là toàn bộ cơ chế invite-only. `/auth/callback` đổi code lấy session rồi về `/`.

**Tech Stack:** Next.js 16 App Router, TypeScript, `@supabase/ssr`, Tailwind v4, Shadcn UI.

Spec: `docs/superpowers/specs/2026-07-17-auth-magic-link-design.md`

## Global Constraints

- Ngôn ngữ: chữ hiển thị cho user = **tiếng Việt**; code, tên biến, comment, commit = **tiếng Anh**.
- Import alias `@/*` → root. Dùng `@/client/...` và `@/server/...`. Không dùng `src/`.
- `client/` chỉ được import **type-only** từ `server/`. Không import runtime.
- Tái sử dụng 3 Supabase client đã có: `client/supabase/client.ts`, `server/supabase/server.ts`.
  **Không viết client mới.** `server/supabase/admin.ts` (service-role) **không được dùng** ở bước này.
- Sau đăng nhập redirect về `/` (không phải `/dashboard` — bước 12 mới có).
- Chưa có test runner → verify bằng `curl` vào dev server thật + thao tác browser. Đây là chủ ý,
  không phải thiếu sót; xem §7 của spec.
- Mỗi task kết thúc bằng một commit.

## File Structure

| File | Trách nhiệm |
|---|---|
| `middleware.ts` (gốc) | Chỉ export `middleware` + `config.matcher`. Next.js buộc ở gốc. Không chứa logic. |
| `server/supabase/middleware.ts` | `updateSession()` — refresh token, quyết định cho qua hay redirect. |
| `app/login/page.tsx` | Server Component: đã đăng nhập → redirect `/`; đọc `?error=` truyền xuống form. |
| `client/components/login-form.tsx` | Client Component: form email, gọi `signInWithOtp`, map lỗi sang tiếng Việt. |
| `app/auth/callback/route.ts` | Route Handler: `exchangeCodeForSession` → `/`, lỗi → `/login?error=...`. |
| `server/auth/actions.ts` | Server Action `signOut()`. Thư mục `server/auth/` là mới. |
| `app/page.tsx` | Sửa: hiện email user + nút đăng xuất (thay placeholder). |

---

### Task 1: Middleware bảo vệ route

**Files:**
- Create: `server/supabase/middleware.ts`
- Create: `middleware.ts`

**Interfaces:**
- Consumes: `@supabase/ssr` (`createServerClient`), `next/server`.
- Produces: `updateSession(request: NextRequest): Promise<NextResponse>` — dùng bởi `middleware.ts`.
  `PUBLIC_PATHS: string[]` không export ra ngoài file.

- [ ] **Step 1: Viết `server/supabase/middleware.ts`**

```ts
import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';
import type { Database } from '@/server/types/database.types';

/** Routes reachable without a session. Everything else requires one. */
const PUBLIC_PATHS = ['/login', '/auth/callback'];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * Refreshes the auth token and gates the request. Runs before every matched route,
 * so any new route is protected unless added to PUBLIC_PATHS.
 */
export async function updateSession(request: NextRequest): Promise<NextResponse> {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  // Must call getUser(): it revalidates the token and triggers the cookie refresh above.
  // On any error (e.g. Supabase unreachable) user is null and we fall through to /login
  // rather than throwing — a dead auth service must not take the whole app down.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user && !isPublicPath(request.nextUrl.pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = '/login';
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}
```

> **Cạm bẫy (rủi ro #2 trong spec):** phải trả về đúng object `supabaseResponse` mà `setAll` đã gắn
> cookie vào. Tạo `NextResponse.next()` mới ở cuối sẽ làm mất session **âm thầm** — đăng nhập xong
> vẫn bị đá về `/login`. Đừng "dọn dẹp" đoạn này.

- [ ] **Step 2: Viết `middleware.ts` ở gốc**

```ts
import type { NextRequest } from 'next/server';
import { updateSession } from '@/server/supabase/middleware';

export async function middleware(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  // Skip static assets so they don't each cost a Supabase call.
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
};
```

- [ ] **Step 3: Chạy dev server**

Run: `npm run dev`
Expected: `Ready on http://localhost:3000`. Để chạy nền suốt các task sau.

- [ ] **Step 4: Verify route bị chặn**

Run:
```bash
curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" http://localhost:3000/
```
Expected: `307 -> http://localhost:3000/login`

- [ ] **Step 5: Verify `/login` KHÔNG bị chặn (không có vòng lặp redirect)**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/login
```
Expected: `404` — trang `/login` chưa tồn tại (Task 2 mới tạo), nhưng **404 chứng minh middleware
đã cho qua**. Nếu ra `307` là `PUBLIC_PATHS` sai → sẽ thành vòng lặp vô hạn khi có trang.

- [ ] **Step 6: Commit**

```bash
git add middleware.ts server/supabase/middleware.ts
git commit -m "feat: gate routes behind an auth session in middleware"
```

---

### Task 2: Trang `/login` + form Magic Link

**Files:**
- Create: `app/login/page.tsx`
- Create: `client/components/login-form.tsx`

**Interfaces:**
- Consumes: `createClient()` từ `@/client/supabase/client` (browser), `createClient()` từ
  `@/server/supabase/server` (async — phải `await`), `Button` từ `@/client/components/ui/button`.
- Produces: `LoginForm({ initialError }: { initialError?: string })` — default export không dùng,
  export tên `LoginForm`.

- [ ] **Step 1: Viết `client/components/login-form.tsx`**

`errorMessage()` map lỗi sang tiếng Việt. Mã lỗi "chưa được mời" **chưa được kiểm chứng** — Step 4
sẽ log lỗi thật rồi mới chốt. Bắt cả `code` lẫn `status` để không phụ thuộc một chuỗi duy nhất:

```tsx
'use client';

import { useState } from 'react';
import { createClient } from '@/client/supabase/client';
import { Button } from '@/client/components/ui/button';

type Status = { kind: 'idle' } | { kind: 'sent' } | { kind: 'error'; message: string };

/** Maps a Supabase auth error to Vietnamese copy. Verified against real errors in Step 4. */
function errorMessage(code: string | undefined, status: number | undefined, fallback: string): string {
  if (code === 'otp_disabled' || status === 422) {
    return 'Email này chưa được mời vào hệ thống.';
  }
  if (code === 'over_email_send_rate_limit' || status === 429) {
    return 'Bạn thử lại quá nhiều lần. Đợi một phút rồi thử lại.';
  }
  return `Không gửi được link đăng nhập. ${fallback}`;
}

/** Copy for errors handed over by /auth/callback via ?error=. */
function callbackErrorMessage(error: string): string {
  if (error === 'invalid_code') {
    return 'Link đăng nhập đã hết hạn hoặc đã được dùng. Xin link mới bên dưới.';
  }
  return 'Link đăng nhập không hợp lệ. Xin link mới bên dưới.';
}

export function LoginForm({ initialError }: { initialError?: string }) {
  const [email, setEmail] = useState('');
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState<Status>(
    initialError ? { kind: 'error', message: callbackErrorMessage(initialError) } : { kind: 'idle' },
  );

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        // The whole invite-only mechanism: Supabase refuses unknown emails
        // instead of silently creating an account for them.
        shouldCreateUser: false,
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    setPending(false);

    if (error) {
      console.error('signInWithOtp failed', { code: error.code, status: error.status, error });
      setStatus({ kind: 'error', message: errorMessage(error.code, error.status, error.message) });
      return;
    }
    setStatus({ kind: 'sent' });
  }

  if (status.kind === 'sent') {
    return (
      <div className="space-y-2 text-center">
        <p className="font-medium">Đã gửi link đăng nhập.</p>
        <p className="text-sm text-muted-foreground">
          Kiểm tra hộp thư <span className="font-medium">{email}</span> và bấm vào link để vào hệ thống.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="w-full space-y-4">
      <div className="space-y-2">
        <label htmlFor="email" className="text-sm font-medium">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="ban@example.com"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
        />
      </div>
      {status.kind === 'error' && (
        <p role="alert" className="text-sm text-destructive">
          {status.message}
        </p>
      )}
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? 'Đang gửi...' : 'Gửi link đăng nhập'}
      </Button>
      <p className="text-center text-xs text-muted-foreground">
        Hệ thống chỉ dành cho thành viên được mời.
      </p>
    </form>
  );
}
```

- [ ] **Step 2: Viết `app/login/page.tsx`**

Next.js 16: `searchParams` là Promise, phải `await`.

```tsx
import { redirect } from 'next/navigation';
import { createClient } from '@/server/supabase/server';
import { LoginForm } from '@/client/components/login-form';

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) redirect('/');

  const { error } = await searchParams;

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-2 text-center">
          <p className="text-sm font-medium uppercase tracking-widest text-muted-foreground">
            Personal LMS
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Đăng nhập</h1>
        </div>
        <LoginForm initialError={error} />
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Verify trang render, không có vòng lặp redirect**

Run:
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/login
```
Expected: `200` (không phải 307 — nếu 307 là vòng lặp).

- [ ] **Step 4: Verify invite-only bằng email chưa được mời — bước quan trọng nhất**

Mở `http://localhost:3000/login` trong browser, mở DevTools Console, nhập một email **chắc chắn
không có** trong `auth.users` (ví dụ `khong-ton-tai-12345@example.com`) rồi submit.

Expected:
1. Form hiện **"Email này chưa được mời vào hệ thống."**
2. Console log `signInWithOtp failed` — **đọc `code` và `status` thật**. Nếu không khớp
   `otp_disabled` / 422, sửa `errorMessage()` cho khớp giá trị thật rồi thử lại.
3. Supabase Dashboard → Authentication → Users: **không có user mới nào được tạo**. Đây là bằng chứng
   `shouldCreateUser: false` có tác dụng. Nếu user mới xuất hiện → invite-only đã hỏng, dừng lại và sửa.

- [ ] **Step 5: Commit**

```bash
git add app/login/page.tsx client/components/login-form.tsx
git commit -m "feat: add invite-only magic link login page"
```

---

### Task 3: `/auth/callback` đổi code lấy session

**Files:**
- Create: `app/auth/callback/route.ts`

**Interfaces:**
- Consumes: `createClient()` từ `@/server/supabase/server`.
- Produces: `GET(request: NextRequest): Promise<NextResponse>`. Redirect `/login?error=missing_code`
  hoặc `?error=invalid_code` — hai giá trị này `callbackErrorMessage()` ở Task 2 đã xử lý.

- [ ] **Step 1: Viết `app/auth/callback/route.ts`**

```ts
import { NextResponse, type NextRequest } from 'next/server';
import { createClient } from '@/server/supabase/server';

/**
 * Magic link lands here with ?code=. Exchanging it sets the session cookies.
 * Any failure sends the user back to /login with a reason instead of a blank page.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get('code');

  if (!code) {
    return NextResponse.redirect(`${origin}/login?error=missing_code`);
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    console.error('exchangeCodeForSession failed', { code: error.code, status: error.status });
    return NextResponse.redirect(`${origin}/login?error=invalid_code`);
  }

  return NextResponse.redirect(`${origin}/`);
}
```

- [ ] **Step 2: Verify thiếu `code`**

Run:
```bash
curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" http://localhost:3000/auth/callback
```
Expected: `307 -> http://localhost:3000/login?error=missing_code`

- [ ] **Step 3: Verify `code` sai**

Run:
```bash
curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" "http://localhost:3000/auth/callback?code=bogus-code-123"
```
Expected: `307 -> http://localhost:3000/login?error=invalid_code`

- [ ] **Step 4: Commit**

```bash
git add app/auth/callback/route.ts
git commit -m "feat: exchange magic link code for a session at /auth/callback"
```

---

### Task 4: Đăng xuất + trang chủ hiện user

**Files:**
- Create: `server/auth/actions.ts`
- Modify: `app/page.tsx` (thay toàn bộ nội dung placeholder hiện tại)

**Interfaces:**
- Consumes: `createClient()` từ `@/server/supabase/server`, `Button` từ `@/client/components/ui/button`.
- Produces: `signOut(): Promise<never>` — Server Action, redirect `/login`.

- [ ] **Step 1: Viết `server/auth/actions.ts`**

```ts
'use server';

import { redirect } from 'next/navigation';
import { createClient } from '@/server/supabase/server';

/** Clears the session cookies and sends the user back to the login page. */
export async function signOut() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect('/login');
}
```

- [ ] **Step 2: Sửa `app/page.tsx`**

Middleware đã đảm bảo có user ở đây, nhưng vẫn lấy user để hiện email:

```tsx
import { createClient } from '@/server/supabase/server';
import { signOut } from '@/server/auth/actions';
import { Button } from '@/client/components/ui/button';

export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-widest text-muted-foreground">
          Personal LMS
        </p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Hệ thống học tập chủ động
        </h1>
        <p className="text-muted-foreground">
          Đăng nhập bằng <span className="font-medium">{user?.email}</span>
        </p>
        <p className="max-w-md text-sm text-muted-foreground">
          Bài học và AI sẽ được thêm ở các bước tiếp theo.
        </p>
      </div>
      <form action={signOut}>
        <Button type="submit" variant="outline">
          Đăng xuất
        </Button>
      </form>
    </main>
  );
}
```

- [ ] **Step 3: Verify build + lint**

Run: `npm run lint && npm run build`
Expected: cả hai exit 0. Đặc biệt: không có lỗi "server-only" — nếu `server/auth/actions.ts` bị kéo
vào client bundle thì build sẽ báo.

- [ ] **Step 4: Commit**

```bash
git add server/auth/actions.ts app/page.tsx
git commit -m "feat: show signed-in user and add sign out"
```

---

### Task 5: Verify luồng thật end-to-end

Không có file mới. Đây là bước chứng minh cả bước 3 chạy được với người thật.

**Files:** không đổi (trừ `check_list.md` ở Step 7).

- [ ] **Step 1: Bootstrap admin**

Supabase Dashboard → Authentication → Users → **Add user** → nhập email trong `ADMIN_EMAIL`
(`.env.local`) → chọn **Auto Confirm User**.

Không có bước này thì **không ai đăng nhập được, kể cả bạn** — đúng thiết kế (quyết định A5 trong spec).

- [ ] **Step 2: Kiểm tra Site URL**

Supabase Dashboard → Authentication → URL Configuration → Site URL phải là `http://localhost:3000`.

Không cần thêm gì vào Redirect URLs: GoTrue chấp nhận redirect khi scheme+hostname+port khớp Site URL
và **không so path**, nên `/auth/callback` đã được phủ. (Xem mục Rủi ro trong spec.)

- [ ] **Step 3: Đăng nhập thật**

Mở `http://localhost:3000/` → phải bị đẩy sang `/login` → nhập email admin → submit → form hiện
"Đã gửi link đăng nhập" → mở hộp thư → bấm link.

Expected: về `/` và thấy "Đăng nhập bằng <email của bạn>".

Nếu bị đá về `/login`: xem rủi ro "kiểu hỏng im lặng" trong spec — kiểm tra URL trong mail có trỏ
`/auth/callback` không, hay trỏ về `/`.

- [ ] **Step 4: Verify session bền qua reload**

F5 lại `/`. Expected: vẫn đăng nhập, không bị đá ra. (Đây là bước bắt lỗi cookie ở Task 1.)

- [ ] **Step 5: Verify trigger tạo profile**

Supabase Dashboard → Table Editor → `user_profiles`.

Expected: đúng **1 dòng**, `display_name` = phần trước `@` của email admin. Chứng minh trigger
`0005_profile_trigger.sql` đã chạy khi user được tạo ở Step 1.

- [ ] **Step 6: Verify đăng xuất**

Bấm "Đăng xuất" → về `/login`. Mở lại `http://localhost:3000/` → bị đẩy về `/login`.

- [ ] **Step 7: Cập nhật `check_list.md`**

Đánh dấu bước 3 xong, ghi rõ đã verify bằng luồng thật:

```markdown
### Bước 3 — Auth
- [x] Magic Link (Supabase Auth), tắt public sign-up (`shouldCreateUser: false`)
- [x] Middleware bảo vệ route (trừ `/login`, `/auth/callback`)
- [x] `/login`, `/auth/callback`
- [x] Đăng xuất (thêm ngoài checklist gốc — cần để test lại luồng đăng nhập)
- Verify: đăng nhập thật bằng email admin OK; email chưa mời bị từ chối và KHÔNG tạo user mới;
  session bền qua reload; `user_profiles` có 1 dòng do trigger 0005 tạo
- Lưu ý bootstrap: user phải được tạo sẵn trong `auth.users` (Dashboard → Add user) mới đăng nhập được
```

- [ ] **Step 8: Commit**

```bash
git add check_list.md
git commit -m "docs: mark step 3 auth complete after verifying the real flow"
```

---

## Self-Review

**Spec coverage:**

| Yêu cầu trong spec | Task |
|---|---|
| §2 Magic Link invite-only | Task 2 |
| §2 Middleware bảo vệ route | Task 1 |
| §2 `/login`, `/auth/callback` | Task 2, 3 |
| §2 Đăng xuất | Task 4 |
| §3 A1 `shouldCreateUser: false` | Task 2 Step 1, verify Step 4 |
| §3 A2 middleware refresh + gate | Task 1 Step 1 |
| §3 A3 báo thẳng "chưa được mời" | Task 2 `errorMessage()` |
| §3 A4 redirect `/` | Task 3 Step 1 |
| §3 A5 bootstrap admin thủ công | Task 5 Step 1 |
| §6 bảng xử lý lỗi (5 dòng) | Task 2 `errorMessage()`/`callbackErrorMessage()`, Task 3 |
| §7 verify 8 mục | Task 1 Step 4–5, Task 2 Step 4, Task 3 Step 2–3, Task 4 Step 3, Task 5 |
| §8 rủi ro redirect loop | Task 1 Step 5, Task 2 Step 3 |
| §8 rủi ro cookie không ghi | Task 1 Step 1 (cảnh báo), Task 5 Step 4 |
| §8 rủi ro Site URL | Task 5 Step 2 |

**Type consistency:** `updateSession` (Task 1) — tên khớp giữa 2 file. `LoginForm({ initialError })`
(Task 2) khớp lời gọi ở `app/login/page.tsx`. `?error=` chỉ nhận `missing_code` | `invalid_code`
(Task 3) — cả hai đều được `callbackErrorMessage()` (Task 2) xử lý. `signOut()` (Task 4) dùng đúng
dạng `form action={signOut}`.

**Placeholder scan:** không còn TBD/TODO/"xử lý lỗi phù hợp". Mọi step sửa code đều có code đầy đủ,
mọi step verify đều có lệnh chạy được kèm output mong đợi.

**Khoảng trống đã biết (có chủ ý):** mã lỗi "chưa được mời" chưa kiểm chứng được ở thời điểm viết
plan — Task 2 Step 4 bắt buộc đọc `code`/`status` thật từ console rồi mới chốt `errorMessage()`.
Đây là lý do `errorMessage()` bắt cả `code` lẫn `status` thay vì tin vào một chuỗi duy nhất.
