# Project Context — Personal LMS

Tài liệu bối cảnh dự án: tại sao, cho ai, quyết định lớn, giả định. Cập nhật khi có quyết định mới.

## 1. Mục tiêu

Xây một Personal LMS để một nhóm nhỏ bạn bè/người quen (invite-only, **< 10 user**) học tập chủ
động: đọc lý thuyết (viết bằng Obsidian, sync tự động), làm bài tự luận được AI chấm + phản biện,
và upload tài liệu cá nhân để AI dùng làm ngữ cảnh (RAG). Ưu tiên **chi phí $0** (free tier) và
**bảo mật dữ liệu cá nhân** (RLS).

## 2. Người dùng & vai trò

- **Admin (chủ hệ thống)**: sở hữu Obsidian Vault, viết nội dung, mời thành viên. Nhận diện qua
  `ADMIN_EMAIL` trong env.
- **Member**: được mời qua email (Magic Link). Học, làm bài, upload tài liệu, xem leaderboard.

## 3. Luồng dữ liệu chính

1. **Nội dung học (dùng chung)**: Obsidian Vault → Obsidian Git plugin (auto commit/push) → GitHub
   private repo → GitHub Webhook → `POST /api/sync` → parse frontmatter + callout → upsert vào
   `lessons` / `questions`.
2. **Học & làm bài (riêng tư)**: user đọc lesson → làm câu hỏi tự luận → AI chấm (`generateObject`,
   context = `lessons.content_md` + câu hỏi + câu trả lời + RAG chunks của chính user) → lưu
   `quiz_attempts` + tăng `daily_activity`.
3. **Socratic chat (riêng tư)**: `streamText`, context = nội dung bài + kiến thức nền model + RAG →
   lưu `chat_sessions`.
4. **Tài liệu cá nhân (riêng tư)**: upload → R2 (file gốc) + `user_files` (metadata) → extract →
   chunk → embed (`vector(768)`) → `document_chunks`. Retrieval: cosine similarity, **filter cứng
   theo `user_id`**, top 5.

## 4. Quyết định kỹ thuật quan trọng

| # | Quyết định | Lý do |
|---|---|---|
| D1 | Postgres cho tất cả (kể cả vector qua `pgvector`) | Đơn giản, 1 nguồn dữ liệu, $0 |
| D2 | Cloudflare R2 thay vì Supabase Storage | Theo spec — free egress, S3-compatible |
| D3 | Embedding 768 chiều (giảm từ 3072) | Tiết kiệm dung lượng DB |
| D4 | Xử lý RAG đồng bộ trong request `/api/documents/upload` | Vercel Hobby cho tới 300s/function — đủ cho quy mô cá nhân, không cần queue |
| D5 | `leaderboard_view` cố ý bypass RLS (view owner-privileged) | Cần tổng hợp cross-user; chỉ lộ số liệu tổng hợp, KHÔNG lộ nội dung câu trả lời |
| D6 | Parser Markdown/callout viết thành module thuần túy, độc lập webhook | Tái sử dụng cho nguồn sync khác sau này |
| D7 | Model AI IDs tạm hoãn | Tên model Gemini trong spec (`gemini-2.5-pro`, `gemini-embedding-2`) có thể đã đổi; sẽ verify khi build feature AI |
| **D8** | **HOÃN RAG / tài liệu cá nhân. Xây LÕI thuần Next.js fullstack (Vercel, $0, 1 deploy). KHÔNG dùng FastAPI/Python.** | RAG là tính năng phụ; toàn bộ độ phức tạp (Python service, embedding model, đa nền deploy) đến từ nó. Đúng nguyên tắc "chỉ thêm phức tạp khi thực sự cần". Thêm RAG sau nếu nhóm thật sự cần mang tài liệu ngoài vào. |
| D9 | Tách code `client/` + `server/` **trong cùng 1 app Next.js** (không phải 2 service) | Tổ chức rõ ràng: `client/` = UI, `server/` = API/db/AI. `app/` (routes) buộc ở gốc theo Next.js |

## 5. Giả định (assumptions)

- Chưa có tài khoản/API key thật cho Supabase, R2, Gemini, GitHub webhook → dùng `.env.example` +
  `SETUP.md`, chưa test live trong pass này.
- `types/database.types.ts` viết tay khớp schema; khi có Supabase thật sẽ regenerate bằng
  `supabase gen types typescript`.
- Dùng root `app/` (không `src/`) để khớp các đường dẫn route trong spec.

## 6. Ràng buộc

- Public sign-up TẮT. Admin thêm email thủ công / qua `/admin/invite`.
- (HOÃN — chỉ áp dụng khi làm RAG sau này) File upload: PDF/DOCX/PPTX tối đa 20MB, PDF tối đa 50
  trang; presigned URL R2 hết hạn ~15 phút, bucket private.

## 7. Biến môi trường

Xem `.env.example`. Nhóm: Supabase (3), Gemini (1), R2 (4), GitHub webhook (1), Admin (1).

## 8. Lịch sử pass

- **Pass 1 (đang làm)**: Scaffold Next.js/Tailwind/Shadcn + toàn bộ SQL schema/RLS/migrations. Xem
  `check_list.md`.
