# #5 — Socratic Chatbot — Design

Ngày: 2026-07-21 · Sub-project #5 · Nhánh dự kiến: `feature/socratic-chatbot`

## Mục tiêu

Mỗi bài học có một trợ giảng AI kiểu **Socratic thuần**: người học hỏi/đối thoại về nội dung
bài, AI **không bao giờ đưa đáp án thẳng** mà dẫn dắt bằng câu hỏi gợi mở để họ tự rút ra. Hội
thoại được lưu bền vững theo (user, bài) — mở lại bài là thấy lại toàn bộ. Giao diện là một
**panel trượt từ phải** trên trang bài học, cạnh phần lý thuyết.

Bám nguyên tắc bất biến: chi phí $0 (Gemini free tier), cách ly dữ liệu bằng RLS
(`auth.uid() = user_id`), graceful degradation (AI lỗi không làm sập request), tiếng Việt cho
người dùng / tiếng Anh cho code.

## Quyết định thiết kế (đã chốt khi brainstorm)

- **D-chat-1 — Socratic thuần.** AI chỉ gợi mở, không đưa lời giải trực tiếp; câu hỏi ngoài phạm
  vi bài → kéo về nội dung bài. (Không có chế độ "mềm" đưa đáp án.)
- **D-chat-2 — Panel trượt từ phải.** Giữ nguyên cột đọc hẹp `max-w-3xl` của `LessonDetail`; chat
  mở ra trong panel overlay trượt từ cạnh phải, không nới layout thành hai cột cố định.
- **D-chat-3 — Một cuộc bền vững / (user, bài).** Đúng một `chat_sessions` cho mỗi cặp
  (user_id, lesson_id). Có nút "Xóa hội thoại" để bắt đầu lại. Khớp pattern "mở lại vẫn thấy" của
  #3/#4.
- **D-chat-4 — Endpoint keyed by `lesson_id` (UUID)**, đúng như checklist ghi
  `POST /api/chat/{lesson_id}`. `LessonDetail` đã có sẵn `lesson.id`, không phải tra slug.
- **D-chat-5 — Thêm migration `0008`** (unique index `(user_id, lesson_id)` trên `chat_sessions`)
  để "một cuộc bền vững" là ràng buộc thật, tránh hai dòng khi hai request đua nhau. Bảng đang
  rỗng nên thêm an toàn.

## Kiến trúc

Ba lớp tách bạch, theo đúng khuôn các sub-project trước:

```
frontend ChatPanel ──HTTP──▶ routers/chat.py ──▶ ai/chat.py ──▶ Gemini (stream)
                                    │
                                    ▼
                          chat_sessions (Supabase, RLS)
```

- `ai/chat.py`: chỉ biết Gemini + prompt, không biết HTTP/DB. Nhận `content_md` + lịch sử + tin
  mới, trả iterator các chunk text.
- `routers/chat.py`: verify quyền sở hữu bài, load/lưu `chat_sessions`, ghép stream. Router mỏng,
  logic AI nằm ở module riêng.
- `ChatPanel.tsx`: UI thuần, gọi qua `lib/chat.ts`.

## Dữ liệu

### Bảng `chat_sessions` (đã tồn tại — 0002, RLS ở 0003)

```sql
chat_sessions (
  id uuid pk,
  user_id uuid  -> auth.users,
  lesson_id uuid -> lessons,
  messages jsonb not null default '[]',
  created_at timestamptz,
  updated_at timestamptz
)
```

RLS đã có: SELECT/INSERT/UPDATE `auth.uid() = user_id`. Không cần policy mới.

**Hình dạng `messages`**: mảng `{"role": "user" | "assistant", "content": "<text>"}` theo thứ tự
thời gian. Không lưu timestamp từng tin (YAGNI — không có màn hình nào cần).

### Migration `0008_chat_sessions_unique.sql`

```sql
create unique index if not exists chat_sessions_user_lesson_idx
  on chat_sessions (user_id, lesson_id);
```

Cưỡng chế D-chat-3. Load-or-create dựa vào đúng cặp cột này.

## Backend

### `app/ai/chat.py`

- Hằng `_FAILURE_MESSAGE = "Không trả lời được lúc này. Vui lòng thử lại."`
- `class ChatError(Exception)` — message tiếng Việt, an toàn để show.
- `_build_system_prompt(content_md: str) -> str` — chỉ thị Socratic thuần:
  - Vai trò: gia sư Socratic, chỉ dựa **duy nhất** trên nội dung bài dưới đây.
  - **Tuyệt đối không đưa đáp án/lời giải trực tiếp**; thay vào đó đặt 1–2 câu hỏi gợi mở dẫn
    người học tới câu trả lời; ghi nhận phần họ đúng, chỉ ra chỗ cần suy nghĩ thêm bằng câu hỏi.
  - Câu hỏi ngoài phạm vi bài → lịch sự kéo về nội dung bài.
  - Trả lời ngắn gọn, tiếng Việt.
  - Nội dung bài nhúng nguyên văn (không RAG — bài đủ nhỏ, D13).
