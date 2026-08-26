# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Một nhóm kín **dưới 10 người** (bạn bè/người quen, invite-only), người học trưởng thành, tự học.
Không có lớp, không có giáo viên phân bài — mỗi người tự mang tài liệu của mình vào.

- **Member** — người học. Upload tài liệu của chính mình, duyệt cách cắt chương, đọc bài, làm câu hỏi
  tự luận, tranh luận với AI, xem mình đứng đâu trên bảng chuyên cần.
- **Admin (chủ hệ thống)** — nhận diện qua `ADMIN_EMAIL`. Chỉ có thêm một quyền: mời thành viên
  (`/admin/invite`). Không soạn nội dung, không thấy dữ liệu học của người khác.

**Bối cảnh dùng (đã xác nhận): desktop-first.** Người học ngồi trước máy tính trong một phiên tập
trung — đọc bài dài, gõ trả lời tự luận, chat phản biện. Điện thoại chỉ cần dùng được, không phải
nơi công việc thật diễn ra.

Nội dung hiển thị cho user là **tiếng Việt**.

## Product Purpose

Biến tài liệu chết của chính bạn (`.md` / `.docx` / `.pptx` / `.pdf` có text layer) thành một khoá
học có người chấm: hệ thống extract sang markdown → cắt thành chương → user duyệt → mỗi chương thành
một bài học riêng tư. AI sinh câu hỏi tự luận từ nội dung bài, chấm điểm và phản biện kiểu Socratic.

Thành công = **người ta quay lại học đều**, không phải điểm cao. Cả nhóm chung đúng một thứ: bảng xếp
hạng **số ngày học**.

## Positioning

Ba thứ cùng lúc mà một sản phẩm bên cạnh không sao chép thẳng được:

1. **Bring-your-own-material** — không có giáo trình dùng chung, không kho khoá học. Nội dung học là
   tài liệu người đó tự upload, và chỉ người đó thấy.
2. **Chấm bằng tự luận + phản biện**, không phải trắc nghiệm. AI có toàn bộ `content_md` của bài làm
   ngữ cảnh, chấm dựa trên bài chứ không dựa trên đáp án mẫu (không có đáp án mẫu).
3. **Thi đua chuyên cần, không thi đua điểm.** Vì tài liệu mỗi người mỗi khác, điểm không so sánh
   được — số ngày học thì có.

## Operating Context

- **Vòng đời một tài liệu**: upload (presigned URL → R2) → extract → cắt chương tự động →
  `user_files.draft_outline` → **user duyệt/sửa ở `/files/:id/review`** → ghi nhiều `lessons`
  (`source_file_id` + `order_index`). Một file có thể là cả giáo trình vài trăm trang.
- **Vòng đời một buổi học**: `/lessons` (danh sách) → đọc bài → làm câu hỏi → AI chấm → chat phản
  biện → đánh dấu "Đã học" → `/` dashboard (streak, biểu đồ tuần, bảng xếp hạng).
- **Tài liệu đầu vào rất không đều**: heading sạch hay không, slide vs giáo trình vs note cá nhân,
  chủ đề rời rạc giữa các thành viên. Không giả định môn học nào, không giả định chia theo tuần
  (`lessons.topic`/`week` luôn NULL — phân nhóm đi theo file nguồn).
- **Mốc ngày là giờ VN (UTC+7)** ở cả nơi ghi lẫn nơi đọc. Streak reset khi qua 0h VN mà chưa học.
- Đăng nhập: mật khẩu (đường chính) hoặc mã OTP qua email (quên mật khẩu / chưa đặt mật khẩu).

## Capabilities and Constraints

