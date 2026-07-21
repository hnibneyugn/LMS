# Spec — #3 Lessons UI (đọc bài + tiến độ)

Ngày: 2026-07-20 · Sub-project: **#3** · Trạng thái: đã duyệt thiết kế, chờ plan

## 1. Mục tiêu

Sau #1a/#1b, người dùng upload tài liệu và duyệt chương, kết quả ghi vào bảng `lessons`. Nhưng
**chưa có chỗ nào đọc được bài học đó**. #3 lấp đúng khoảng trống ấy: danh sách bài, trang đọc, và
đánh dấu đã học.

## 2. Phạm vi

**Trong phạm vi**
- `GET /api/lessons` — danh sách bài của chính user
- `GET /api/lessons/{slug}` — nội dung một bài + điều hướng chương trước/sau
- `PUT /api/lessons/{id}/progress` — bật/tắt "Đã học" (`lesson_progress`)
- Trang `/lessons` (nhóm theo file nguồn, bộ lọc trạng thái học)
- Trang `/lessons/:slug` (render markdown, checkbox Đã học, prev/next)

**Ngoài phạm vi** (thuộc sub-project khác)
- Sidebar chat Socratic → #5
- Câu hỏi tự luận do AI sinh + chấm điểm → #4a/#4
- `topic` / `week` và bộ lọc theo chủ đề → xem §3
- Xoá/sửa bài học, tìm kiếm toàn văn

Checklist gốc mô tả `/lessons/:slug` gồm "render markdown + sidebar chat + câu hỏi tự luận". Hai
phần sau bị chặn bởi việc **chưa chốt model chat Gemini**, nên tách ra. #3 **không dựng khung giả**
("Sắp có…") cho chúng — khung giả dựng trước API thật gần như luôn phải viết lại.

## 3. Quyết định thiết kế

### D20 — Nhóm theo file nguồn, không theo `topic`

Checklist yêu cầu "tab lọc Chủ đề", nhưng `_build_lesson_rows` trong
`backend/app/routers/files.py` chỉ ghi `user_id`, `source_file_id`, `title`, `slug`, `content_md`,
`order_index`. **`lessons.topic` và `lessons.week` luôn NULL** — không có dữ liệu để lọc.

Trục phân nhóm có thật là `source_file_id` + `order_index`, đúng mô hình "cuốn sách → chương" mà
#1a/#1b đã dựng. Nên `/lessons` nhóm theo file nguồn. Không cần migration, không cần user nhập tay.

`lessons.source_file_id` khai báo `on delete set null`, nên bài có thể mồ côi — gom vào nhóm
**"Khác"** đặt cuối danh sách.

### D21 — Dữ liệu đi qua backend, không đọc thẳng Supabase

RLS `lessons_own` cho phép frontend đọc `lessons` trực tiếp bằng anon key, và như thế sẽ ít code
hơn. Vẫn chọn đi qua backend vì:

- `CLAUDE.md` quy định mọi lời gọi backend đi qua `apiFetch()`; hai đường vào dữ liệu song song
  (đọc bằng anon key, ghi bằng service role) là mầm mống lệch quy tắc về sau.
- #4a (sinh câu hỏi), #5 (chat), #6 (streak/leaderboard) **bắt buộc** có backend. Dựng
  `routers/lessons.py` từ bây giờ thì các sub-project sau chỉ việc mở rộng.

### D22 — Backend trả danh sách phẳng, frontend gom nhóm

`GET /api/lessons` trả một mảng phẳng kèm `source_file_id` + `source_file_name`; việc gom nhóm là
quyết định trình bày, để ở frontend. Router mỏng, một request duy nhất cho cả trang, và khi #6 cần
đếm tiến độ thì dùng lại đúng endpoint này.

### D23 — `react-markdown`, không bật HTML thô

