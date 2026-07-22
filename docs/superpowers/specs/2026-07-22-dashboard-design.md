# Spec — #6 Dashboard

Ngày: 2026-07-22 · Sub-project #6 (xem `check_list.md`)

## Mục tiêu

Thay trang Home placeholder bằng một **dashboard thật**: thống kê chuyên cần của cá nhân
(streak, câu hỏi theo ngày, % hoàn thành bài học) + **bảng xếp hạng cả nhóm theo số ngày
học**. Đây là màn hình đầu tiên user thấy sau khi đăng nhập (`/`).

## Quyết định đã chốt (brainstorm 2026-07-22)

- **Thư viện biểu đồ = Recharts.** CLAUDE.md ưu tiên Tremor, nhưng Tremor v3 nhắm Tailwind v3 /
  React 18; stack hiện tại là **Tailwind v4 + React 19** nên Tremor dễ vỡ. Recharts là fallback
  được CLAUDE.md cho phép và chạy sạch trên stack này. → chỉ thêm dep frontend `recharts`.
- **BarChart câu hỏi theo tuần = 7 ngày gần nhất, mỗi ngày 1 cột** (hôm nay lùi về 6 ngày trước).
  Ngày không có hoạt động → cột 0 (zero-fill).
- **Streak = streak hiện tại + streak dài nhất.** Đều tính từ `daily_activity.activity_date`.
  **Streak hiện tại phải kết thúc đúng hôm nay** — qua 0h (giờ VN) mà chưa học là mất (reset 0).
