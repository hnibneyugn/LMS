# Spec — #7 `/admin/invite`

Ngày: 2026-07-22 · Sub-project #7 (xem `check_list.md`)

## Mục tiêu

Đưa việc **mời thành viên** từ script dòng lệnh (`backend/scripts/invite_user.py`) lên một
**endpoint chỉ dành cho admin** + một **trang web** để admin thêm email thành viên và xem ai đã
trong nhóm. Nhóm < 10 người, invite-only — đây là chỗ admin bootstrap thành viên mới mà không phải
mở terminal.

## Quyết định đã chốt (brainstorm 2026-07-22)

- **Luồng mời = giống hệt script hiện tại, KHÔNG gửi email.** Endpoint tạo tài khoản auth **không
  mật khẩu**, `email_confirm: true`, `user_metadata.password_set: false`. Thành viên tự vào trang
  đăng nhập → "Chưa có mật khẩu? Gửi mã qua email" → nhập mã → buộc đặt mật khẩu. Không đụng tới
  template email "Invite user" của Supabase, đúng bằng luồng đã verify ở #0. (Không dùng
  `/auth/v1/invite`.)
- **Trang có: danh sách thành viên (read-only) + form mời.** Danh sách giúp tránh mời trùng và thấy
  ai đã đặt mật khẩu. → cần thêm `GET /api/admin/members`.
- **Cổng admin = so email trong JWT với `ADMIN_EMAIL`** (không phân biệt hoa/thường). Là **ranh
  giới bảo mật thật**: mọi endpoint admin phụ thuộc dependency `require_admin` phía server, **không
  bao giờ tin frontend**.
- **Frontend biết mình có phải admin không qua `/api/me`** (thêm cờ `is_admin`). `ADMIN_EMAIL`
  **không bao giờ lộ ra browser**.
- **Non-admin vào `/admin/invite` → redirect về `/`** (không làm trang 403 riêng). Backend vẫn tự
  cưỡng chế 403 độc lập.
- **Không cần migration** — chỉ thao tác trên Supabase Auth users, không đụng bảng ứng dụng nào.

## Bối cảnh / ràng buộc

- Backend verify JWT qua JWKS/ES256; `get_current_user()` trả `CurrentUser(user_id, email)` —
  `email` lấy từ claim `email` của token Supabase.
- Tạo/liệt kê user dùng **Supabase Admin API** (`/auth/v1/admin/users`) với
  `SUPABASE_SERVICE_ROLE_KEY` — key này **chỉ ở backend**, bypass mọi policy.
- `invite_user.py` đã chứng minh payload đúng: `email_confirm: true` +
  `user_metadata: {password_set: false}`; tìm trùng bằng cách quét `admin/users` và so email
  thường-hoá.
- Nguyên tắc #4 (graceful degradation): lỗi phía Supabase/mạng KHÔNG được làm 500 mù — trả lỗi có
  thông báo tiếng Việt, cho admin thử lại.

## Kiến trúc

Một router backend mỏng + một dependency admin + một trang frontend. Không migration.

```
backend/app/config/settings.py          # THÊM: admin_email() (required)
backend/app/dependencies/auth.py         # THÊM: require_admin (bọc get_current_user)
backend/app/admin/members.py             # helper: find_member / invite_member / list_members (gọi Admin API)
backend/app/routers/admin.py             # POST /api/admin/invite, GET /api/admin/members
backend/app/routers/me.py                # SỬA: /api/me thêm is_admin
backend/app/main.py                      # include_router(admin.router)
frontend/src/lib/admin.ts                # getMe(), inviteMember(), listMembers()
frontend/src/pages/AdminInvite.tsx       # trang /admin/invite (list + form)
frontend/src/pages/Dashboard.tsx         # SỬA: nút "Mời thành viên" chỉ hiện với admin
frontend/src/App.tsx                     # SỬA: route /admin/invite
backend/scripts/verify_7.py              # verify thật end-to-end
```

### 1. Cổng admin

`settings.admin_email()` — đọc `ADMIN_EMAIL`, dùng `_required` (thiếu → RuntimeError, đọc lười như
các helper khác).

`require_admin` trong `dependencies/auth.py`:

```python
def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    admin = settings.admin_email().strip().lower()
    if not user.email or user.email.strip().lower() != admin:
        raise HTTPException(status_code=403, detail="Chỉ admin mới được phép.")
    return user
```

- Không token / token hỏng → `get_current_user` đã trả 401 trước khi tới đây.
- Token hợp lệ nhưng không phải admin → 403.

### 2. Helper `app/admin/members.py`

Tách phần gọi Admin API ra khỏi router (router mỏng — quy ước backend). Ba hàm thuần, nhận
`base`/`headers` hoặc tự dựng từ settings; dùng `httpx` như script.

- `list_members() -> list[dict]`: GET `/auth/v1/admin/users` (page 1, per_page 200 — đủ cho < 10
  người), trả về danh sách rút gọn `{email, password_set, created_at}`. `password_set` đọc từ
  `user_metadata.password_set` (mặc định `False` nếu vắng).
- `find_member(email) -> dict | None`: quét danh sách, so email thường-hoá (như script).
- `invite_member(email) -> dict`: nếu `find_member` khác None → raise `AlreadyMemberError`; ngược
  lại POST tạo user với payload đã chốt, trả user vừa tạo. Lỗi HTTP khác → raise `InviteError`
  (thông báo tiếng Việt).

