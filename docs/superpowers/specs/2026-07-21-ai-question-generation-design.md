# #4a — Sinh câu hỏi ôn tập bằng AI — Design

**Ngày**: 2026-07-21
**Sub-project**: #4a (thay cho parse callout — D13)
**Trạng thái**: spec, chờ plan

## 1. Mục tiêu

Thay việc soạn tay câu hỏi ôn tập bằng câu hỏi do AI (Gemini `gemini-2.5-flash`) sinh **riêng cho
từng user** từ nội dung một bài học (`lessons.content_md`). Không dùng RAG — một bài học chỉ vài nghìn
token nên đưa nguyên nội dung vào prompt chính xác hơn retrieval (D13).

Phạm vi #4a **chỉ tới bước sinh + hiển thị read-only**. Ô nhập câu trả lời và chấm điểm là #4.

## 2. Quyết định chốt (từ brainstorm)

| # | Quyết định | Lý do |
|---|---|---|
| A | **Lazy + cache DB**: lần đầu user mở mục ôn tập → gọi Gemini, lưu vào `questions` với `user_id`; lần sau đọc thẳng DB, không gọi lại AI. Có nút "Sinh lại". | Rẻ nhất ($0), ổn định để làm bài lại, đúng tinh thần free-tier. |
| B | **Backend + hiển thị read-only**: #4a làm endpoint sinh/cache/trả **và** hiển thị danh sách câu hỏi read-only dưới bài học. Ô trả lời + chấm để #4. | Thấy kết quả ngay, verify dễ; vẫn giữ ranh giới với #4. |
| C | **5 câu/bài, ép ≥3/4 loại** (recall/scenario/compare/explain). | Đa dạng, tránh toàn recall, prompt vẫn gọn. |
| D | **Regenerate = xoá bộ cũ + ghi mới, chấp nhận cascade.** `quiz_attempts.question_id` có `ON DELETE CASCADE`; sinh lại xoá luôn lịch sử trả lời của bài đó. #4a chưa có `quiz_attempts` nên vô hại bây giờ — ghi chú lại cho #4. | Đơn giản; chủ dự án chấp nhận. |

## 3. Data model — migration `0007_questions_per_user.sql`

> Checklist ghi "0006" nhưng số đó đã thuộc #1a (`0006_lessons_per_user_and_files.sql`). Migration mới
> là **`0007`**.

Bảng `questions` hiện là **dùng chung** (không `user_id`, RLS `questions_select` cho mọi user đã đăng
nhập đọc chung). Chuyển sang riêng tư từng user:

```sql
-- questions: shared -> per-user private.
alter table questions add column user_id uuid references auth.users(id) on delete cascade;

-- Bảng rỗng ở production (chưa từng sinh câu hỏi). Nếu tồn tại dòng cũ mồ côi, xoá trước:
--   delete from questions where user_id is null;
alter table questions alter column user_id set not null;

-- Một user có đúng một bộ câu hỏi cho mỗi bài, order_index không trùng.
-- Nền tảng cho cache (kiểm tra tồn tại) và chống trùng khi hai request cùng sinh.
create unique index questions_user_lesson_order_idx
  on questions (user_id, lesson_id, order_index);

-- Thay policy đọc-chung bằng RLS riêng tư.
drop policy "questions_select" on questions;
create policy "questions_select_own" on questions
  for select using (auth.uid() = user_id);
```

**Giữ nguyên**: cột `type` + CHECK `type in ('recall','scenario','compare','explain')`; không thêm
write policy — chỉ service-role (backend) ghi, như mọi bảng nội dung khác.

## 4. Module AI — `backend/app/ai/`

Tách riêng như `ingest/` để #4 (chấm điểm) và #5 (chat) dùng lại cùng client.

### 4.1 `app/ai/client.py`
- `get_client() -> genai.Client` (lru_cache 1) khởi tạo từ `settings.gemini_api_key()`.
- Hằng `CHAT_MODEL = "gemini-2.5-flash"`.
- Thêm `GEMINI_API_KEY` vào `settings.py` (`gemini_api_key()` theo khuôn `_required`) và `.env.example`.
- Thêm `google-genai` vào `backend/requirements.txt`.

