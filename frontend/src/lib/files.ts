import { ApiError, apiFetch } from "@/lib/api"

export type FileType = "md" | "docx" | "pptx" | "pdf"

export type ProcessingStatus =
  | "pending"
  | "processing"
  | "ready_for_review"
  | "error"
  | "done"

export interface UserFile {
  id: string
  file_name: string
  file_type: FileType
  file_size: number | null
  processing_status: ProcessingStatus
  error_message: string | null
  uploaded_at: string | null
  chapter_count: number | null
}

export interface DraftChapter {
  title: string
  content_md: string
  order_index: number
}

export interface UserFileDetail extends UserFile {
  draft_outline: DraftChapter[] | null
}

export interface ConfirmChapter {
  title: string
  source_indexes: number[]
}

export const MAX_FILE_BYTES = 20 * 1024 * 1024
export const ACCEPTED_EXTENSIONS = [".md", ".docx", ".pptx", ".pdf"] as const

/** File extension -> backend file_type, or null if unsupported. */
export function fileTypeOf(fileName: string): FileType | null {
  const ext = fileName.toLowerCase().split(".").pop()
  if (ext === "md" || ext === "docx" || ext === "pptx" || ext === "pdf") return ext
  return null
}

export function listFiles(): Promise<UserFile[]> {
  return apiFetch("/api/files")
}

export function getFile(fileId: string): Promise<UserFileDetail> {
  return apiFetch(`/api/files/${fileId}`)
}

export async function processFile(fileId: string): Promise<void> {
  await apiFetch(`/api/files/${fileId}/process`, { method: "POST" })
}

export function confirmChapters(
  fileId: string,
  chapters: ConfirmChapter[],
): Promise<{ lesson_count: number }> {
  return apiFetch(`/api/files/${fileId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chapters }),
  })
}

export type UploadStep = "presigning" | "uploading" | "processing"

/**
 * presign -> PUT straight to R2 -> ask the backend to process. Returns file_id.
 *
 * Each step reports through `onStep` so the page can say which one is running
 * instead of showing a fake progress bar.
 */
export async function uploadFile(
  file: File,
  onStep: (step: UploadStep) => void,
): Promise<string> {
  const fileType = fileTypeOf(file.name)
  if (!fileType) throw new Error("Định dạng không hỗ trợ. Chỉ nhận .md, .docx, .pptx, .pdf.")
  if (file.size > MAX_FILE_BYTES) throw new Error("File vượt quá giới hạn 20MB.")
  if (file.size === 0) throw new Error("File rỗng.")

  onStep("presigning")
  const { file_id, upload_url } = await apiFetch("/api/files/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_name: file.name,
      file_type: fileType,
      file_size: file.size,
    }),
  })

  onStep("uploading")
  // Plain fetch, NOT apiFetch: a presigned URL carries its own signature and
  // adding an Authorization header invalidates it. This is the only place in
  // the app that talks to something other than our own backend.
  const putRes = await fetch(upload_url, { method: "PUT", body: file })
  if (!putRes.ok) throw new Error("Tải file lên thất bại. Hãy thử lại.")

  onStep("processing")
  await processFile(file_id)
  return file_id
}

/** Message for any thrown value, preferring the backend's Vietnamese detail. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError || err instanceof Error) return err.message
  return "Đã có lỗi xảy ra."
}
