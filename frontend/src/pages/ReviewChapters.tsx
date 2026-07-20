import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  confirmChapters,
  errorMessage,
  getFile,
  type ConfirmChapter,
  type DraftChapter,
} from "@/lib/files"

/** A chapter as edited on this page: the payload shape plus a preview. */
interface EditableChapter extends ConfirmChapter {
  preview: string
  charCount: number
}

const PREVIEW_CHARS = 300

function toEditable(draft: DraftChapter[], indexes: number[], title: string): EditableChapter {
  const content = indexes.map((i) => draft[i].content_md).join("\n\n")
  return {
    title,
    source_indexes: indexes,
    preview: content.slice(0, PREVIEW_CHARS),
    charCount: content.length,
  }
}

/**
 * Merging is only legal when the two chapters' original draft indexes are
 * contiguous. Two chapters that are adjacent *in the current list* are not
 * necessarily adjacent in the original draft outline -- a chapter dropped
 * between them leaves a gap (e.g. previous=[0], current=[2] after index 1
 * was removed). Merging those would produce source_indexes=[0,2], which the
 * backend rejects with 400 because it is ascending but not contiguous.
 */
function canMergeWithPrevious(previous: EditableChapter, current: EditableChapter): boolean {
  const previousLast = previous.source_indexes[previous.source_indexes.length - 1]
  return previousLast + 1 === current.source_indexes[0]
}

export function ReviewChapters() {
  const { fileId } = useParams<{ fileId: string }>()
  const navigate = useNavigate()

  const [fileName, setFileName] = useState("")
  const [readOnly, setReadOnly] = useState(false)
  const [draft, setDraft] = useState<DraftChapter[]>([])
  const [chapters, setChapters] = useState<EditableChapter[]>([])
  const [removed, setRemoved] = useState<{ at: number; chapter: EditableChapter } | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!fileId) return
    getFile(fileId)
      .then((file) => {
        const outline = file.draft_outline ?? []
        setFileName(file.file_name)
        setReadOnly(file.processing_status === "done")
        setDraft(outline)
        setChapters(outline.map((c, i) => toEditable(outline, [i], c.title)))
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [fileId])

  function renameChapter(position: number, title: string) {
    setChapters((prev) =>
      prev.map((c, i) => (i === position ? { ...c, title } : c)),
    )
  }

  function mergeIntoPrevious(position: number) {
    setChapters((prev) => {
      const previous = prev[position - 1]
      const current = prev[position]
      if (!canMergeWithPrevious(previous, current)) return prev
      const merged = toEditable(
        draft,
        [...previous.source_indexes, ...current.source_indexes],
        previous.title,
      )
      return [...prev.slice(0, position - 1), merged, ...prev.slice(position + 1)]
    })
    setRemoved(null)
  }

  function removeChapter(position: number) {
    // Dropping a chapter loses content, so it always leaves one level of undo.
    setRemoved({ at: position, chapter: chapters[position] })
    setChapters((prev) => prev.filter((_, i) => i !== position))
  }

  function undoRemove() {
    if (!removed) return
    setChapters((prev) => [
      ...prev.slice(0, removed.at),
      removed.chapter,
      ...prev.slice(removed.at),
    ])
    setRemoved(null)
  }

  function toggleExpanded(position: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(position)) next.delete(position)
      else next.add(position)
      return next
    })
  }

  async function handleConfirm() {
    if (!fileId) return
    setSubmitting(true)
    setError(null)
    try {
      await confirmChapters(
        fileId,
        chapters.map(({ title, source_indexes }) => ({ title, source_indexes })),
      )
      navigate("/files")
    } catch (err) {
      setError(errorMessage(err))
      setSubmitting(false)
    }
  }

  if (loading) return <p className="p-8 text-sm text-gray-500">Đang tải…</p>

  const canSubmit =
    !readOnly &&
    !submitting &&
    chapters.length > 0 &&
    chapters.every((c) => c.title.trim().length > 0)

  return (
    <div className="mx-auto max-w-3xl p-8 pb-28">
      <h1 className="text-xl font-semibold">Duyệt chương</h1>
      <p className="mt-1 text-sm text-gray-500">{fileName}</p>

      {readOnly && (
        <p className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800">
          File đã duyệt xong. Không sửa được nữa.
        </p>
      )}
      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <ul className="mt-6 space-y-4">
        {chapters.map((chapter, position) => {
          const mergeable = position > 0 && canMergeWithPrevious(chapters[position - 1], chapter)
          return (
            <li key={chapter.source_indexes[0]} className="rounded-lg border p-4">
              <Input
                value={chapter.title}
                disabled={readOnly}
                onChange={(e) => renameChapter(position, e.target.value)}
              />
              <p className="mt-2 text-xs text-gray-500">
                {chapter.charCount.toLocaleString("vi-VN")} ký tự
                {chapter.source_indexes.length > 1 &&
                  ` · gộp từ ${chapter.source_indexes.length} chương`}
              </p>
              <button
                type="button"
                onClick={() => toggleExpanded(position)}
                className="mt-2 w-full text-left text-sm text-gray-600"
              >
                <span
                  className={expanded.has(position) ? "whitespace-pre-wrap" : "line-clamp-3"}
                >
                  {chapter.preview}
                </span>
              </button>
              {!readOnly && (
                <div className="mt-3 flex gap-2">
                  {mergeable && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => mergeIntoPrevious(position)}
                    >
                      Gộp với chương trên
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => removeChapter(position)}
                  >
                    Bỏ chương này
                  </Button>
                </div>
              )}
            </li>
          )
        })}
      </ul>

      {chapters.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-500">
          Đã bỏ hết chương. Hoàn tác hoặc tải lại trang để bắt đầu lại.
        </p>
      )}

      {removed && (
        <div className="mt-4 flex items-center gap-3 rounded bg-gray-100 p-3 text-sm">
          <span>Đã bỏ “{removed.chapter.title}”.</span>
          <Button size="sm" variant="outline" onClick={undoRemove}>
            Hoàn tác
          </Button>
        </div>
      )}

      {!readOnly && (
        <div className="fixed inset-x-0 bottom-0 border-t bg-white p-4">
          <div className="mx-auto flex max-w-3xl items-center justify-between">
            <span className="text-sm text-gray-600">
              Sẽ tạo {chapters.length} bài học
            </span>
            <Button disabled={!canSubmit} onClick={handleConfirm}>
              {submitting ? "Đang lưu…" : "Xác nhận"}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
