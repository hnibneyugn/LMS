# Project Context — Personal LMS

Tài liệu bối cảnh dự án: tại sao, cho ai, quyết định lớn, giả định. Cập nhật khi có quyết định mới.

## 1. Mục tiêu

Xây một Personal LMS để một nhóm nhỏ bạn bè/người quen (invite-only, **< 10 user**) học tập chủ
động: đọc lý thuyết (viết bằng Obsidian, sync tự động), làm bài tự luận được AI chấm + phản biện,
và (sau này) upload tài liệu cá nhân để AI dùng làm ngữ cảnh (RAG). Ưu tiên **chi phí $0** (free
tier) và **bảo mật dữ liệu cá nhân** (RLS).

## 2. Người dùng & vai trò

- **Admin (chủ hệ thống)**: sở hữu Obsidian Vault, viết nội dung, mời thành viên. Nhận diện qua
  `ADMIN_EMAIL` trong env.
- **Member**: được mời qua email (Magic Link). Học, làm bài, xem leaderboard.

## 3. Luồng dữ liệu chính

1. **Nội dung học (dùng chung)**: Obsidian Vault → Obsidian Git plugin (auto commit/push) → GitHub
   private repo → GitHub Webhook → `POST /api/sync` (FastAPI) → parse frontmatter + callout → upsert
   vào `lessons` / `questions` bằng service-role.
2. **Đăng nhập**: frontend gọi thẳng Supabase Auth (Magic Link) → nhận JWT → đính kèm
   `Authorization: Bearer` vào mọi request tới backend → backend verify qua JWKS.
3. **Học & làm bài (riêng tư)**: user đọc lesson → làm câu hỏi tự luận → AI chấm (structured output,
   context = `lessons.content_md` + câu hỏi + câu trả lời + RAG chunks của chính user nếu có) → lưu
   `quiz_attempts` + tăng `daily_activity`.
4. **Socratic chat (riêng tư)**: streaming, context = nội dung bài + kiến thức nền model + RAG →
   lưu `chat_sessions`.
5. **Tài liệu cá nhân (riêng tư — HOÃN)**: upload → R2 (file gốc) + `user_files` (metadata) →
   extract → chunk → embed (`vector(768)`) → `document_chunks`. Retrieval: cosine similarity,
   **filter cứng theo `user_id`**, top 5.

## 4. Quyết định kỹ thuật quan trọng

