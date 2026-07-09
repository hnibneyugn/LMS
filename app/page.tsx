import { Button } from '@/client/components/ui/button';

// Placeholder landing page for Pass 1 (scaffold + schema). Real routes (/login,
// /dashboard, /lessons, ...) are added in later passes — see check_list.md.
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-widest text-muted-foreground">
          Personal LMS
        </p>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Hệ thống học tập chủ động
        </h1>
        <p className="max-w-md text-muted-foreground">
          Nền tảng đã được khởi tạo (scaffold + database schema). Các tính năng đăng nhập, bài học
          và AI sẽ được thêm ở các bước tiếp theo.
        </p>
      </div>
      <Button disabled>Đăng nhập (sắp có)</Button>
    </main>
  );
}