### 4.2 `app/ai/questions.py`
`generate_questions(content_md: str) -> list[GeneratedQuestion]`:

- **Structured output**: gọi `client.models.generate_content` với
  `config={"response_mime_type": "application/json", "response_schema": <schema>}`.
  Schema = mảng đúng 5 phần tử, mỗi phần tử `{type: <enum QUESTION_TYPES>, question_text: str}`.
- **Prompt tiếng Việt**: đưa nguyên `content_md`; yêu cầu 5 câu hỏi **tự luận** (không trắc nghiệm);
  **bắt buộc phủ ít nhất 3 trong 4 loại**; kèm `QUESTION_TYPE_DESCRIPTIONS` mô tả từng loại để model
  chọn đúng.
- **`GeneratedQuestion`** = Pydantic `{type: str, question_text: str}`.
- **Graceful degradation (nguyên tắc #4)**: bọc try/catch quanh lời gọi + parse JSON + validate.
  - Mỗi `type` phải nằm trong `QUESTION_TYPES`, `question_text` không rỗng — nếu sai, coi như lỗi sinh.
  - Bất kỳ lỗi nào (mạng, quota, JSON hỏng, validate) → raise một exception nội bộ có thông báo
    tiếng Việt; router bắt và trả 502. Không nuốt lỗi, không trả bộ câu rác.
  - **Không ép cứng "đúng 5 câu / đủ 3 loại" thành lỗi**: nếu model trả 4–5 câu hợp lệ vẫn nhận (đa
    dạng là yêu cầu trong prompt, không phải điều kiện chặn) — tránh làm hỏng cả pipeline vì một ràng
    buộc mềm. Ràng buộc cứng duy nhất: mỗi câu có `type` hợp lệ và `question_text` không rỗng, và có
    ít nhất 1 câu.

## 5. `callout_types.py` đổi vai trò

- **Bỏ** `is_question_type` (không nơi nào import — đã kiểm).
- **Giữ** `QUESTION_TYPES` làm nguồn chân lý duy nhất (đồng bộ với CHECK constraint DB).
- **Thêm** `QUESTION_TYPE_DESCRIPTIONS: dict[str, str]` (mô tả tiếng Việt từng loại) để bơm vào prompt.
- Cập nhật docstring: từ "whitelist parser" → "enum ép AI chọn khi sinh câu hỏi".

## 6. API — thêm vào `routers/lessons.py`

Theo đúng khuôn `_Repo` của file: service-role client, mọi truy vấn lọc `user_id` tường minh, bài của
người khác → **404** (không 403). Dùng `slug` cho nhất quán với `GET /api/lessons/{slug}`.

| Method | Path | Hành vi |
|---|---|---|
| `GET` | `/api/lessons/{slug}/questions` | Tra `(user_id, lesson_id)`. **Có sẵn** → trả luôn (0 token AI). **Chưa có** → `generate_questions(content_md)` → lưu → trả về. |
| `POST` | `/api/lessons/{slug}/questions/regenerate` | Xoá bộ cũ của `(user_id, lesson_id)` → sinh mới → lưu → trả về. |

- **Response** (`QuestionOut[]`): `{ id, type, question_text, order_index }`. Không trả `user_id`/`lesson_id`
  (nội bộ, như `FileOut` giấu `storage_path`/`user_id`).
- Bài không tồn tại / của người khác → **404** `"Không tìm thấy bài học."`.
- Lỗi AI → **502** + thông báo tiếng Việt (user bấm thử lại). Bài rỗng `content_md` → 422/400 thông báo
  rõ (không gọi AI với nội dung rỗng).
- **Ghi câu hỏi**: lưu kèm `order_index` 0..n theo thứ tự model trả. Insert một lần (batched) như
  `insert_lessons`. Regenerate: `delete` theo `(user_id, lesson_id)` rồi insert — hai bước, chấp nhận
  không nguyên tử (rủi ro thấp với <10 user; nếu insert lỗi sau khi xoá, GET sau sẽ tự sinh lại).
- **Chống trùng khi sinh lần đầu**: unique index `(user_id, lesson_id, order_index)` khiến hai request
  đồng thời cùng insert → một cái dính lỗi unique; bắt lỗi đó và đọc lại bộ đã có thay vì nhân đôi.
  (Rủi ro double-click thấp nhưng index làm nó bất khả thay vì chỉ hiếm.)

### `_QuestionRepo`
Thêm phương thức: `list_questions(user_id, lesson_id)`, `insert_questions(rows)`,
`delete_questions(user_id, lesson_id)`. Tách khỏi `_Repo` lesson hiện có (một lớp riêng, cùng file) để
mỗi lớp một trách nhiệm; hoặc gộp nếu plan thấy gọn hơn — quyết định ở bước plan.

## 7. Frontend — hiển thị read-only

Trong `frontend/src/pages/LessonDetail` (trang `/lessons/:slug`), dưới `<article class="prose">`: mục
**"Câu hỏi ôn tập"**.

- **Chưa sinh**: nút "Sinh câu hỏi ôn tập" → gọi `GET .../questions` → spinner "Đang sinh câu hỏi…".
- **Đã có**: danh sách 5 câu; mỗi câu một badge loại (nhãn tiếng Việt cho recall/scenario/compare/explain)
  + nội dung câu hỏi. **Không có ô trả lời** (để #4).
- Nút nhỏ **"Sinh lại"** → `POST .../questions/regenerate` (xác nhận nhẹ vì sẽ thay bộ hiện tại).
- Lỗi (502/mạng) → thông báo tiếng Việt + nút thử lại. Mọi request qua `apiFetch`.
- Wrapper kiểu trong `frontend/src/lib/` (theo khuôn `files.ts`).

## 8. Kiểm thử

**pytest** (`test_ai_questions.py`, `test_questions_api.py`) — không gọi mạng thật:
- AI client giả trả JSON cố định → cache-miss gọi generator đúng 1 lần và lưu; cache-hit **không** gọi
  generator; regenerate xoá rồi ghi bộ mới.
- Validate: `type` ngoài `QUESTION_TYPES` hoặc `question_text` rỗng → coi là lỗi sinh → 502; JSON hỏng
  → 502; danh sách rỗng → 502.
- 404 khi slug không thuộc user.
- `content_md` rỗng → không gọi AI, trả lỗi rõ.
- Toàn bộ pytest phải xanh và **output sạch** (không warning).

**Verify thật** (`backend/scripts/verify_4a.py`) — Gemini thật + Supabase thật, session mint trong tiến
trình:
- Gọi `GET .../questions` trên một bài `.docx` đã cắt → 5 (hoặc ≥1) câu hợp lệ, **≥3 loại khác nhau**,
  nội dung bám sát `content_md` bài đó.
- Gọi `GET` lần 2 → **không phát sinh dòng mới** trong `questions` (cache hit).
- `POST .../regenerate` → bộ câu đổi, số dòng vẫn đúng.
- **RLS thật**: anon key đọc `questions` ra **0 dòng**.
- Dọn sạch: xoá các dòng `questions` script tạo, tài khoản về nguyên trạng.
- Lưu ý console Windows: chạy kèm `PYTHONIOENCODING=utf-8` nếu in tiếng Việt; script cần
  `SUPABASE_ANON_KEY` (nằm ở `frontend/.env.local`) cho phần kiểm RLS.

**Frontend**: `npm run build` sạch; kiểm trình duyệt thủ công (sinh lần đầu, hiển thị badge loại, sinh
lại, lỗi hiển thị tiếng Việt).

## 9. Ngoài phạm vi (không làm ở #4a)

- Ô nhập câu trả lời, chấm điểm, `quiz_attempts`, `daily_activity` → **#4**.
- Socratic chat → #5.
- RAG / tài liệu cá nhân → hoãn (D8).

## 10. Nợ ghi nhận cho #4

- Regenerate xoá lan `quiz_attempts` qua cascade (D). Khi làm #4 quyết định có chặn "Sinh lại" khi đã
  có lịch sử trả lời hay không.
- Delete-then-insert của regenerate không nguyên tử (rủi ro thấp; GET sau tự phục hồi).