**Đang chạy** (sub-project #0–#7 xong, xem `check_list.md`): auth invite-only, upload → extract →
duyệt chương, đọc bài + đánh dấu đã học, AI sinh câu hỏi, AI chấm điểm, Socratic chat streaming,
dashboard + leaderboard, mời thành viên. Còn lại: #8 deploy.

**Ràng buộc bất biến** (chi tiết ở `CLAUDE.md`, `project_context.md`):

- **Chi phí $0** — mọi thứ trên free tier. Ảnh hưởng thật tới thiết kế: quota AI có hạn
  (`gemini-3.1-flash-lite`), không có dịch vụ ảnh/font trả tiền, không CDN riêng.
- **Cách ly dữ liệu nghiêm ngặt** — mọi bảng riêng tư có RLS `auth.uid() = user_id`. Chỉ
  `leaderboard_view` là số liệu tổng hợp cross-user (không bao giờ lộ nội dung câu trả lời).
- **Invite-only, public sign-up tắt.** Không có trang đăng ký, không có luồng marketing tự phục vụ.
- **Graceful degradation** — một file lỗi hoặc một call AI lỗi không được làm sập pipeline; luôn có
  trạng thái lỗi hiển thị được và đường retry.
- Không OCR: PDF không có text layer bị từ chối kèm lý do rõ ràng, không trả markdown rác.
- Frontend là **SPA thuần (React + Vite), không SSR**; chart = Recharts; UI = Tailwind v4 + Shadcn.

**Từ vựng dùng trong sản phẩm**: tài liệu (file nguồn) · chương (draft trước khi duyệt) · bài học
(lesson) · câu hỏi ôn tập · chuyên cần / streak / số ngày học.

## Brand Commitments

Chưa có. "Personal LMS" là **tên làm việc**, không phải tên sản phẩm — user xác nhận sẽ chốt tên sau,
và đề xuất tên/wordmark thuộc phần visual world (không thuộc file này). Không có logo, không có màu
hay font ràng buộc.

Ràng buộc duy nhất về ngôn ngữ: chuỗi hiển thị cho user = tiếng Việt; code/tên biến/commit = tiếng Anh.

## Evidence on Hand

- Nội dung thật duy nhất là **tài liệu do từng user upload** — riêng tư, không dùng được làm ví dụ
  công khai, không screenshot ra ngoài được.
- **Không có** testimonial, logo khách hàng, số liệu người dùng, benchmark, pricing, case study.
  Sản phẩm chưa deploy (#8), chưa có ai ngoài nhóm dùng. Đừng bịa những thứ này.
- Ảnh chụp UI hiện tại là bằng chứng duy nhất về giao diện đang có: `frontend/src/pages/*`,
  token mặc định Shadcn neutral ở `frontend/src/index.css`.
- `DESIGN-claude.md` ở gốc repo là **phân tích giao diện của claude.ai**, không phải design system
  của dự án này. Đừng đọc nó như visual authority của sản phẩm.

## Product Principles

1. **Tài liệu của người ta là nhân vật chính.** Mọi surface tồn tại để đưa họ tới nội dung của chính
   họ nhanh hơn; giao diện không được cạnh tranh với bài đọc.
2. **Thưởng cho sự đều đặn, không thưởng cho điểm.** Chỗ nào phải chọn giữa khoe điểm và khoe chuỗi
   ngày học thì chọn chuỗi ngày.
3. **Đọc lâu và gõ dài là công việc thật.** Desktop, một phiên tập trung — ưu tiên bề rộng đọc, khả
   năng quét, và ô soạn thảo tử tế hơn là hiệu ứng.
4. **Riêng tư là mặc định, và phải thấy được là riêng tư.** Người dùng phải luôn hiểu cái gì chỉ
   mình thấy và cái gì cả nhóm thấy (chỉ có số ngày học).
5. **Lỗi là một trạng thái của sản phẩm, không phải ngoại lệ.** Extract lỗi, hết quota AI, PDF scan —
   đều phải có chỗ hiển thị đàng hoàng và một đường đi tiếp.

## Accessibility & Inclusion

Chưa xác lập yêu cầu riêng nào cho sản phẩm này (nhóm nhỏ, chưa có nhu cầu cụ thể được nêu). Mặc
định vẫn giữ nền tảng: contrast đủ, focus thấy được, điều hướng bàn phím cho luồng đọc–làm bài.