Định nghĩa `AlreadyMemberError`, `InviteError` ngay trong module để router ánh xạ sang mã HTTP.

### 3. Router `app/routers/admin.py`

```
POST /api/admin/invite   body {email}   Depends(require_admin)
GET  /api/admin/members                 Depends(require_admin)
```

- **`invite`**: validate email dạng cơ bản (có `@`, có `.` sau `@`, không rỗng) → nếu sai trả 422
  tiếng Việt. Gọi `invite_member`:
  - thành công → 201 `{email, password_set: false, created_at}`.
  - `AlreadyMemberError` → 409 "… đã là thành viên rồi."
  - `InviteError` → 502 "Không mời được lúc này, thử lại sau." (graceful degradation).
- **`members`**: gọi `list_members` → 200 danh sách; lỗi Admin API → 502.
- Chỉ trả các field cần cho UI — **không** trả `id`/token/`storage`… (nguyên tắc lộ tối thiểu).

### 4. `/api/me` thêm `is_admin`

```python
@router.get("/api/me")
def read_me(user: CurrentUser = Depends(get_current_user)):
    admin = settings.admin_email().strip().lower()
    is_admin = bool(user.email) and user.email.strip().lower() == admin
    return {"user_id": user.user_id, "email": user.email, "is_admin": is_admin}
```

### 5. Frontend

`lib/admin.ts`:
- `getMe(): Promise<{user_id, email, is_admin}>` — `apiFetch('/api/me')`.
- `listMembers(): Promise<Member[]>` — `apiFetch('/api/admin/members')`.
- `inviteMember(email): Promise<Member>` — `apiFetch('/api/admin/invite', {method:'POST', body})`.
- `Member = {email: string, password_set: boolean, created_at: string}`.

`pages/AdminInvite.tsx` (route `/admin/invite`, trong `ProtectedRoute`):
- Mount: `getMe()`. `!is_admin` → `navigate('/', {replace:true})`. Đang kiểm → hiện "Đang tải…".
- **Danh sách thành viên**: email + nhãn "Đã đặt mật khẩu" (xanh) / "Chưa đặt mật khẩu" (xám).
- **Form mời**: input email + nút "Mời". Đang gửi → disable. Thành công → prepend vào danh sách +
  xoá input + báo "Đã mời {email}." Lỗi (409/422/502/mạng) → thông báo đỏ inline (dùng
  `errorMessage`). Reuse `Button`/`Input` Shadcn có sẵn.

`Dashboard.tsx`: gọi `getMe()`; chỉ khi `is_admin` mới render nút **"Mời thành viên"** → điều hướng
`/admin/invite`. (Email hiện tại vẫn lấy từ `supabase.auth.getUser()` như cũ; `getMe` chỉ để lấy
cờ admin.)

`App.tsx`: thêm route `/admin/invite` bọc `ProtectedRoute`.

## Xử lý lỗi (tổng hợp)

| Tình huống | Mã | Thông báo (VI) |
|---|---|---|
| Không admin gọi endpoint admin | 403 | "Chỉ admin mới được phép." |
| Email sai định dạng | 422 | "Email không hợp lệ." |
| Email đã là thành viên | 409 | "{email} đã là thành viên rồi." |
| Supabase/Admin API lỗi | 502 | "Không mời được lúc này, thử lại sau." / "Không tải được danh sách thành viên." |
| Non-admin mở trang `/admin/invite` | — | redirect `/` (backend vẫn 403 nếu gọi API) |

## Testing

**Backend pytest** (theo style hiện có — monkeypatch lời gọi HTTP tới Admin API, không chạm mạng
thật):
- `require_admin`: email = ADMIN_EMAIL (khác hoa/thường vẫn khớp) → pass; email khác → 403; không
  token → 401.
- `/api/me`: trả `is_admin` đúng cho admin và non-admin.
- `invite`: payload gửi đúng (`email_confirm:true`, `password_set:false`); trùng → 409; email sai →
  422; Admin API lỗi → 502.
- `members`: shape đúng `{email, password_set, created_at}`, không rò field thừa; Admin API lỗi → 502.

**Frontend**: `npm run build` + `oxlint` sạch.

**Verify thật** (`backend/scripts/verify_7.py` — chuẩn của dự án, HTTP thật + Supabase Auth thật,
session admin mint trong tiến trình):
- Mint session admin → `POST /api/admin/invite` với email dùng-một-lần → 201.
- Xác nhận qua Admin API: user tồn tại, `user_metadata.password_set == false`.
- Mời lại cùng email → 409.
- `GET /api/admin/members` → có email vừa mời.
- Mint session **non-admin** (hoặc giả token non-admin) → gọi endpoint admin → 403.
- **Dọn sạch**: xoá user dùng-một-lần qua Admin API, nhóm về nguyên trạng.

## Không làm (YAGNI)

- Không gửi email mời tự động (đã chốt — dùng luồng self-request code).
- Không xoá/khoá/đổi vai trò thành viên từ UI (chưa cần; xoá vẫn qua Supabase Dashboard).
- Không phân trang danh sách (< 10 người).
- Không migration, không đụng bảng ứng dụng.
