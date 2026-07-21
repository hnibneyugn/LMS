import { useState } from "react"
import { errorMessage } from "@/lib/files"
import {
  getQuestions,
  regenerateQuestions,
  QUESTION_TYPE_LABELS,
  type ReviewQuestion,
} from "@/lib/lessons"

/**
 * Read-only review questions for one lesson. Generation is lazy: nothing is
 * fetched until the user asks (first click), matching the backend's
 * cache-or-generate contract. Answering + grading is #4, not here.
 */
export function ReviewQuestions({ slug }: { slug: string }) {
  const [questions, setQuestions] = useState<ReviewQuestion[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load(regenerate: boolean) {
    setLoading(true)
    setError(null)
    try {
      const data = regenerate
        ? await regenerateQuestions(slug)
        : await getQuestions(slug)
      setQuestions(data)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-4 border-t pt-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">Câu hỏi ôn tập</h2>
        {questions && !loading && (
          <button
            type="button"
            onClick={() => void load(true)}
            className="text-sm text-gray-500 underline"
          >
            Sinh lại
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading && (
        <p className="text-sm text-gray-500">Đang sinh câu hỏi…</p>
      )}

      {!loading && questions === null && (
        <button
          type="button"
          onClick={() => void load(false)}
          className="rounded-md border px-4 py-2 text-sm hover:bg-gray-50"
        >
          Sinh câu hỏi ôn tập
        </button>
      )}

      {!loading && questions !== null && (
        <ol className="space-y-3">
          {questions.map((q) => (
            <li key={q.id} className="space-y-1">
              <span className="inline-block rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {QUESTION_TYPE_LABELS[q.type]}
              </span>
              <p className="text-sm">{q.question_text}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
