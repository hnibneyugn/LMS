# #4 — AI chấm điểm — Design

**Ngày**: 2026-07-21
**Sub-project**: #4 (chấm câu trả lời tự luận do AI sinh ở #4a)
**Trạng thái**: spec, chờ plan
**Tiền đề**: #4a đã xong & merged — `questions` riêng tư từng user, `app/ai/client.py` (Gemini
`gemini-3.5-flash`), `app/ai/questions.py`, section read-only `ReviewQuestions` ở trang bài học.

## 1. Mục tiêu

User trả lời câu hỏi ôn tập (tự luận) → AI chấm điểm 0–10, chỉ ra ý còn thiếu và một nhận xét ngắn →
lưu vào `quiz_attempts` (lịch sử bất biến) và tăng `daily_activity` (chuyên cần). Chấm dựa **chỉ trên
nội dung bài** (`lessons.content_md`) — **không RAG** (D8).

## 2. Quyết định chốt (từ brainstorm)

| # | Quyết định | Lý do |
|---|---|---|
| A | **Inline từng câu** tại section "Câu hỏi ôn tập": mỗi câu có ô trả lời + nút "Nộp bài", chấm xong hiện điểm/nhận xét ngay dưới câu. | Liền mạch với #4a, không thêm trang/route mới. |
| B | **daily_activity đếm mỗi câu 1 lần/ngày**: lần đầu chấm một câu trong ngày (theo ngày UTC) mới +1; nộp lại cùng câu trong ngày không cộng. | Thống kê chuyên cần phản ánh "bao nhiêu câu đã làm" thật, không thổi bằng nộp lặp. |
| C | **Có GET attempts**: mở lại bài vẫn thấy câu đã làm + đáp án + điểm. | Trải nghiệm học liền mạch; kết quả không biến mất khi F5. |
| D | **Chấm = điểm + ý thiếu + nhận xét** (không phản biện Socratic). | Socratic là #5 (chat). #4 chỉ chấm. |

## 3. Data model — KHÔNG cần migration

`quiz_attempts` và `daily_activity` đã có sẵn (`0002_tables.sql`) + RLS (`0003_rls.sql`):
- `quiz_attempts(id, user_id, question_id→questions, user_answer, ai_score numeric(3,1) [0..10],
  ai_feedback jsonb, created_at)`. RLS: select+insert own, **không** update/delete (lịch sử bất biến).
- `daily_activity(user_id, activity_date, questions_done_count, PK(user_id, activity_date))`.
  RLS: select+insert+update own.

Backend ghi qua service-role client (bypass RLS) → mọi truy vấn lọc `user_id` tường minh, như #4a.

## 4. Module AI — `backend/app/ai/grading.py`