- `stream_socratic_reply(content_md, history, user_message) -> Iterator[str]`:
  - `history`: list `{role, content}` đã lưu (không gồm tin mới).
  - Dựng `contents` cho google-genai: map `role` "assistant" → "model", "user" → "user"; nối
    `user_message` cuối cùng với role "user".
  - Gọi `get_client().models.generate_content_stream(model=CHAT_MODEL,
    contents=..., config={"system_instruction": _build_system_prompt(content_md)})`.
  - `yield` `chunk.text` cho từng chunk có text.
  - Bọc try/except: bất kỳ lỗi nào (network/quota/malformed) → `raise ChatError(_FAILURE_MESSAGE)`,
    log qua `logger.exception`.
- **Chặn đầu vào rỗng**: `user_message` rỗng/chỉ whitespace → `ChatError("Tin nhắn không được để
  trống.")` (router chặn trước bằng 422; module vẫn tự vệ như `grade_answer`).

### `app/routers/chat.py` — prefix `/api/chat`, thêm vào `main.py`

`_Repo` trên service-role client (bypass RLS), **mọi query lọc `user_id` tường minh**; bài của
người khác → **404** (không 403), đồng nhất với `lessons.py`/`quiz.py`.

Repo:
- `get_lesson(user_id, lesson_id) -> dict | None` — `select("id, content_md")` lọc
  `id` + `user_id`.
- `get_session(user_id, lesson_id) -> dict | None` — `select("id, messages")` theo cặp cột.
- `create_session(user_id, lesson_id) -> dict` — insert dòng rỗng `messages=[]`, id mint ở backend.
- `update_messages(session_id, messages)` — set `messages` + `updated_at`.

Models:
- `ChatRequest { message: str = Field(max_length=4000) }`
- `MessageOut { role: str, content: str }`
- `HistoryOut { messages: list[MessageOut] }`

Endpoints:

1. **`POST /api/chat/{lesson_id}`** → `StreamingResponse`
   - `message.strip()` rỗng → 422 "Tin nhắn không được để trống."
   - `get_lesson` None → 404 "Không tìm thấy bài học."
   - Load-or-create session. `history = session["messages"]`.
   - **Append tin user + lưu ngay** (`update_messages`) trước khi stream — nếu stream lỗi, câu hỏi
     người dùng vẫn còn.
   - **Kéo chunk đầu tiên eagerly** để lỗi up-front thành 502:
     ```python
     gen = stream_socratic_reply(content_md, history, message)
     try:
         first = next(gen)          # có thể raise ChatError
     except ChatError as exc:
         raise HTTPException(502, str(exc))
     except StopIteration:
         first = ""
     ```
   - Trả `StreamingResponse(_body(), media_type="text/plain; charset=utf-8")` với generator nội bộ:
     - yield `first`, rồi yield tiếp phần còn lại của `gen`, tích lũy vào `parts`.
     - Lỗi **giữa chừng**: `except ChatError` → log, dừng (không yield thêm) — phần đã nhận vẫn được
       lưu; không đổi được status vì body đã bắt đầu.
     - Cuối cùng (finally/sau vòng lặp): nếu `"".join(parts).strip()` không rỗng → append
       `{"role":"assistant","content": joined}` và `update_messages`.
   - Ghi chú: việc lưu assistant message xảy ra **trong generator** (sau khi client nhận hết), nên
     dùng closure giữ `session_id`, `history + [user_msg]`.

2. **`GET /api/chat/{lesson_id}`** → `HistoryOut`
   - `get_lesson` None → 404. Session None → `{messages: []}`. Ngược lại trả `messages` đã lưu.

3. **`DELETE /api/chat/{lesson_id}`** → 204 / `{messages: []}`
   - `get_lesson` None → 404. Nếu có session → `update_messages(id, [])`. Idempotent.

## Frontend

### `lib/api.ts` — thêm `apiStream`

`apiFetch` luôn `res.json()`, không đọc được stream. Thêm:

```ts
export async function apiStream(path, options): Promise<Response>
```

- Gắn Bearer như `apiFetch`, bọc lỗi mạng thành `ApiError("Không kết nối được máy chủ…", 0)`.
- `!res.ok` → đọc `detail` JSON như `apiFetch`, ném `ApiError`.
- Thành công → **trả `Response` thô** (caller đọc `res.body`).

### `lib/chat.ts`

```ts
export interface ChatMessage { role: "user" | "assistant"; content: string }
export function getChatHistory(lessonId): Promise<ChatMessage[]>       // GET
export function clearChat(lessonId): Promise<void>                     // DELETE
export async function streamChat(lessonId, message, onChunk): Promise<void>
```

- `streamChat` dùng `apiStream` POST, đọc `res.body!.getReader()` + `TextDecoder`, gọi
  `onChunk(text)` cho mỗi mẩu decode (`stream: true`), flush cuối.

### `components/ChatPanel.tsx`

- Props: `{ lessonId: string; open: boolean; onClose: () => void }`.
- Panel `fixed inset-y-0 right-0` trượt vào (`translate-x` transition), rộng ~`max-w-md`, có
  backdrop mờ click để đóng. `z` cao hơn nội dung.
