# Design — Bước 3: Auth (Magic Link, invite-only)

Ngày: 2026-07-17 · Trạng thái: chờ duyệt · Bước 3/14 trong `check_list.md`

## 1. Bối cảnh

Pass 1 đã xong: schema + RLS đã chạy trên Supabase live, đã verify anon key không đọc/ghi được dữ
liệu riêng tư. Nhưng **chưa có đường nào để một người thật đăng nhập**, nên toàn bộ RLS
(`auth.uid() = user_id`) chưa dùng được: không có `auth.uid()` thì mọi truy vấn riêng tư trả về rỗng.

Bước 3 dựng đường đăng nhập đó. Nó chặn các bước 4–6 (parser, sync, lessons UI) vì không có user thì
không test được luồng thật.

## 2. Phạm vi

**Làm:**
- Đăng nhập bằng Magic Link (Supabase Auth email OTP), invite-only.
- Middleware bảo vệ mọi route trừ `/login`, `/auth/callback`, static assets.
- `/login` và `/auth/callback`.
- Đăng xuất — không có trong `check_list.md`, nhưng thiếu nó thì không test lại được luồng đăng nhập
  lần thứ hai. Giữ ở mức tối thiểu: một Server Action + nút.

**Không làm (để bước sau):**
- Chức năng mời và phân cấp quyền mời → bước 13. Không thêm cột `invited_by`/`can_invite` lúc này;
  khi cần sẽ thêm migration `0006`, không vướng gì thiết kế này.
- Trang quản lý tài khoản / thu hồi quyền.
- `/dashboard` (bước 12) — sau khi đăng nhập tạm về `/`.

## 3. Quyết định

| # | Quyết định | Lý do |
|---|---|---|
| A1 | `signInWithOtp({ shouldCreateUser: false })` | Toàn bộ cơ chế cưỡng chế invite-only. Mặc định Supabase tự tạo user cho email lạ = public sign-up, trái ràng buộc mục 6 `project_context.md`. Không cần bảng allowlist: `auth.users` chính là danh sách mời. |
| A2 | Middleware vừa refresh token vừa chặn route | Pattern chuẩn `@supabase/ssr`. Mặc định-đóng: thêm route mới là tự động được bảo vệ, không thể quên. Khớp `architecture.md` §Frontend. |
| A3 | Báo thẳng "email chưa được mời" | Nhóm riêng <10 người quen; UX rõ ràng quan trọng hơn rủi ro dò email thành viên. |
| A4 | Sau đăng nhập redirect `/` | `/dashboard` chưa tồn tại (bước 12). Đổi target là sửa một hằng số. |
| A5 | Admin bootstrap thủ công qua Supabase Dashboard | Chưa có UI mời. Hệ quả trực tiếp của A1: **không ai vào được hệ thống nếu chưa có trong `auth.users`, kể cả admin.** |

## 4. Kiến trúc

Bám quy ước dự án: `app/` mỏng, logic ở `client/` + `server/`.

| File | Vai trò | Phụ thuộc |
|---|---|---|
| `middleware.ts` (gốc) | Mỏng: export `middleware` + `config.matcher`. Next.js buộc file ở gốc. | `server/supabase/middleware` |
| `server/supabase/middleware.ts` | `updateSession(request)`: tạo server client theo cookie của request, refresh token, chưa đăng nhập → redirect `/login`. Trả `NextResponse` đã gắn cookie mới. | `@supabase/ssr` |
| `app/login/page.tsx` | Server Component. Đã có session → redirect `/`. Ngược lại render form. | `server/supabase/server`, `client/components/login-form` |
| `client/components/login-form.tsx` | `'use client'`. Nhập email → `signInWithOtp`. Quản lý 3 trạng thái: idle / đã gửi / lỗi. | `client/supabase/client` |
| `app/auth/callback/route.ts` | Route Handler: `exchangeCodeForSession(code)` → redirect `/`. Lỗi → `/login?error=...`. | `server/supabase/server` |
| `server/auth/actions.ts` | Server Action `signOut()`: `supabase.auth.signOut()` + `redirect('/login')`. | `server/supabase/server` |

Ba Supabase client đã có sẵn (`client/supabase/client.ts`, `server/supabase/server.ts`,
`server/supabase/admin.ts`) — **tái sử dụng, không viết mới**. `admin.ts` không được dùng ở bước này.

### Matcher của middleware

