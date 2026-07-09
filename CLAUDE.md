# CLAUDE.md — Personal LMS

Hướng dẫn cho Claude khi làm việc trên codebase này. Đọc file này + `project_context.md` +
`architecture.md` + `check_list.md` trước khi code.

## Dự án là gì

Personal LMS (Learning Management System) cho nhóm nhỏ **< 10 người** (invite-only, không public).
Nội dung học viết bằng Markdown trong Obsidian Vault của admin → auto-sync lên web. Người dùng học
lý thuyết, làm bài tự luận, được AI chấm điểm + phản biện (Socratic), upload tài liệu cá nhân làm
ngữ cảnh RAG.

## Nguyên tắc thiết kế (BẤT BIẾN)

1. **Đơn giản, chi phí $0** — dùng free tier. Chỉ thêm phức tạp khi thực sự cần.
2. **Cách ly dữ liệu nghiêm ngặt** — mọi dữ liệu riêng tư (câu trả lời, điểm, chat, tài liệu) phải
   được bảo vệ bằng Row Level Security (RLS) theo `auth.uid() = user_id`.
3. **Ngôn ngữ**: nội dung hiển thị cho user = **tiếng Việt**; code, tên bảng/cột/biến, comment kỹ
   thuật, commit = **tiếng Anh**.
4. **Graceful degradation** — một file/tác vụ AI lỗi KHÔNG được làm sập cả pipeline. Luôn try/catch,
   cập nhật trạng thái lỗi, cho phép retry.
5. **Không dùng NoSQL** — mọi thứ (kể cả vector, dữ liệu bán cấu trúc) lưu trong Postgres
   (`jsonb` + `pgvector`).

## Tech stack (CHỐT CỨNG — không đổi)

| Lớp | Công nghệ |
|---|---|
| Framework | Next.js 14+ App Router, TypeScript |
| UI | Tailwind CSS, Shadcn UI |
| Charts | Tremor (ưu tiên) / Recharts |
| Database | Supabase (Postgres) + extension `pgvector` |
| File storage | Cloudflare R2 (S3-compatible) — **KHÔNG dùng Supabase Storage** |
| Auth | Supabase Auth — Magic Link (email OTP), invite-only |
| AI | Google Gemini qua Vercel AI SDK (`@ai-sdk/google`) |
| Sync | GitHub Webhook → `/api/sync` |
| Hosting | Vercel (Hobby/Free) |

> **Model IDs (chat + embedding) — TẠM HOÃN.** Sẽ chốt khi build feature AI. Xem `check_list.md`.

## Cấu trúc thư mục

Code chia làm 2 nửa **client/** và **server/**. Riêng `app/` (routes) BẮT BUỘC ở gốc — Next.js
App Router chỉ nhận `app/` ở root hoặc `src/app/`, không cho nằm trong `client/`. Nên `app/` giữ
routes mỏng, gọi sang `client/` (UI) và `server/` (logic).

```
app/                        # Next.js App Router — routes + API routes (thin, ở gốc)
client/                     # Mọi thứ chạy phía browser / UI
  components/ui/            # Shadcn components (shadcn add đổ vào đây)
  lib/utils.ts             # cn()
  supabase/client.ts       # Browser Supabase client (anon key, RLS)
server/                     # Server-only + domain types/config dùng chung
  supabase/server.ts       # Server client (cookies, anon key)
  supabase/admin.ts        # Service-role client (server-only, webhook)
  config/callout-types.ts  # Whitelist QUESTION_TYPES — single source of truth
  types/database.types.ts  # Type khớp DB schema
  (sau: parser/, ai/, rag/, db/ ...)
supabase/
  migrations/              # SQL migrations (nguồn chân lý của schema)
```

## Quy ước code

- Route/folder dùng root `app/` (không dùng `src/`). `app/` chỉ ở gốc; logic nằm ở `client/`+`server/`.
- Import alias: `@/*` trỏ về root → dùng `@/client/...`, `@/server/...`.
- **Ranh giới client/server**: `client/` chỉ được import **type-only** từ `server/` (bị xoá lúc
  build), KHÔNG import runtime. `server/` giữ cả type/config dùng chung (callout-types, database.types)
  vì chúng là domain của DB/parser.
- Tất cả secret qua biến môi trường (xem `.env.example`). KHÔNG hardcode key.
- `SUPABASE_SERVICE_ROLE_KEY` chỉ dùng server-side (`server/supabase/admin.ts`, có `import 'server-only'`)
  — không bao giờ import vào client component.
- `callout-types.ts` là nguồn duy nhất định nghĩa loại câu hỏi — parser và DB CHECK constraint phải
  đồng bộ với nó.

## Trạng thái hiện tại

Đang ở **Pass 1: Scaffold + Schema** (bước 1–2 trong 14 bước). Xem `check_list.md` để biết chi tiết
việc đã/đang/sẽ làm. Các feature (auth flow, parser, AI, RAG, dashboard...) hoãn sang pass sau.

## Verify sau mỗi thay đổi

- `npm run lint` và `npm run build` phải sạch.
- Với thay đổi có runtime: chạy thử luồng thật (`npm run dev`), đừng chỉ dựa vào typecheck.
- SQL: đọc lại migration theo thứ tự, đảm bảo RLS bật cho mọi bảng riêng tư.
