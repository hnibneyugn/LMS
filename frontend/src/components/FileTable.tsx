import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import type { ProcessingStatus, UserFile } from "@/lib/files"

const STUCK_AFTER_MS = 10 * 60 * 1000

const BADGE_CLASS: Record<ProcessingStatus, string> = {
  pending: "bg-gray-100 text-gray-700",
  processing: "bg-blue-100 text-blue-700",
  ready_for_review: "bg-amber-100 text-amber-800",
  error: "bg-red-100 text-red-700",
  done: "bg-green-100 text-green-700",
}

function statusLabel(file: UserFile): string {
  switch (file.processing_status) {
    case "pending":
      return "Chưa xử lý"
    case "processing":
      return "Đang xử lý…"
    case "ready_for_review":
      return file.chapter_count === null
        ? "Chờ duyệt"
        : `Chờ duyệt · ${file.chapter_count} chương`
    case "error":
      return "Lỗi"
    case "done":
      return "Đã duyệt"
  }
}

/**
 * A file whose background task died with the backend stays `processing`
 * forever (a known, accepted risk from #1a). Offering "Xử lý lại" after ten
 * minutes is the escape hatch. The clock runs from `uploaded_at` because the
 * schema records no processing-start time; a file left alone for hours before
 * anyone pressed "Xử lý" therefore shows the button immediately, which is
 * harmless -- pressing it returns 409 and the list refetches.
 */
function looksStuck(file: UserFile): boolean {
  if (file.processing_status !== "processing" || !file.uploaded_at) return false
  return Date.now() - new Date(file.uploaded_at).getTime() > STUCK_AFTER_MS
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return ""
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function FileTable({
  files,
  onProcess,
  busyId,
}: {
  files: UserFile[]
  onProcess: (fileId: string) => void
  busyId: string | null
}) {
  if (files.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-500">
        Chưa có tài liệu nào. Tải lên file đầu tiên để bắt đầu.
      </p>
    )
  }

  return (
    <ul className="divide-y rounded-lg border">
      {files.map((file) => (
        <li key={file.id} className="flex items-center gap-4 p-4">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{file.file_name}</p>
            <p className="text-xs text-gray-500">{formatSize(file.file_size)}</p>
            {file.processing_status === "error" && file.error_message && (
              <p className="mt-1 text-sm text-red-600">{file.error_message}</p>
            )}
          </div>
          <span
            className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${
              BADGE_CLASS[file.processing_status]
            }`}
          >
            {statusLabel(file)}
          </span>
          <div className="w-32 shrink-0 text-right">
            {file.processing_status === "pending" && (
              <Button
                size="sm"
                disabled={busyId === file.id}
                onClick={() => onProcess(file.id)}
              >
                Xử lý
              </Button>
            )}
            {(file.processing_status === "error" || looksStuck(file)) && (
              <Button
                size="sm"
                variant="outline"
                disabled={busyId === file.id}
                onClick={() => onProcess(file.id)}
              >
                Xử lý lại
              </Button>
            )}
            {file.processing_status === "ready_for_review" && (
              <Button
                size="sm"
                render={<Link to={`/files/${file.id}/review`}>Duyệt chương</Link>}
              />
            )}
            {file.processing_status === "done" && (
              <Button
                size="sm"
                variant="outline"
                render={<Link to={`/files/${file.id}/review`}>Xem lại</Link>}
              />
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