- **Mốc ngày = giờ Việt Nam (UTC+7)**, áp dụng ở **cả nơi ghi lẫn nơi đọc**. Hệ quả: `quiz.py`
  (#4) đang ghi `daily_activity.activity_date` theo ngày UTC sẽ đổi sang **ngày VN**, qua một
  helper dùng chung, để streak/biểu đồ khớp đúng dòng đã lưu quanh nửa đêm.
- **Dữ liệu đi qua backend (D21).** Frontend không đọc thẳng Supabase; thêm router
  `dashboard.py`. Kể cả leaderboard cũng đọc `leaderboard_view` phía server để đồng nhất.
- **Xếp hạng theo số ngày học** (`count(distinct activity_date)`), KHÔNG theo điểm (D-dash-1;
  đồng bộ với ghi chú #6 và D15 — giờ học web không đo được đáng tin).
- **Dashboard thay Home tại `/`.** Giữ route catch-all `/*` hiện có; chỉ đổi component.

## Bối cảnh / ràng buộc

- Nhóm < 10 người, invite-only. Bảng riêng tư bảo vệ bằng RLS `auth.uid() = user_id`.
- `daily_activity` (đã có): `(user_id, activity_date date, questions_done_count int)`. `quiz.py`
  hiện ghi `activity_date` theo **ngày UTC** và tăng `questions_done_count` **mỗi câu 1 lần/ngày**.
  Spec này đổi nơi ghi sang **ngày VN (UTC+7)** để nhất quán với streak/biểu đồ (xem §0).
- Giờ Việt Nam là **UTC+7 cố định, không DST** → offset tĩnh, không cần thư viện tz.
- `lesson_progress` (đã có): `(user_id, lesson_id, status 'done'|'not_done', completed_at)`.
- `lessons.user_id` có thật (migration `0006`) → "tổng bài" đếm theo user.
- `leaderboard_view` (migration `0004`) hiện có `lessons_completed`, `total_questions_done`,
  `GRANT SELECT to authenticated`; là **security-definer view** (đọc xuyên RLS có chủ đích) để
  tổng hợp cross-user — chỉ lộ số liệu tổng hợp, không lộ nội dung trả lời/chat/tài liệu.

## Kiến trúc

Một router backend mỏng + một trang frontend + một migration sửa view.

```
backend/app/util/dates.py          # VN_TZ (UTC+7) + vn_today() — nguồn duy nhất "ngày ứng dụng"
backend/app/routers/dashboard.py   # /api/dashboard/me, /api/dashboard/leaderboard
backend/app/routers/quiz.py        # SỬA: ghi daily_activity theo ngày VN (dùng vn_today)
supabase/migrations/0009_leaderboard_active_days.sql
frontend/src/pages/Dashboard.tsx   # thay Home.tsx tại "/"
frontend/src/lib/dashboard.ts      # wrapper apiFetch (kiểu TS cho payload)
```

### 0. Helper ngày VN — `app/util/dates.py`

Nguồn chân lý duy nhất cho "ngày ứng dụng":

```python
from datetime import date, datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))          # UTC+7, không DST

def vn_today() -> date:
    return datetime.now(VN_TZ).date()

def vn_date_of(iso_ts: str) -> date:          # 'ngày VN' của một ISO timestamp có offset
    return datetime.fromisoformat(iso_ts).astimezone(VN_TZ).date()
```

`quiz.py` (#4) đổi sang dùng `vn_today()` khi ghi `daily_activity.activity_date`, và dùng
`vn_date_of(created_at)` cho phép kiểm "câu này đã làm hôm nay chưa" (thay `_attempt_date` hiện
convert sang UTC). Nhờ vậy "một câu / một ngày" và streak/biểu đồ cùng một khái niệm "ngày VN".
Không migration: cột `activity_date` vẫn là `date`, chỉ đổi giá trị được ghi từ nay về sau (dữ
liệu #4 lúc verify đã dọn sạch; quy mô nhóm nhỏ nên vài dòng cũ lệch — nếu có — không đáng kể).

### 1. Backend — `routers/dashboard.py`

Theo đúng khuôn `_Repo` + `db.admin()` + lọc `user_id` tường minh của `quiz.py`. Bài của người
khác không lộ. Prefix `/api/dashboard`, cả hai route `Depends(get_current_user)`. Đăng ký ở
`main.py` cạnh các router khác.

**`GET /api/dashboard/me`** → thống kê cá nhân:

```jsonc
{
  "current_streak": 3,
  "longest_streak": 7,
  "weekly_questions": [            // đúng 7 phần tử, cũ→mới, zero-fill
    {"date": "2026-07-16", "count": 0},
    {"date": "2026-07-17", "count": 2},
    // ... tới hôm nay
  ],
  "lessons_completed": 4,
  "lessons_total": 12,
  "completion_pct": 33            // int, làm tròn; 0 khi lessons_total = 0
}
```

- **Streak** tính trong Python từ tập `distinct activity_date` (chỉ những ngày có dòng
  `daily_activity` — tức có làm ít nhất 1 câu; đây là đơn vị "ngày học" nhất quán với leaderboard).
  Mọi so sánh dùng **ngày VN** qua `vn_today()`:
  - `current_streak`: số ngày liên tiếp **kết thúc đúng hôm nay** (VN). Nếu ngày gần nhất ≠ hôm
    nay → 0 (qua 0h chưa học là mất — theo yêu cầu). Đếm ngược từ hôm nay, ngắt khi hụt 1 ngày.
  - `longest_streak`: run liên tiếp dài nhất trong toàn bộ lịch sử.
  - Tính bằng cách sắp ngày tăng dần, duyệt, ngắt run khi khoảng cách > 1 ngày. Không dùng SQL
    window function để giữ logic ở một chỗ, dễ test đơn vị.
- **weekly_questions**: lấy các dòng `daily_activity` trong 7 ngày gần nhất, map theo `date`, rồi
  zero-fill đủ 7 ngày (hôm nay − 6 … hôm nay). Mốc "hôm nay" = `vn_today()` (khớp cách ghi mới).
- **Bài học**: `lessons_total = count(lessons where user_id)`;
  `lessons_completed = count(lesson_progress where user_id and status='done')`.
  `completion_pct = round(100 * completed / total)` (0 nếu total = 0).

**`GET /api/dashboard/leaderboard`** → xếp hạng cả nhóm:

```jsonc
[
  {"user_id":"...", "display_name":"An", "avatar_url":null,
   "active_days":7, "lessons_completed":5, "total_questions_done":30, "is_me":true},
  ...
]
```

- Đọc `leaderboard_view` qua `db.admin()`, `order by active_days desc, lessons_completed desc,
  total_questions_done desc` (tie-break ổn định). Gắn `is_me = (user_id == current user)`.
- Trả cả nhóm (<10 dòng) — client tô đậm dòng của mình.
- Không lộ email; chỉ `display_name`/`avatar_url` như view đã giới hạn.

### 2. Migration `0009_leaderboard_active_days.sql`

`leaderboard_view` hiện **fan-out**: join `lesson_progress` **và** `daily_activity` trong cùng một
truy vấn → `sum(questions_done_count)` bị nhân lên theo số bài done. Viết lại, tổng hợp **mỗi bảng
riêng** bằng subquery (không cross-join), và thêm `active_days`:

```sql
-- 0009_leaderboard_active_days.sql
-- Rank leaderboard by number of distinct study days (#6). Also fixes a fan-out bug in
-- 0004: joining lesson_progress AND daily_activity in one query multiplied
-- sum(questions_done_count) by the done-lesson count. Aggregate each private table in its
-- own subquery so counts are independent.
--
-- SECURITY NOTE (intentional, same as 0004): created WITHOUT security_invoker so it reads
-- all users' rows past RLS to build a cross-user leaderboard. It exposes ONLY aggregates
-- (display_name, avatar_url, lessons_completed, total_questions_done, active_days) — never
-- answer text, feedback, chat, or document content. Supabase's "security definer view"
-- linter warning is expected and accepted.

create or replace view leaderboard_view as
select
  up.id as user_id,
  up.display_name,
  up.avatar_url,
  coalesce(lp.lessons_completed, 0)    as lessons_completed,
  coalesce(da.total_questions_done, 0) as total_questions_done,
  coalesce(da.active_days, 0)          as active_days
from user_profiles up
left join (
  select user_id, count(distinct lesson_id) as lessons_completed
  from lesson_progress where status = 'done' group by user_id
) lp on lp.user_id = up.id
left join (
  select user_id,
         count(distinct activity_date) as active_days,
         sum(questions_done_count)     as total_questions_done
  from daily_activity group by user_id
) da on da.user_id = up.id;

grant select on leaderboard_view to authenticated;
```

- `create or replace view` giữ nguyên GRANT nhưng ta grant lại cho chắc.
- Không migration nào khác cần: các bảng + RLS đã có từ trước.

### 3. Frontend — `pages/Dashboard.tsx` (thay `Home.tsx`)

Đổi import trong `App.tsx`: `Home` → `Dashboard` cho route `/*`. Xóa `Home.tsx` (thay hẳn).

Bố cục (một cột, `max-w-…` như các trang khác, tiếng Việt toàn bộ):

1. **Header**: lời chào + email; nav sang **Bài học** (`/lessons`), **Tài liệu của tôi**
   (`/files`), **Tài khoản** (`/account`); nút **Đăng xuất** *tử tế* — bắt lỗi `signOut()` và
   hiện thông báo tiếng Việt nếu lỗi (khắc phục món nợ "Home nuốt lỗi signOut").
2. **Thẻ thống kê** (3 thẻ): Streak hiện tại 🔥 (`current_streak` ngày), Streak dài nhất
   (`longest_streak`), % hoàn thành (`completion_pct`% kèm `x/y` bài).
3. **BarChart** (Recharts `ResponsiveContainer` + `BarChart`): "Câu hỏi đã làm 7 ngày qua", trục
   X nhãn ngày tiếng Việt ngắn (T2…CN hoặc dd/MM), trục Y số câu; dữ liệu `weekly_questions`.
4. **Bảng xếp hạng**: cột Hạng · Tên · Số ngày học · Bài xong · Câu hỏi. Dòng của mình
   (`is_me`) tô nền nổi bật. Bảng HTML thuần + Tailwind (không cần thư viện bảng).

- Trạng thái **loading** và **lỗi** riêng cho từng khối, thông báo tiếng Việt; gọi qua `apiFetch`
  (đã bọc lỗi mạng → tiếng Việt). Hai fetch (`/me`, `/leaderboard`) độc lập, lỗi cái này không
  chặn cái kia.
- `lib/dashboard.ts`: kiểu TS cho hai payload + hai hàm gọi `apiFetch`.

## Xử lý lỗi

- Backend: truy vấn Supabase lỗi → để FastAPI trả 500 (không nuốt). Không có phần AI nên không có
  nhánh 502. Route riêng tư luôn `Depends(get_current_user)` → thiếu/hỏng token = 401.
- Bài của người khác không áp dụng ở đây (dashboard chỉ đọc dữ liệu của chính user + view tổng hợp).
- Frontend: mỗi khối tự chịu lỗi, hiển thị "Không tải được …" tiếng Việt, không làm trắng cả trang.

## Kiểm thử

**Backend `pytest`** (phải xanh + output sạch — gồm cả **cập nhật test #4** `test_quiz_*` cho mốc
ngày VN: các test đang gắn ngày UTC vào `daily_activity` phải đổi kỳ vọng sang `vn_today()`):
- `test_dashboard_repo.py`: logic thuần (inject "hôm nay" để test tất định, không phụ giờ chạy) —
  - streak: chuỗi liền kết đúng hôm nay → `current` đúng; **kết ở hôm qua → `current`=0** (qua 0h
    mất); kết < hôm nay → 0; `longest` là run dài nhất kể cả khi `current`=0; tập rỗng → 0/0; một
    ngày = hôm nay → 1/1.
  - weekly zero-fill: đúng 7 phần tử, thứ tự cũ→mới, ngày trống = 0, khớp count ngày có dữ liệu.
  - completion: total=0 → 0%; làm tròn đúng.
  - `vn_today`/`vn_date_of`: một timestamp 6h sáng VN (23h UTC hôm trước) → ngày VN là hôm nay,
    không phải hôm qua (chốt đúng biên UTC+7).
- `test_dashboard_api.py`: hai endpoint qua `TestClient` với `_Repo` fake (như các test router
  khác) — shape payload, `is_me` gắn đúng, thứ tự xếp hạng theo `active_days` giảm dần + tie-break,
  401 khi thiếu auth.

**SQL**: apply `0009` lên Supabase thật; xác minh view trả `active_days` đúng và
`total_questions_done` **không còn bị nhân** (so với một user có nhiều bài done + nhiều ngày hoạt
động).

**Frontend**: `npm run build` + `oxlint` sạch.

**Verify thật** `backend/scripts/verify_6.py` (khuôn như `verify_5.py`, session mint trong tiến
trình, HTTP thật + Supabase thật):
- `GET /api/dashboard/me` → streak/weekly/completion khớp dữ liệu seed tạm; zero-fill đúng 7 ngày.
- `GET /api/dashboard/leaderboard` → có dòng của user, `is_me=true`, xếp theo số ngày học.
- Dọn sạch mọi dòng seed script tạo, tài khoản về nguyên trạng.
- **Kiểm trình duyệt (thủ công)**: 3 thẻ, BarChart 7 cột, bảng xếp hạng tô đậm dòng mình, nav +
  đăng xuất chạy; F5 giữ nguyên.

## Ngoài phạm vi (YAGNI)

- Không đo **giờ học** (D15 — web không đo đáng tin).
- Không lọc/đổi khoảng thời gian biểu đồ (cố định 7 ngày).
- Không avatar upload; `avatar_url` render nếu có, bỏ qua nếu null.
- Không phân trang leaderboard (nhóm < 10).
- Không realtime; fetch một lần khi vào trang.

## Quyết định (ghi vào project_context khi build)

- **D-dash-1** Xếp hạng theo số ngày học (`count(distinct activity_date)`), không theo điểm.
- **D-dash-2** Recharts thay Tremor vì Tailwind v4 + React 19.
- **D-dash-3** Dữ liệu dashboard qua backend (D21); leaderboard cũng đọc view phía server.
- **D-dash-4** Sửa fan-out của `leaderboard_view` (0004) bằng subquery tổng hợp riêng từng bảng.
- **D-dash-5** Mốc ngày = **giờ VN (UTC+7)**, thống nhất cả nơi ghi (`quiz.py` #4 dùng `vn_today`)
  lẫn nơi đọc; streak hiện tại reset về 0 khi qua 0h VN mà chưa học.