| # | Quyết định | Lý do |
|---|---|---|
| D1 | Postgres cho tất cả (kể cả vector qua `pgvector`) | Đơn giản, 1 nguồn dữ liệu, $0 |
| D2 | Cloudflare R2 thay vì Supabase Storage | Theo spec — free egress, S3-compatible |
| D3 | Embedding 768 chiều (giảm từ 3072) | Tiết kiệm dung lượng DB |
| D4 | Xử lý RAG bằng FastAPI `BackgroundTasks` trong cùng request upload | Đủ cho quy mô cá nhân; không cần queue riêng (Celery/Redis) |
| D5 | `leaderboard_view` cố ý bypass RLS (view owner-privileged) | Cần tổng hợp cross-user; chỉ lộ số liệu tổng hợp, KHÔNG lộ nội dung câu trả lời |
| D6 | Parser Markdown/callout viết thành module thuần túy, độc lập webhook | Tái sử dụng cho nguồn sync khác sau này |
| D7 | Model AI IDs tạm hoãn | Tên model Gemini trong spec (`gemini-2.5-pro`, `gemini-embedding-2`) có thể đã đổi; verify khi build feature AI |
| **D8** | **HOÃN RAG / tài liệu cá nhân** (vẫn giữ) | RAG là tính năng phụ. Bảng `user_files`/`document_chunks` giữ trong schema (vô hại), chỉ chưa build pipeline. Thêm khi nhóm thật sự cần mang tài liệu ngoài vào. Lưu ý: lý do gốc của D8 ("tránh phải dựng service Python") **đã không còn** — backend FastAPI nay đã tồn tại sẵn (D10), nên chi phí thêm RAG giờ thấp hơn trước. |
| D9 | Doc processing **KHÔNG dùng Gemini** khi làm RAG | Ràng buộc của chủ dự án; chọn công cụ extract riêng (`python-docx`, `python-pptx`, ...) |
| **D10** | **PIVOT (2026-07-18): bỏ Next.js fullstack → React (Vite) SPA + FastAPI backend, 2 thư mục trong 1 repo** | Thay cho quyết định cũ "thuần Next.js, không dùng FastAPI". Chủ dự án cung cấp spec kiến trúc mới. Vì app Next.js mới chỉ ở mức scaffold + schema (chưa có trang/API nào), đây là **build mới lớp ứng dụng**, không phải migrate code. Toàn bộ Supabase + R2 đang chạy được **giữ nguyên 100%**, không đụng dữ liệu. |
| D11 | Backend verify JWT bằng **JWKS/ES256**, không dùng shared JWT secret | Đo thực tế: project Supabase này ký bất đối xứng (JWKS trả key ES256). HS256 + shared secret sẽ fail mọi token thật. |
| **D13** | **Câu hỏi ôn tập do AI sinh riêng cho từng user, KHÔNG parse từ callout Obsidian** (2026-07-18) | Admin chỉ viết lý thuyết, không phải soạn tay câu hỏi cho mọi bài. Hệ quả: bỏ hẳn cú pháp `> [!recall]`; `callout_types.py` đổi vai trò thành enum ép AI chọn `type`; bảng `questions` cần thêm `user_id` + RLS (đang là bảng dùng chung); sub-project #1 rút gọn còn parse frontmatter nên **gộp vào #2**; sinh câu hỏi tách ra thành #4a. **Không dùng RAG** cho việc này — một bài học chỉ vài nghìn token, đưa nguyên `content_md` vào prompt chính xác hơn retrieval. RAG (D8) vẫn chỉ dành cho tài liệu cá nhân user upload. |
| D14 | Parser **không đọc `week`** từ frontmatter | Giả định "tài liệu chia theo tuần" không đúng với mọi người viết. Cột `lessons.week` giữ lại nullable (luôn NULL, không cần migration) phòng khi dùng lại; UI ở #3 bỏ tab lọc Tuần, chỉ còn Chủ đề. |
| D15 | Leaderboard xếp theo **số ngày học**, không theo điểm; xếp theo **giờ học** hoãn | Chủ dự án muốn thi đua chuyên cần thay vì điểm số. Số ngày lấy từ `daily_activity.activity_date` — chính xác, gần như miễn phí, trùng nguồn dữ liệu với streak. Đo *giờ* học trên web cần heartbeat lúc tab mở và xử lý tab bỏ quên/đóng máy đột ngột → dễ ra số liệu rác, chưa đáng làm. |
| D12 | Dev local chạy backend bằng **venv**, không Docker | Máy dev hạn chế RAM (Docker Desktop/WSL2 nặng); RAG sau này thêm nhiều thư viện Python nên venv bền vững hơn. `docker-compose.yml` vẫn giữ như tuỳ chọn + parity với bản deploy Koyeb. |

## 5. Giả định (assumptions)

- Supabase + R2 + Gemini + GitHub webhook đã có **key thật**, Supabase đang chạy live với schema +
  RLS đã apply và **đã verify bằng luồng đăng nhập thật**.
- `frontend/src/lib/database.types.ts` hiện là placeholder tối thiểu; sẽ regenerate bằng
  `supabase gen types typescript` khi frontend bắt đầu query bảng thật.
- Local dev: frontend cổng **5173**, backend cổng **8000**; Supabase Site URL trỏ `localhost:5173`.

## 6. Ràng buộc

- Public sign-up **TẮT**. Admin thêm email thủ công / qua `/admin/invite` (sub-project #7).
  Cưỡng chế bằng `shouldCreateUser: false` — đã verify: email chưa mời không tạo được user.
- Frontend chỉ dùng anon key; service-role key chỉ ở backend.
- (HOÃN — chỉ áp dụng khi làm RAG) File upload: PDF/DOCX/PPTX tối đa 20MB, PDF tối đa 50 trang;
  presigned URL R2 hết hạn ~15 phút, bucket private.

## 7. Biến môi trường

Hai file riêng: `backend/.env.example` (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ADMIN_EMAIL`,
`ALLOWED_ORIGINS`; sau thêm Gemini/R2/webhook) và `frontend/.env.example` (`VITE_SUPABASE_URL`,
`VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`). Chi tiết cách lấy: `SETUP.md`.

## 8. Lịch sử

- **Pass 1 (Next.js, đã bỏ)**: scaffold + toàn bộ SQL schema/RLS/migrations. Schema được **giữ lại
  nguyên vẹn** qua pivot — đây là phần giá trị nhất của pass này.
- **Sub-project #0 — Foundation + Auth (XONG, 2026-07-18)**: dựng frontend Vite + backend FastAPI,
  đăng nhập Magic Link invite-only chạy thật end-to-end, backend verify JWT ES256. Xem
  `check_list.md` và `docs/superpowers/specs|plans/2026-07-18-foundation-auth*`.
