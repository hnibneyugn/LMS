# Spec — #1b: UI upload + duyệt chương

Ngày: 2026-07-19 · Sub-project **#1b** · Trạng thái: chờ implement

## 1. Bối cảnh

#1a đã làm xong nửa backend của luồng ingest: từ file trên R2 ra được `user_files.draft_outline`
(danh sách chương nháp), trạng thái dừng ở `ready_for_review`. Chưa có UI nào, và chưa có đường
nào ghi vào bảng `lessons`.

#1b khép kín vòng đó: user upload được từ trình duyệt, theo dõi được tiến trình xử lý, duyệt/sửa
danh sách chương nháp, rồi xác nhận để sinh ra bài học thật.

Ngoài ra #1a để lại một phát hiện từ dữ liệu thật: tài liệu Word tiếng Việt thường **không gán
heading style** (file mẫu có 110/114 đoạn là `Normal`), khiến 19k ký tự đầu bị cắt cứng thành 3 cục
"Mở đầu (1)(2)(3)". #1b sửa gốc vấn đề này bằng heuristic ở extractor.

## 2. Phạm vi

**Trong phạm vi:**
- Endpoint `POST /api/files/{file_id}/confirm` → ghi `lessons`, đặt file thành `done`
- Chốt ngữ nghĩa `/process` trên file `done` (nợ kỹ thuật #1a)
- `response_model` whitelist cho `GET /api/files*` (nợ kỹ thuật #1a)
- Heuristic nhận diện heading đánh số trong `.docx`
- Trang `/files` — upload + danh sách + poll trạng thái + nút xử lý lại
- Trang `/files/:id/review` — sửa tên / gộp / bỏ chương → xác nhận

**Ngoài phạm vi:**
- Sửa nội dung markdown của chương (chỉ tên/gộp/bỏ)
- Tách một chương thành hai (thay bằng heuristic ở mục 5)
- Lưu nháp chỉnh sửa qua F5
- Xoá file / xoá bài học
- Hạ tầng test frontend (repo chưa có; dựng riêng, không nhét vào #1b)
- Trang `/lessons` hiển thị bài học (thuộc #3)

## 3. Quyết định thiết kế

| # | Quyết định | Lý do |
|---|---|---|
| B1 | Trang duyệt chỉ cho **sửa tên / gộp / bỏ** | Đúng phạm vi checklist. Sửa markdown thô là việc user không muốn làm. |
| B2 | `confirm` nhận **lệnh**, không nhận nội dung | Client gửi `{title, source_indexes[]}`; server dựng `content_md` từ `draft_outline` trong DB. Nội dung bài học không đi qua client, payload nhỏ. |
| B3 | `done` là chốt hạ, nhưng **xem lại được** | `/process` và `/confirm` trên file `done` → 409. Trang review vẫn mở được ở chế độ chỉ đọc. Bảo vệ `quiz_attempts` trỏ vào `lessons`. |
| B4 | Không cho tách chương, thay bằng **heuristic ở extractor** | Cắt nhỏ quá thì gộp lại được; cắt to quá thì bó tay. Sửa ở gốc lợi cho mọi file sau. |
| B5 | Không lưu nháp chỉnh sửa | F5 quay về `draft_outline` gốc. Hệ quả có ý thức của B2; nếu phiền thì thêm `sessionStorage` sau, không phải đổi API. |

## 4. Backend

### 4.1 `POST /api/files/{file_id}/confirm`

```
req:  { chapters: [ { title: str, source_indexes: [int] } ] }
resp: { lesson_count: int }
```

`Depends(get_current_user)`. `user_id` luôn lấy từ JWT.

**Validate** (vi phạm → **400**, thông báo tiếng Việt):
- `chapters` không rỗng
- `title` sau khi trim dài 1–200 ký tự
- mỗi `source_indexes` không rỗng, mọi phần tử là index hợp lệ trong `draft_outline`
- không index nào xuất hiện ở hai chương khác nhau (bỏ được, trùng thì không)
- trong một chương, các index phải **tăng dần** (không cần liền kề) và không index nào bị
  lặp lại — không liền kề cũng được vì nếu bắt liền kề thì user bỏ một chương ở giữa sẽ không
  thể gộp lại hai chương hai bên khoảng trống đó

**Kiểm tra trạng thái:**

| Trạng thái file | Kết quả |
|---|---|
| `ready_for_review` | chạy tiếp |
| `pending` / `processing` | **409** "File chưa xử lý xong." |
| `error` | **409** "File xử lý lỗi — hãy xử lý lại trước khi duyệt." |
| `done` | **409** "File đã được duyệt." |
| không thuộc user gọi / không tồn tại | **404** "Không tìm thấy file." (không bao giờ 403) |

**Ghi `lessons`** — mỗi phần tử `chapters` thành một dòng:

| Cột | Giá trị |
|---|---|
| `user_id` | từ JWT |
| `source_file_id` | `file_id` |
| `title` | `title` đã trim |
| `content_md` | `"\n\n".join(draft_outline[i]["content_md"] for i in source_indexes)` |
| `order_index` | đánh lại từ 0 theo thứ tự mảng `chapters` |
| `slug` | xem 4.2 |
| `topic`, `week` | NULL |

Insert cả mẻ trong **một** lần gọi, **xong mới** `set_status(file_id, user_id, "done")`. Thứ tự này
quan trọng: insert lỗi thì file vẫn `ready_for_review` và duyệt lại được, không để lại `lessons` mồ côi.

### 4.2 Slug

`slug = slugify(tên file bỏ đuôi) + "-" + order_index`, bỏ dấu tiếng Việt, hạ chữ thường, ký tự
không phải chữ/số thành `-`, gom nhiều `-` liền nhau thành một, cắt còn 80 ký tự.

Unique là `(user_id, slug)` (migration `0006`). Hai file **cùng tên** của cùng một user sẽ đụng nhau,
nên trước khi insert phải đọc các slug đã tồn tại của user và thêm hậu tố ngắn (`-2`, `-3`) cho
những cái trùng. Tên file toàn ký tự lạ → slug rỗng → dùng `bai-{order_index}`.

### 4.3 Sửa `/process` (nợ kỹ thuật #1a)

Hiện tại `/process` gọi trên file `ready_for_review`/`done` sẽ ghi đè `draft_outline` không hỏi gì.
Chốt lại: trạng thái `done` → **409** "File đã được duyệt." Trạng thái `ready_for_review` vẫn cho
chạy lại (user muốn cắt lại từ đầu trước khi duyệt là hợp lý).

### 4.4 `response_model` cho `GET /api/files*` (nợ kỹ thuật #1a)

Hai endpoint đang trả `select("*")`, lộ `storage_path` và `user_id`. Thêm model whitelist:

```
FileOut: id, file_name, file_type, file_size, processing_status,
         error_message, uploaded_at, chapter_count
```

`chapter_count` = `len(draft_outline)` nếu có, không thì `null` — để `/files` hiện "N chương" mà
không phải tải cả `draft_outline` cho từng dòng.

`GET /api/files/{id}` dùng model riêng `FileDetailOut` = `FileOut` + `draft_outline` (trang review
cần nội dung chương). `GET /api/files` dùng `list[FileOut]`, không kèm `draft_outline`.

## 5. Heuristic heading trong `.docx`

Sửa ở `backend/app/ingest/extractors/docx.py`, **không** ở `splitter.py` — splitter chỉ ăn markdown,
giữ nguyên ranh giới trách nhiệm đã có từ #1a.

Một đoạn style `Normal` được nâng thành heading khi thỏa **tất cả**:
- dài ≤ 120 ký tự
- không kết thúc bằng `.` `,` `;` `:`
- không phải list item
- khớp một trong các mẫu đầu dòng:
  - chữ: `Chương N`, `Bài N`, `Phần N`, `Mục N`, `Chapter N`
  - La Mã: `I.` `II.` `III.` …
  - số phân cấp: `1.` `1.1` `1.1.1` (có hoặc không dấu chấm cuối)

**Cấp heading**: mẫu số phân cấp suy theo độ sâu — `1.` → `##`, `1.1` → `###`, `1.1.1` → `####`.
Mẫu chữ và La Mã luôn `##`.

**Đánh đổi đã cân nhắc**: danh sách đánh số kiểu "1. Điều thứ nhất là…" có thể bị nhận nhầm thành
heading. Ràng buộc ≤120 ký tự + không kết thúc bằng dấu câu chặn phần lớn; phần lọt lưới thì user
gộp lại được ở trang duyệt. Chấp nhận, vì cắt nhỏ quá sửa được còn cắt to quá thì không.

Tài liệu **có sẵn** Heading style thật vẫn chạy heuristic, nhưng heading thật vốn đã ra `#`/`##`/`###`
nên chương cấp cao nhất không đổi — heuristic chỉ làm giàu thêm cấp dưới, có lợi khi splitter phải
cắt tiếp chương vượt 8000 ký tự.

## 6. Frontend

### 6.1 `/files` — upload + danh sách

**Upload**: dropzone gọn trên đỉnh (click chọn hoặc kéo thả). Luồng:

1. validate đuôi file + kích thước ≤20MB **ngay tại client**, sai thì không gọi API
2. `POST /api/files/presign` (qua `apiFetch`)
3. `PUT` thẳng lên R2 bằng `fetch` **trần** — presigned URL không được mang header
   `Authorization`, gắn vào là hỏng chữ ký. Đây là chỗ duy nhất trong codebase không dùng `apiFetch`.
4. `POST /api/files/{id}/process`

Hiện tiến độ từng bước bằng chữ tiếng Việt ("Đang tải lên…", "Đang xử lý…"), không dựng progress
bar giả.

**Danh sách**: mới nhất trước. Mỗi dòng gồm tên file, kích thước, thời gian, badge trạng thái, và
một hành động chính:

| Trạng thái | Hiển thị | Hành động |
|---|---|---|
| `pending` | "Chưa xử lý" | "Xử lý" |
| `processing` | "Đang xử lý…" | không có — trừ khi quá 10 phút thì hiện "Xử lý lại" |
| `ready_for_review` | "Chờ duyệt · N chương" | "Duyệt chương" |
| `error` | `error_message` (đỏ) | "Xử lý lại" |
| `done` | "Đã duyệt" | "Xem lại" |

Ngưỡng 10 phút tính từ `uploaded_at` — schema không có cột ghi thời điểm bắt đầu xử lý, và thêm cột
chỉ để phục vụ một nút "xử lý lại" là thừa. Hệ quả: file upload xong nhưng để đó vài giờ rồi mới
bấm "Xử lý" sẽ hiện nút "Xử lý lại" ngay lập tức. Vô hại — bấm vào chỉ nhận 409 "File đang được xử
lý" rồi UI refetch. Xử lý ca backend restart giữa chừng (rủi ro đã ghi nhận ở spec #1a mục 8).

**Poll**: `GET /api/files` mỗi **3 giây**, chỉ chạy khi danh sách còn ít nhất một file `processing`,
tự dừng khi không còn, và dừng khi tab ẩn (`visibilitychange`) — không để tab bỏ quên gọi API vô hạn.

### 6.2 `/files/:id/review` — duyệt chương

Danh sách dọc các chương nháp. Mỗi thẻ:
- ô input tiêu đề
- số ký tự nội dung
- 3 dòng đầu nội dung, thu gọn, bấm để mở rộng
- nút `Gộp với chương trên` (ẩn ở thẻ đầu tiên)
- nút `Bỏ chương này`

**State client** là mảng `{ title, source_indexes }` — đúng hình dạng payload gửi đi, nên không cần
tầng chuyển đổi lúc submit.

- **Gộp**: trộn `source_indexes` của thẻ hiện tại vào thẻ ngay trên, giữ tiêu đề thẻ trên, xoá thẻ hiện tại.
- **Bỏ**: xoá khỏi mảng, kèm `Hoàn tác` một cấp ngay tại chỗ — thao tác này mất dữ liệu nên phải có đường lùi.
- **Sửa tên**: gõ trực tiếp vào input.

Đáy trang là thanh dính: "Sẽ tạo N bài học" + nút `Xác nhận`. Xác nhận thành công → điều hướng về
`/files`, file đã thành `done`.

**Chế độ chỉ đọc** (file `done`): mở được, input khoá, không có nút gộp/bỏ/xác nhận, hiện dòng
"File đã duyệt xong".

**Không lưu nháp**: F5 mất chỉnh sửa, quay về `draft_outline` gốc (B5).

### 6.3 Điều hướng

Thêm link tới `/files` ở `Home.tsx`. Cả hai route mới bọc trong `ProtectedRoute`.

## 7. Xử lý lỗi phía frontend

Mỗi bước hỏng có thông báo riêng, không nuốt lỗi, và luôn có đường làm lại:

| Hỏng ở đâu | Người dùng thấy | Trạng thái để lại |
|---|---|---|
| Sai định dạng / quá 20MB | Chặn tại client, không gọi API | không tạo bản ghi |
| `presign` 4xx/5xx | "Không tạo được đường tải lên. Thử lại." | không có bản ghi |
| `PUT` R2 hỏng | "Tải file lên thất bại." + nút "Thử lại" | bản ghi `pending`; bấm "Xử lý" sẽ ra `error` "Chưa thấy file trên kho lưu trữ" — đúng thông điệp có sẵn từ #1a |
| `process` 503 | "Kho lưu trữ tạm thời không khả dụng." | `pending`, thử lại được |
| `process` 409 | refetch danh sách để đồng bộ UI | không đổi |
| `confirm` 409 | đọc `detail` từ backend, refetch file | không đổi |
| `confirm` 400 | đọc `detail` từ backend, giữ nguyên chỉnh sửa | không đổi |

Mọi lỗi hiện bằng tiếng Việt và **ưu tiên `detail` của backend** thay vì tự chế câu mới.

## 8. Test

### Backend (`pytest`, phải xanh và output sạch)

`confirm`:
- đường hạnh phúc: ghi đúng N `lessons`, `order_index` 0..N-1, `content_md` nối đúng thứ tự
- gộp nhiều chương → một `lessons` có nội dung của cả hai, ngăn bằng `\n\n`
- bỏ chương → chương đó không có trong `lessons`
- 400: index lạ · index trùng ở hai chương · index giảm dần trong một chương · `chapters` rỗng · title rỗng · title >200
- 409: `pending` · `processing` · `error` · `done`
- 404: file của user khác
- insert `lessons` lỗi → file vẫn `ready_for_review`, không sót `lessons`
- slug: hai file cùng tên của cùng user không đụng unique constraint

`/process`:
- file `done` → 409

`docx` heuristic:
- toàn `Normal` với `Chương 1..3` → 3 chương
- list đánh số dài → không bị cắt vụn thành heading
- có Heading style thật → kết quả chương cấp cao nhất không đổi (hồi quy)

### Frontend

`npm run build` sạch TypeScript. Không dựng test runner cho #1b.

### Verify thật (bắt buộc — không kết luận "xong" chỉ dựa vào pytest)

Dùng lại chính file `.docx` 6MB và `.pdf` 30 trang đã verify ở #1a:
- upload qua UI thật → trạng thái tự chuyển `pending` → `processing` → `ready_for_review` không cần F5
- vào trang duyệt, gộp + đổi tên + bỏ vài chương, xác nhận
- kiểm tra bảng `lessons` trên Supabase thật: đúng số dòng, nội dung chương gộp đúng, `order_index` liên tục
- `.docx` không heading style → verify heuristic ra nhiều chương thay vì 3 cục "Mở đầu"
- file `error` → bấm "Xử lý lại" chạy được
- RLS: anon key đọc `lessons` ra 0 dòng

## 9. Định nghĩa hoàn thành

- [ ] `POST /api/files/{id}/confirm` chạy, validate đủ 5 quy tắc, sai quyền → 404
- [ ] `/process` trên file `done` → 409
- [ ] `GET /api/files*` không còn lộ `storage_path`/`user_id`
- [ ] Heuristic docx có test, gồm test hồi quy cho file có heading thật
- [ ] `/files` upload được end-to-end, poll tự dừng đúng lúc
- [ ] `/files/:id/review` sửa tên / gộp / bỏ / hoàn tác chạy đúng; `done` là chỉ đọc
- [ ] pytest xanh, output sạch · `npm run build` sạch
- [ ] Verify thật đủ 6 mục ở §8
- [ ] `check_list.md` cập nhật (gồm gạch 3 mục nợ kỹ thuật đã giải quyết)
