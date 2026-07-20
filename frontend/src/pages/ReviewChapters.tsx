import { useCallback, useEffect, useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api"
import {
  confirmChapters,
  errorMessage,
  getFile,
  type ConfirmChapter,
  type DraftChapter,
} from "@/lib/files"

/** A chapter as edited on this page: the payload shape plus its full text. */
interface EditableChapter extends ConfirmChapter {
  content: string
  charCount: number
}

function toEditable(draft: DraftChapter[], indexes: number[], title: string): EditableChapter {
  const content = indexes.map((i) => draft[i].content_md).join("\n\n")
  return {
    title,
    source_indexes: indexes,
    // The whole chapter, not an excerpt: deciding what to merge or drop means
    // reading the thing. `getFile` already shipped every chapter's content_md,
    // so this costs no extra request -- collapsing is purely a CSS clamp.
    content,
    charCount: content.length,
  }
}

export function ReviewChapters() {
  const { fileId } = useParams<{ fileId: string }>()
  const navigate = useNavigate()

  const [fileName, setFileName] = useState("")
  const [readOnly, setReadOnly] = useState(false)
  const [draft, setDraft] = useState<DraftChapter[]>([])
  const [chapters, setChapters] = useState<EditableChapter[]>([])
  const [removed, setRemoved] = useState<{ at: number; chapter: EditableChapter } | null>(null)
  // Keyed by chapter identity (source_indexes[0], same value as the React
  // `key` below), not list position -- a position-keyed set would point at
  // the wrong row once a drop shifts later rows up.
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Shared by the mount effect and the confirm-409 resync (Finding 3): both
  // need to fetch the file and re-derive the same page state from it.
  const loadFile = useCallback(async (id: string) => {
    const file = await getFile(id)
    const outline = file.draft_outline ?? []
    setFileName(file.file_name)
    setReadOnly(file.processing_status === "done")
    setDraft(outline)
    setChapters(outline.map((c, i) => toEditable(outline, [i], c.title)))
    // The old edit-in-progress state no longer matches the freshly loaded
    // chapters (indexes/identities may differ), so drop it rather than risk
    // "Hoàn tác" inserting a stale chapter into the new list.
    setRemoved(null)
  }, [])

  useEffect(() => {
    if (!fileId) return
    loadFile(fileId)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false))
  }, [fileId, loadFile])

  function renameChapter(position: number, title: string) {
    setChapters((prev) =>
      prev.map((c, i) => (i === position ? { ...c, title } : c)),
    )
  }

  function mergeIntoPrevious(position: number) {
    setChapters((prev) => {
      const previous = prev[position - 1]
      const current = prev[position]
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

  function toggleExpanded(chapterKey: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(chapterKey)) next.delete(chapterKey)
      else next.add(chapterKey)
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
      // Spec §7: a 409 means the file moved on without us (e.g. confirmed
      // from another tab) -- resync instead of leaving a stale editable
      // outline behind the error banner. Reuses the same load path as the
      // mount effect so the derived state (readOnly included) matches
      // whatever the backend actually holds now.
      if (err instanceof ApiError && err.status === 409 && fileId) {
        await loadFile(fileId).catch(() => {
          // Resync itself failed -- keep the 409 detail on screen, that's
          // still more useful than nothing.
        })
      }
    }
  }

  if (loading) return <p className="p-8 text-sm text-gray-500">Đang tải…</p>

  const canSubmit =
    !readOnly &&
    !submitting &&
    chapters.length > 0 &&
    chapters.every((c) => c.title.trim().length > 0 && c.title.trim().length <= 200)

  return (
    <div className="mx-auto max-w-3xl p-8 pb-28">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Duyệt chương</h1>
        <Link to="/files" className="text-sm text-gray-500 underline">
          Tài liệu của tôi
        </Link>
      </div>
      <p className="mt-1 text-sm text-gray-500">{fileName}</p>

      {readOnly && (
        <p className="mt-4 rounded bg-green-50 p-3 text-sm text-green-800">
          File đã duyệt xong. Không sửa được nữa.
        </p>
      )}
      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <ul className="mt-6 space-y-4">
        {chapters.map((chapter, position) => {
          return (
            <li key={chapter.source_indexes[0]} className="rounded-lg border p-4">
              <Input
                value={chapter.title}
                disabled={readOnly}
                maxLength={200}
                onChange={(e) => renameChapter(position, e.target.value)}
              />
              <p className="mt-2 text-xs text-gray-500">
                {chapter.charCount.toLocaleString("vi-VN")} ký tự
                {chapter.source_indexes.length > 1 &&
                  ` · gộp từ ${chapter.source_indexes.length} chương`}
              </p>
              {expanded.has(chapter.source_indexes[0]) ? (
                <>
                  {/* Scrollable rather than inline: a chapter runs up to 8000
                      characters, and letting that push the page would bury the
                      merge/drop buttons the user came here to press. */}
                  <div className="mt-2 max-h-96 overflow-y-auto rounded border bg-gray-50 p-3 text-sm whitespace-pre-wrap text-gray-700">
                    {chapter.content}
                  </div>
                  <button
                    type="button"
                    onClick={() => toggleExpanded(chapter.source_indexes[0])}
                    className="mt-1 text-sm text-gray-600 underline"
                  >
                    Thu gọn
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => toggleExpanded(chapter.source_indexes[0])}
                  className="mt-2 w-full text-left text-sm text-gray-600"
                >
                  <span className="line-clamp-3">{chapter.content}</span>
                  <span className="mt-1 block underline">Xem toàn bộ nội dung</span>
                </button>
              )}
              {!readOnly && (
                <div className="mt-3 flex gap-2">
                  {position > 0 && (
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
          {draft.length > 0
            ? "Đã bỏ hết chương. Hoàn tác hoặc tải lại trang để bắt đầu lại."
            : "Chưa có chương nào để duyệt."}
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

      {!readOnly && chapters.length > 0 && (
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