`grade_answer(content_md, question_text, question_type, user_answer) -> GradeResult`:
- **`GradeResult`** (Pydantic): `score: float`, `missing_points: list[str]`, `comment: str`.
- **Structured output**: `response_mime_type="application/json"` + `response_schema` (dict JSON-schema,
  như #4a — đã chứng minh google-genai chấp nhận). Model `CHAT_MODEL` từ `app/ai/client.py`.
- **Prompt tiếng Việt**: chấm công bằng thang **0–10** dựa **chỉ trên nội dung bài** + câu hỏi + câu
  trả lời; liệt kê ý còn thiếu (rỗng nếu đủ); một nhận xét ngắn mang tính xây dựng.
- **Graceful degradation (nguyên tắc #4)**: bọc try/catch quanh call + parse + validate. Lỗi mạng/
  quota/JSON hỏng/validate → raise `GradingError` (thông báo tiếng Việt) — router bắt, trả 502. Không
  nuốt lỗi, không ghi gì. Validate: `score` kẹp về [0,10] (số ngoài dải bị kẹp, không phải lỗi);
  `missing_points` phải là list[str] (không phải → coi lỗi sinh); `comment` là str.

## 5. API — `backend/app/routers/quiz.py` (prefix `/api/quiz`)

Khuôn `_Repo` service-role, lọc `user_id` tường minh, bài/câu của người khác → **404** (không 403).
Đăng ký router trong `main.py`.

### `POST /api/quiz/grade`
Body: `{ question_id: str, user_answer: str }`.
1. Tra question theo `(user_id, question_id)` (join/lookup lấy `lesson_id`, `question_text`, `type`).
   Không có / của người khác → **404**.
2. `user_answer` sau strip rỗng → **422** "Câu trả lời không được để trống." (không gọi AI). Giới hạn
   độ dài `user_answer` ≤ **5000** ký tự (Pydantic `max_length`) → 422 nếu vượt.
3. Lấy `lessons.content_md` theo `lesson_id` (+ `user_id`). `grade_answer(...)`. Lỗi → **502** tiếng
   Việt, **chưa ghi gì**.
4. **Đếm trước khi ghi**: đếm số `quiz_attempts` hiện có của `(user_id, question_id)` với
   `created_at::date = today` (ngày UTC). `first_today = (count == 0)`. Phải đếm **trước** bước 5, nếu
   không dòng vừa insert sẽ làm count luôn ≥1.
5. Insert `quiz_attempts` (id uuid mint ở backend, user_id, question_id, user_answer, ai_score=score,
   ai_feedback=`{missing_points, comment}`).
6. **daily_activity**: nếu `first_today` → upsert +1 `questions_done_count` cho `(user_id, today)`
   (on_conflict `user_id,activity_date`, cộng dồn). Nếu không → giữ nguyên.
7. Trả **`GradeOut`**: `{ score, missing_points, comment, created_at }`.

### `GET /api/quiz/attempts/{lesson_slug}`
- Tra lesson theo `(user_id, slug)` → 404 nếu không phải của mình.
- Trả **attempt mới nhất mỗi câu** của bài đó: `list[AttemptOut]` với
  `{ question_id, user_answer, score, missing_points, comment, created_at }`. Câu chưa làm không có mặt.
- Frontend merge theo `question_id`.

**Thứ tự**: chấm (3) → đếm-hôm-nay (4) → insert attempt (5) → tăng daily nếu lần đầu (6). Lỗi AI để
lại DB nguyên trạng; user nộp lại được.

## 6. Frontend — mở rộng `ReviewQuestions.tsx` + lib

- Khi load section: sau khi có danh sách câu (GET `/api/lessons/{slug}/questions` của #4a), gọi thêm
  `getAttempts(slug)` → prefill câu đã làm (đáp án cũ + điểm + nhận xét + ý thiếu).
- Mỗi câu: nếu **chưa có attempt** → hiện **textarea** + nút **"Nộp bài"** (disable khi rỗng/đang chấm).
  Nộp → `gradeAnswer(questionId, answer)` → hiện **điểm /10** + **nhận xét** + danh sách **ý còn thiếu**.
- Nếu **đã có attempt** → hiện đáp án đã nộp + kết quả, kèm nút **"Làm lại"** (xoá hiển thị, mở lại
  textarea để nộp attempt mới).
- Lỗi (422/502/mạng) → thông báo tiếng Việt + cho nộp lại. Mọi request qua `apiFetch`.
- lib (`frontend/src/lib/quiz.ts` hoặc thêm vào `lessons.ts`): types `GradeResult`/`Attempt`,
  `gradeAnswer(questionId, answer)`, `getAttempts(slug)`.

## 7. Kiểm thử

**pytest** (`test_grading.py`, `test_quiz_api.py`, `test_quiz_repo.py`) — không gọi mạng:
- grader giả trả JSON cố định → grade lưu đúng `quiz_attempts` (score, ai_feedback shape); trả GradeOut.
- **daily_activity chỉ +1 lần đầu/ngày**: attempt thứ 2 cùng câu trong ngày → daily **không** tăng;
  câu khác cùng ngày → +1.
- Validate: `score` ngoài [0,10] bị kẹp; `missing_points` không phải list → 502; JSON hỏng/AI lỗi → 502
  và **không ghi** quiz_attempts / daily_activity; `user_answer` rỗng → 422 không gọi AI; quá dài → 422.
- 404 khi question/lesson không thuộc user.
- `GET attempts` trả **mới-nhất-mỗi-câu** (câu nộp 2 lần chỉ ra bản mới nhất).
- **repo-level** (real `_Repo` vs FakeClient): mọi read/insert lọc `user_id` — drop filter thì đỏ test.
- Toàn bộ pytest xanh, **output sạch**.

**Verify thật** (`backend/scripts/verify_4.py`) — Gemini + Supabase thật, session mint trong tiến trình,
trên một câu hỏi thật (sinh trước bằng #4a):
- `POST grade` → điểm 0–10 + `missing_points` + `comment`; `quiz_attempts` có đúng 1 dòng mới;
  `daily_activity` hôm nay +1.
- Nộp lại cùng câu → `quiz_attempts` +1 dòng nữa nhưng `daily_activity` **không đổi**.
- `GET attempts/{slug}` → trả bản mới nhất.
- **RLS thật**: anon key đọc `quiz_attempts` và `daily_activity` ra **0 dòng**.
- Dọn sạch: xoá các dòng script tạo, tài khoản về nguyên trạng.
- Lưu ý Windows: `PYTHONIOENCODING=utf-8`; cần `SUPABASE_ANON_KEY` (ở `frontend/.env.local`) cho phần RLS.

**Frontend**: `npm run build` sạch; kiểm trình duyệt thủ công (nộp → điểm/feedback; F5 vẫn thấy; làm lại).

## 8. Ngoài phạm vi (không làm ở #4)
- Streak, biểu đồ câu hỏi theo tuần, % hoàn thành, leaderboard, xem lại lịch sử nhiều attempt → **#6**.
- Socratic chatbot → **#5**. RAG / tài liệu cá nhân → hoãn (D8).

## 9. Nợ ghi nhận
- `activity_date` dùng **ngày UTC**; với người ở VN (UTC+7) ranh giới "ngày" là 7h sáng. Streak (#6)
  sẽ cân nhắc timezone khi làm — #4 giữ UTC cho nhất quán với `completed_at` (#3).
- Bước 5 (đếm-rồi-quyết-định tăng daily) không nguyên tử: hai lần nộp cùng câu gần như đồng thời có thể
  cùng thấy "0 attempt hôm nay" và cùng +1. Rủi ro rất thấp (<10 user, một người tự nộp) — chấp nhận;
  hệ quả tối đa là questions_done_count nhỉnh 1 đơn vị, không phải lỗi bảo mật.