Nội dung `content_md` do extractor sinh từ file người dùng upload. `react-markdown` mặc định
**không** render HTML thô; #3 giữ nguyên mặc định đó (không dùng `rehype-raw`), nên không có đường
tiêm HTML qua tài liệu. Thêm `remark-gfm` cho bảng và danh sách checkbox.

Class `prose` cần `@tailwindcss/typography`; dự án dùng Tailwind v4 nên khai báo bằng
`@plugin "@tailwindcss/typography";` trong file CSS chính, không qua `tailwind.config`.

## 4. Backend — `app/routers/lessons.py`

Theo đúng khuôn `files.py`: một class `_Repo` mỏng dùng `db.admin()` (service role, bypass RLS) và
**mọi truy vấn lọc `user_id` tường minh**; `user_id` lấy từ JWT qua `Depends(get_current_user)`,
không bao giờ nhận từ client. Truy cập bài của người khác trả **404** chứ không 403 — giống #1a, để
không lộ sự tồn tại của tài nguyên.

### 4.1 `GET /api/lessons`

Trả `list[LessonListOut]`, sắp theo `(source_file_name, order_index)`:

```
{
  id: str, slug: str, title: str, order_index: int,
  source_file_id: str | null,
  source_file_name: str | null,     # null khi file nguồn đã bị xoá
  done: bool,
  completed_at: str | null
}
```

`done` lấy từ `lesson_progress` (`status = 'done'`). Bài chưa có dòng nào trong `lesson_progress`
→ `done = false`. Đọc `lessons` và `lesson_progress` riêng rồi ghép trong Python — supabase-py
không diễn đạt gọn được LEFT JOIN, và tập dữ liệu ở quy mô này (< 10 người, vài trăm bài) không
đáng để tối ưu.

### 4.2 `GET /api/lessons/{slug}`

Slug chỉ unique trong phạm vi một user (`lessons_user_slug_idx`), nên tra bằng
`(user_id, slug)`. Trả:

```
{
  id, slug, title, content_md, order_index,
  source_file_id, source_file_name, done, completed_at,
  prev: { slug, title } | null,
  next: { slug, title } | null
}
```

`prev`/`next` là chương liền kề **trong cùng `source_file_id`**, theo `order_index`. Bài mồ côi
(`source_file_id` null) có cả hai là null. Không tìm thấy → 404 `"Không tìm thấy bài học."`.

### 4.3 `PUT /api/lessons/{id}/progress`

Body `{ done: bool }`. Kiểm bài thuộc về user (không thì 404), rồi upsert vào `lesson_progress`
theo khoá `(user_id, lesson_id)`:

- `done = true` → `status = 'done'`, `completed_at = now()`
- `done = false` → `status = 'not_done'`, `completed_at = null`

Trả `{ done, completed_at }` để client đồng bộ lại trạng thái thật.

Ghi `daily_activity` **không** làm ở đây — đó là việc của #6, và đọc bài không phải "hoạt động
học" theo nghĩa #6 đo (số ngày có trả lời câu hỏi).

### 4.4 Đăng ký router

`app/main.py` `include_router(lessons.router)`, cạnh `files`.

## 5. Frontend

### 5.1 `src/lib/lessons.ts`

Wrapper quanh `apiFetch`, cùng khuôn `lib/files.ts`: export interface `Lesson`, `LessonDetail`,
`LessonNav`, và hàm `listLessons()`, `getLesson(slug)`, `setLessonProgress(id, done)`.

Tái dùng `errorMessage()` đã có trong `lib/files.ts` (không viết bản thứ hai).

### 5.2 `src/pages/Lessons.tsx` — `/lessons`

- Gom bài theo `source_file_id`; tiêu đề nhóm là `source_file_name`, kèm tiến độ `x/y`.
  Nhóm `null` hiển thị tên **"Khác"** và xếp cuối.
