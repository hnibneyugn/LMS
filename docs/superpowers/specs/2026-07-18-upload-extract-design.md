# Spec — #1a: Upload tài liệu → Extract → Cắt chương

Ngày: 2026-07-18 · Sub-project **#1a** · Trạng thái: chờ implement

## 1. Bối cảnh

Dự án đổi hướng trong lúc brainstorm (xem D13/D16/D17 trong `project_context.md`): nội dung học
không còn do admin soạn trong Obsidian rồi sync qua GitHub, mà **mỗi user tự upload tài liệu của
mình để học**. Obsidian Git sync bị bỏ hẳn.

Một tài liệu upload lên có thể là cả một giáo trình vài trăm trang, nên "1 file = 1 bài học" không
dùng được: bài quá dài để đọc, và `content_md` vượt giới hạn prompt khi AI sinh câu hỏi (#4a). Vì
vậy một file được **cắt thành nhiều bài học**, mỗi bài về lại cỡ vài nghìn token.

Sub-project này làm **nửa backend**: từ file trên R2 ra được danh sách chương ở dạng nháp. Việc user
duyệt/sửa chương rồi ghi vào `lessons` thuộc **#1b**.

## 2. Phạm vi

**Trong phạm vi:**
- Migration `0006` cho `lessons` + `user_files`
- Cấu hình R2 (`boto3`) + endpoint xin presigned URL upload
- Endpoint đăng ký file đã upload + kích hoạt xử lý nền
- Extract 4 định dạng (`.md`, `.docx`, `.pptx`, `.pdf`) sang markdown
- Cắt markdown thành chương, lưu vào `user_files.draft_outline`
- Xử lý lỗi + cho phép retry

**Ngoài phạm vi:**
- Mọi UI (thuộc #1b)
- Ghi vào bảng `lessons` (thuộc #1b — pha confirm)
- Sinh câu hỏi bằng AI (thuộc #4a)
- OCR cho PDF scan/ảnh (hoãn — xem mục 8)
- RAG / `document_chunks` (vẫn hoãn theo D8)

## 3. Vòng đời một file

```
pending ──► processing ──► ready_for_review ──► done
                │                                 ▲
                └──► error ──(retry)──┘           └── (#1b ghi xong lessons)
```

| Trạng thái | Ý nghĩa |
|---|---|
| `pending` | Đã có bản ghi `user_files`, file đã nằm trên R2, chưa xử lý |
| `processing` | Đang extract/cắt trong background task |
| `ready_for_review` | Đã có `draft_outline`, chờ user duyệt ở #1b |
| `error` | Hỏng ở đâu đó; `error_message` giải thích bằng tiếng Việt; retry được |
| `done` | #1b đã ghi `lessons` xong |

#1a chịu trách nhiệm tới `ready_for_review`. Không bao giờ tự set `done`.

## 4. API

Tất cả đều `Depends(get_current_user)`. Không endpoint nào nhận `user_id` từ client — luôn lấy từ
JWT, để user A không thể thao tác trên file của user B.

### `POST /api/files/presign`
```
req:  { file_name: str, file_type: 'md'|'docx'|'pptx'|'pdf', file_size: int }
resp: { file_id: uuid, upload_url: str, storage_path: str }
```
Validate `file_size` ≤ 20MB và `file_type` hợp lệ **trước** khi ký. Tạo bản ghi `user_files` trạng
thái `pending`. `storage_path` = `{user_id}/{file_id}.{ext}` — tiền tố `user_id` để một key rò rỉ
cũng không suy ra được key của người khác. Presigned URL hết hạn **15 phút** (theo ràng buộc mục 6
`project_context.md`).

### `POST /api/files/{file_id}/process`
Frontend gọi sau khi `PUT` lên R2 xong. Kiểm tra file thuộc về user gọi (không thì **404**, không
phải 403 — tránh lộ sự tồn tại của file người khác). Kiểm tra object đã thật sự có trên R2
(`head_object`) — không có thì `error`. Đặt `processing`, đẩy việc vào `BackgroundTasks`, trả `202`
ngay.

Cho phép gọi lại khi trạng thái là `error` → đó chính là cơ chế retry. Gọi khi đang `processing` thì
trả **409**, tránh chạy song song hai lần trên cùng file.

### `GET /api/files/{file_id}`
Trả trạng thái + `draft_outline` (nếu có) + `error_message`. #1b poll endpoint này để biết xử lý
xong chưa.

### `GET /api/files`
Danh sách file của user, mới nhất trước.

## 5. Xử lý nền

```python
def process_file(file_id: UUID) -> None:
    # 1. tải bytes từ R2
    # 2. raw_md = EXTRACTORS[file_type](data)
    # 3. chapters = split_into_chapters(raw_md, file_type)
    # 4. lưu draft_outline + ready_for_review
    # bọc toàn bộ trong try/except -> error + error_message
```

Chạy bằng `BackgroundTasks` của FastAPI trong cùng process (D4) — quy mô <10 user không cần queue
riêng. Hệ quả phải chấp nhận: **backend restart giữa chừng thì file kẹt ở `processing`**. Xử lý ở
mục 8.

### 5.1 Extract — `backend/app/ingest/extractors/`

Mỗi định dạng một module, cùng chữ ký `extract(data: bytes) -> str`. Tách khỏi phần cắt để thêm
định dạng mới sau này chỉ phải viết đúng một hàm.

| Định dạng | Thư viện | Ghi chú |
|---|---|---|
| `.md` | `python-frontmatter` | Lấy `title`/`topic` từ frontmatter nếu có; body giữ nguyên |
| `.docx` | `python-docx` | Heading 1–3 → `#`/`##`/`###`; list → `-`; đoạn thường → dòng trống ngăn cách |
| `.pptx` | `python-pptx` | Mỗi slide → `## {tiêu đề slide}` + text các shape |
| `.pdf` | `pypdf` | `extract_text()` từng trang, nối bằng `\n\n` |

**PDF không có text layer** (scan/ảnh): sau khi extract mà tổng ký tự < 100 thì coi như thất bại,
set `error` với thông báo tiếng Việt gợi ý dùng bản có text. **Không** trả markdown rỗng hoặc rác.

### 5.2 Cắt chương — `backend/app/ingest/splitter.py`

```python
def split_into_chapters(md: str, file_type: str) -> list[Chapter]
```

Chỉ ăn markdown (trừ ca PDF không outline), nên test được độc lập hoàn toàn.

| Nguồn | Ranh giới |
|---|---|
| `.md`, `.docx` | Heading cấp cao nhất thực sự xuất hiện trong tài liệu (`#`, không có thì `##`) |
| `.pptx` | Mỗi slide = 1 chương |
| `.pdf` | Outline/bookmark nếu có; không có → cắt mỗi ~10 trang |

Quy tắc:
- Phần văn bản **trước** heading đầu tiên, nếu dài hơn 200 ký tự, thành chương "Mở đầu"; ngắn hơn
  thì gộp vào chương đầu.
- Chương dài hơn **8000 ký tự** bị cắt tiếp theo heading cấp dưới; vẫn dài thì cắt cứng theo đoạn
  văn. Trần này để `content_md` vừa prompt sinh câu hỏi ở #4a.
- Chương rỗng hoặc chỉ có khoảng trắng bị loại.
- Tài liệu không có heading nào → một chương duy nhất, `title` = tên file (đã bỏ đuôi).
- `title` chương = text của heading, cắt còn 200 ký tự.
- `order_index` đánh từ 0 theo thứ tự xuất hiện.

**Hình dạng `draft_outline`** (jsonb trong `user_files`):
```json
[{ "title": "Chương 1 — ...", "content_md": "...", "order_index": 0 }]
```

## 6. Migration `0006`

```sql
alter table lessons
  add column user_id uuid not null references auth.users(id) on delete cascade,
  add column source_file_id uuid references user_files(id) on delete set null,
  add column order_index int not null default 0;

alter table lessons drop constraint lessons_slug_key;
create unique index lessons_user_slug_idx on lessons (user_id, slug);

alter table lessons enable row level security;
create policy lessons_own on lessons for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

alter table user_files add column draft_outline jsonb;
-- nới CHECK: file_type thêm 'md'; processing_status thêm 'ready_for_review', 'done'
```

`lessons` hiện **rỗng** (chưa có luồng nào ghi vào), nên `user_id not null` thêm được trực tiếp,
không cần backfill. Cột `week` giữ nguyên nullable (D14), luôn NULL.

`source_file_id` dùng `on delete set null` chứ không `cascade`: xóa file gốc không được làm mất bài
học user đã học dở cùng toàn bộ `quiz_attempts` trỏ vào đó.

## 7. Biến môi trường mới

```
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=
```
Thêm vào `backend/.env.example`. **Xóa** `GITHUB_WEBHOOK_SECRET` khỏi kế hoạch — Obsidian sync đã bỏ.

Dependencies thêm vào `requirements.txt`: `boto3`, `python-frontmatter`, `python-docx`,
`python-pptx`, `pypdf`.

## 8. Rủi ro đã biết, chấp nhận có ý thức

| Rủi ro | Xử lý |
|---|---|
| Backend restart giữa lúc `processing` → file kẹt | Chấp nhận. #1b hiện nút "Xử lý lại" cho file `processing` quá 10 phút. Không dựng queue (D4). |
| PDF scan không đọc được | Báo lỗi rõ, không OCR. OCR nặng + D9 cấm dùng Gemini + chất lượng tiếng Việt kém. Làm sau nếu thực sự cần. |
| Cắt chương ra kết quả xấu với PDF cấu trúc lộn xộn | Đã có pha user duyệt ở #1b — máy cắt, người sửa. |
| `draft_outline` phình to với file lớn | Trần 8000 ký tự/chương giữ nó trong tầm kiểm soát. |
| DOCX/PPTX phức tạp (bảng, textbox, ảnh) mất định dạng | Chấp nhận đợt đầu; chỉ lấy text. |

## 9. Test

`backend/tests/` — pytest, phải xanh và **output sạch**.

**Unit (không cần mạng, không cần R2):**
- `splitter`: cắt theo `#`; fallback `##`; phần mở đầu dài → chương riêng; phần mở đầu ngắn → gộp;
  không heading → 1 chương lấy tên file; chương quá dài → cắt tiếp; loại chương rỗng; `order_index`
  đúng thứ tự
- mỗi extractor: một file mẫu nhỏ trong `tests/fixtures/`
- PDF không text layer → raise, thông báo tiếng Việt

**API (mock R2):**
- `presign` từ chối file > 20MB và định dạng lạ
- thao tác lên file của user khác → 404
- `process` khi đang `processing` → 409; khi `error` → chạy lại được
- extract lỗi → trạng thái `error` + `error_message`, không văng 500

**Verify thật (bắt buộc trước khi coi là xong):** upload thật một `.docx` và một `.pdf` nhiều
chương lên R2 thật, xem `draft_outline` sinh ra có đúng số chương và nội dung không. Không kết luận
"xong" chỉ dựa vào pytest.

## 10. Định nghĩa hoàn thành

- [ ] Migration `0006` apply lên Supabase thật, verify RLS: user A không đọc được `lessons` của B
- [ ] 4 extractor + splitter có test, pytest xanh, output sạch
- [ ] 4 endpoint chạy, sai quyền → 404
- [ ] Verify thật với `.docx` + `.pdf` nhiều chương trên R2 thật
- [ ] File hỏng → `error` + thông báo tiếng Việt, retry chạy lại được
- [ ] `.env.example` + `requirements.txt` + `check_list.md` cập nhật
