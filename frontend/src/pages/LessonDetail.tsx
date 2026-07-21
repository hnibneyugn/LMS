import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { ApiError } from "@/lib/api"
import { errorMessage } from "@/lib/files"
import { getLesson, setLessonProgress, type LessonDetail } from "@/lib/lessons"

export function LessonDetailPage() {
  const { slug } = useParams<{ slug: string }>()
  const [lesson, setLesson] = useState<LessonDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!slug) return
    let cancelled = false
    setLoading(true)
    setNotFound(false)
    setError(null)
    getLesson(slug)
      .then((data) => {
        if (!cancelled) setLesson(data)
      })
      .catch((err) => {
        if (cancelled) return
        // 404 gets its own screen; anything else is a banner over the page.
        if (err instanceof ApiError && err.status === 404) setNotFound(true)
        else setError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    // Guards against a stale response landing after the user navigated to
    // the next chapter -- this page re-fetches on every slug change.
    return () => {
      cancelled = true
    }
  }, [slug])

  async function toggleDone() {
    if (!lesson || saving) return
    const next = !lesson.done
    // Optimistic: flip now, roll back if the write fails. Reading feels
    // instant and a failed write must not leave the box lying.
    setLesson({ ...lesson, done: next })
    setSaving(true)
    setError(null)
    try {
      const result = await setLessonProgress(lesson.id, next)
      setLesson((current) =>
        current === null ? current : { ...current, ...result },
      )
    } catch (err) {
      setLesson((current) =>
        current === null ? current : { ...current, done: !next },
      )
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="p-8 text-center text-sm text-gray-500">Đang tải…</p>
  }

  if (notFound || !lesson) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-8 text-center">
        <p className="text-sm text-gray-600">Không tìm thấy bài học.</p>
        <Link to="/lessons" className="text-sm underline">
          Về danh sách bài học
        </Link>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <div className="space-y-2">
        <Link to="/lessons" className="text-sm text-gray-500 underline">
          ← Bài học
        </Link>
        {lesson.source_file_name && (
          <p className="text-xs text-gray-500">{lesson.source_file_name}</p>
        )}
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-xl font-semibold">{lesson.title}</h1>
          <label className="flex shrink-0 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={lesson.done}
              disabled={saving}
              onChange={() => void toggleDone()}
            />
            Đã học
          </label>
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* No rehype-raw: react-markdown drops raw HTML by default, and lesson
          text comes from user-uploaded documents. Keep it that way. */}
      <article className="prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{lesson.content_md}</ReactMarkdown>
      </article>

      <nav className="flex justify-between gap-4 border-t pt-4 text-sm">
        {lesson.prev ? (
          <Link to={`/lessons/${lesson.prev.slug}`} className="underline">
            ← {lesson.prev.title}
          </Link>
        ) : (
          <span />
        )}
        {lesson.next ? (
          <Link to={`/lessons/${lesson.next.slug}`} className="text-right underline">
            {lesson.next.title} →
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </div>
  )
}