- Bộ lọc *Tất cả / Chưa học / Đã học* — lọc phía client trên dữ liệu đã tải.
- Mỗi dòng: tiêu đề (link tới `/lessons/{slug}`) + dấu hiệu đã học.
- Chưa có bài nào → trạng thái rỗng: *"Chưa có bài học nào. Hãy tải tài liệu lên."* + link `/files`.
- Lỗi tải → thông báo tiếng Việt + nút thử lại.

### 5.3 `src/pages/LessonDetail.tsx` — `/lessons/:slug`

- Header: link quay lại `/lessons`, tên file nguồn, tiêu đề bài, checkbox **"Đã học"**.
- Thân bài: `<article class="prose">` render `content_md` bằng `react-markdown` + `remark-gfm`,
  giới hạn bề ngang cho dễ đọc.
- Cuối bài: điều hướng `← chương trước` / `chương sau →` (ẩn khi null).
- Slug lạ / 404 → *"Không tìm thấy bài học."* + link về `/lessons`.
- Bọc nội dung trong một container để #5 chỉ cần thêm cột phải cho chat — **không dựng cột rỗng ở
  #3**.

### 5.4 Checkbox tiến độ

Cập nhật **lạc quan**: đổi UI ngay, gọi `PUT` nền, hỏng thì trả lại trạng thái cũ và hiện lỗi
tiếng Việt. Khoá checkbox trong lúc request đang chạy để không gửi chồng nhau.

### 5.5 Routing & điều hướng

`App.tsx` thêm `/lessons` và `/lessons/:slug`, cả hai bọc `ProtectedRoute`. Thêm link "Bài học"
vào `Home` và `Files` để trang mới có lối vào (Home vẫn là placeholder, sẽ thay ở #6).

## 6. Xử lý lỗi

`apiFetch` đã bọc lỗi mạng thành tiếng Việt (commit `6078dfa`), nên #3 không lặp lại việc đó —
chỉ hiển thị `errorMessage(err)`.

| Tình huống | Hành vi |
|---|---|
| Chưa đăng nhập | `ProtectedRoute` đẩy về `/login`; API trả 401 |
| Slug không tồn tại / của người khác | 404 → trang "Không tìm thấy bài học." |
| Backend tắt | "Không kết nối được máy chủ." (đã có sẵn) |
| `PUT` progress hỏng | Hoàn tác UI + báo lỗi, không mất trạng thái thật |

## 7. Verify

**Tự động**
- `pytest` từ `backend/` — xanh và **output sạch**. Ca cần có: danh sách chỉ trả bài của mình;
  ghép `done` đúng; bài của user khác → 404; `{slug}` lạ → 404; `prev`/`next` null ở đầu/cuối file
  và ở bài mồ côi; upsert progress bật rồi tắt; thiếu token → 401.
- `npm run build` từ `frontend/` — không lỗi TypeScript.

**Thật (script kiểu `backend/scripts/verify_1b.py`, HTTP thật + Supabase thật)**
- `GET /api/lessons` trả đúng số bài của tài khoản thật, nhóm khớp file nguồn
- Mở một bài qua `{slug}` → `content_md` khớp DB, `prev`/`next` đúng thứ tự chương
- `PUT` progress true → `lesson_progress` có dòng `done` + `completed_at`; PUT false → về
  `not_done` + `completed_at` null
- **RLS thật**: anon key chưa đăng nhập đọc `lesson_progress` ra **0 dòng**
- Dọn sạch dữ liệu tạo lúc verify

**Chỉ trình duyệt kiểm được** (ghi lại vào `check_list.md`, không cố tự động hoá): render markdown
thực tế của bài `.docx`/`.pdf` đã cắt, bộ lọc, và cập nhật lạc quan của checkbox.

## 8. Dependency mới

| Gói | Vì sao |
|---|---|
| `react-markdown` | Render `content_md`; mặc định chặn HTML thô |
| `remark-gfm` | Bảng, checklist, strikethrough trong markdown trích xuất |
| `@tailwindcss/typography` | Class `prose` cho thân bài |

Không thêm dependency backend.