Bỏ qua static assets và ảnh để không tốn một lần gọi Supabase cho mỗi file tĩnh:

```
'/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'
```

`/login` và `/auth/callback` vẫn qua middleware nhưng được cho đi tiếp bằng danh sách public path
trong `updateSession` — gom một chỗ, dễ đọc hơn là nhồi vào regex.

## 5. Luồng

**Đăng nhập thành công**
```
/lessons (chưa đăng nhập) → middleware chặn → /login
  → nhập email → signInWithOtp({ shouldCreateUser: false })
  → Supabase gửi mail → bấm link → /auth/callback?code=...
  → exchangeCodeForSession → set cookie → redirect /
```

**Email chưa được mời**: Supabase từ chối, không gửi mail, không tạo user. Form hiện:
*"Email này chưa được mời vào hệ thống."*

> Mã lỗi cụ thể (dự kiến `otp_disabled`, HTTP 422, message "Signups not allowed for otp") **chưa
> được kiểm chứng trên phiên bản `@supabase/supabase-js` đang dùng**. Lúc implement phải log
> `error.code` / `error.status` thật rồi mới map, thay vì tin vào giá trị viết ở đây. Nếu map trượt,
> người dùng sẽ thấy thông báo lỗi chung chung thay vì câu đúng — không sập, nhưng sai UX.

## 6. Xử lý lỗi

Đúng nguyên tắc #4 (graceful degradation) — mọi lỗi phải hiện ra, không nuốt lặng:

| Tình huống | Xử lý |
|---|---|
| Email chưa được mời (mã lỗi xác minh lúc implement) | "Email này chưa được mời vào hệ thống." |
| Quá nhiều lần thử (429) | "Bạn thử lại quá nhiều lần. Đợi một phút rồi thử lại." |
| Lỗi khác khi gửi link | Hiện `error.message` kèm "Không gửi được link đăng nhập." |
| `/auth/callback` thiếu `code` | Redirect `/login?error=missing_code` |
| `exchangeCodeForSession` lỗi (link hết hạn / đã dùng) | Redirect `/login?error=invalid_code` → "Link đăng nhập đã hết hạn hoặc đã được dùng. Xin link mới." |

Middleware không được ném lỗi: Supabase chết thì `getUser()` trả lỗi → coi như chưa đăng nhập →
redirect `/login`, không phải sập cả app.

## 7. Verify

Không có test framework (bước 4 mới thêm), nên verify bằng luồng thật với `npm run dev`:

1. **Bootstrap**: Supabase Dashboard → Authentication → Add user → email của admin (`ADMIN_EMAIL`).
2. **Chặn route**: mở `/` khi chưa đăng nhập → phải bị đẩy sang `/login`.
3. **Invite-only** (quan trọng nhất): nhập một email **không** có trong `auth.users` → phải hiện
   "chưa được mời", và **kiểm tra Dashboard xác nhận không có user mới nào được tạo**. Đây là bằng
   chứng A1 chạy đúng; nếu user mới xuất hiện tức `shouldCreateUser` không có tác dụng.
4. **Đăng nhập thật**: nhập email admin → nhận mail → bấm link → về `/` và thấy nội dung.
5. **Session bền**: F5 lại `/` → vẫn đăng nhập.
6. **RLS có `auth.uid()`**: đăng nhập rồi query `user_profiles` → thấy đúng 1 dòng của mình
   (chứng minh trigger `0005` đã tạo profile và RLS cho đọc).
7. **Đăng xuất** → về `/login`; mở lại `/` → bị chặn.
8. `npm run lint` và `npm run build` sạch.

## 8. Rủi ro

- **Redirect loop**: nếu `/login` không nằm trong danh sách public path, middleware sẽ đẩy `/login`
  về `/login` vô hạn. Bước verify 2 bắt được lỗi này ngay.
- **Cookie không được ghi**: `updateSession` phải trả đúng object `NextResponse` mà nó đã gắn cookie
  vào; tạo response mới sau khi set cookie sẽ làm mất session một cách âm thầm — đăng nhập xong vẫn
  bị đá về `/login`. Bước verify 5 bắt được.
- **URL redirect của Magic Link**: Supabase chỉ chấp nhận redirect tới URL nằm trong danh sách cho
  phép. `http://localhost:3000/**` cần có trong Authentication → URL Configuration, nếu không link
  trong mail sẽ đưa về sai chỗ. Khi deploy (bước 14) phải thêm domain Vercel.