- Khi `open` chuyển true lần đầu: `getChatHistory` đổ vào state `messages`.
- State: `messages: ChatMessage[]`, `input`, `sending`, `error`.
- Gửi: push `{role:"user", input}` + một `{role:"assistant", content:""}` rỗng; gọi `streamChat`,
  mỗi `onChunk` cộng dồn vào content của tin assistant cuối (cập nhật lạc quan, cuộn xuống).
  Lỗi → gỡ tin assistant rỗng + hiện `error` tiếng Việt (giữ lại input để gửi lại).
- Render: user căn phải, trợ giảng căn trái + markdown (`ReactMarkdown` + `remarkGfm`, không
  rehype-raw — nhất quán `LessonDetail`).
- Nút "Xóa hội thoại": `clearChat` → `messages=[]`. Xác nhận đơn giản bằng `window.confirm`.
- Ô nhập + nút "Gửi" (disable khi `sending` hoặc input rỗng); Enter để gửi, Shift+Enter xuống dòng.

### `pages/LessonDetail.tsx`

- Thêm state `chatOpen`. Nút "Hỏi đáp Socratic" (cạnh checkbox "Đã học" hoặc cuối trang) mở panel.
- `<ChatPanel lessonId={lesson.id} open={chatOpen} onClose={() => setChatOpen(false)} />`.

## Xử lý lỗi (tổng hợp)

| Tình huống | Kết quả |
|---|---|
| Tin nhắn rỗng | 422, "Tin nhắn không được để trống." |
| Bài không thuộc user / không tồn tại | 404, "Không tìm thấy bài học." |
| Gemini lỗi/hết quota **trước** token đầu | 502, "Không trả lời được lúc này. Vui lòng thử lại." |
| Gemini lỗi **giữa** stream | Stream dừng êm; phần đã nhận được lưu; log server |
| Mất kết nối backend (frontend) | "Không kết nối được máy chủ…" (ApiError status 0) |
| Token sai/thiếu | 401 (get_current_user) |

Không nuốt lỗi âm thầm: mọi nhánh lỗi AI đều `logger.exception` + thông báo tiếng Việt.

## Kiểm thử

### `backend/tests/test_chat.py` — module AI (fake client)
- `_build_system_prompt` chứa nội dung bài + chỉ thị "không đưa đáp án".
- Map role assistant→model đúng khi dựng `contents`.
- Fake stream client yield 2 chunk → `stream_socratic_reply` yield đúng 2 text.
- Fake client raise → `ChatError` với message tiếng Việt (không rò exception gốc).
- `user_message` rỗng → `ChatError`.

### `backend/tests/test_chat_api.py` — router (fake repo + fake AI)
- POST bài người khác → 404.
- POST message rỗng → 422.
- POST hợp lệ → body stream nối đúng các chunk; sau đó session có 2 message (user + assistant);
  tin user được lưu **trước** khi stream (kiểm bằng cách cho AI raise giữa chừng: user message vẫn
  còn, assistant chứa phần đã nhận).
- AI raise ngay chunk đầu → 502, session chỉ có tin user.
- GET không session → `{messages: []}`; có session → trả đúng.
- DELETE → session `messages == []`; DELETE bài người khác → 404.

Tất cả pytest xanh, **output sạch** (không warning).

### Frontend
- `npm run build` sạch (không lỗi TS), `oxlint` sạch.

### `backend/scripts/verify_5.py` — thật đầu-cuối
HTTP thật + Gemini thật + Supabase thật, session mint trong tiến trình, trên bài `.docx` thật của
tài khoản admin (khuôn `verify_4.py`):
- POST một câu hỏi về bài → nhận reply **stream không rỗng, tiếng Việt, kiểu Socratic** (chứa dấu
  "?", không phải bài giải dài).
- GET → đúng 2 message (user + assistant), nội dung khớp.
- POST câu thứ hai → history có 4 message (ngữ cảnh được nối).
- DELETE → GET trả `messages: []`.
- **RLS thật**: anon key đọc `chat_sessions` → **0 dòng**.
- Dọn sạch: xóa dòng `chat_sessions` script tạo, tài khoản về nguyên trạng.

> Nợ nhỏ đã biết (như `verify_3`/`verify_4`): script in tiếng Việt ra stdout → chạy kèm
> `PYTHONIOENCODING=utf-8` trên Windows; cần `SUPABASE_ANON_KEY` trong env cho bước RLS
> (nằm ở `frontend/.env.local`).

## Ngoài phạm vi (YAGNI)

- Không đa-hội-thoại/nhiều tab chat mỗi bài (một cuộc bền vững là đủ — D-chat-3).
- Không lưu timestamp từng tin, không "đang gõ…" của AI ngoài chính token stream.
- Không RAG/tài liệu cá nhân (hoãn cùng D8).
- Không rehype-raw / HTML thô trong markdown (nhất quán D23).
- Không rate-limit riêng (Gemini free tier tự giới hạn; nhóm < 10 người).
