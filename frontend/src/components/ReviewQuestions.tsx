import { useState } from "react"
import { errorMessage } from "@/lib/files"
import {
  getQuestions,
  regenerateQuestions,
  QUESTION_TYPE_LABELS,
  type ReviewQuestion,
} from "@/lib/lessons"
import { gradeAnswer, getAttempts } from "@/lib/quiz"

/** Per-question result shown after grading (or loaded from a past attempt). */
interface Result {
  score: number
  missing_points: string[]
  comment: string
}

/**
 * Review questions for one lesson, with inline grading (#4). Generation is
 * lazy (first click). For each question the learner types an answer and submits
 * it; the AI score + feedback + missing points show inline. Past attempts are
 * loaded on open so a graded question stays graded across reloads.
 */
export function ReviewQuestions({ slug }: { slug: string }) {
  const [questions, setQuestions] = useState<ReviewQuestion[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Per-question UI state, keyed by question id.
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [results, setResults] = useState<Record<string, Result>>({})
  const [grading, setGrading] = useState<Record<string, boolean>>({})
  const [rowError, setRowError] = useState<Record<string, string>>({})

  async function loadQuestions(regenerate: boolean) {
    setLoading(true)
    setError(null)
    try {
      const data = regenerate
        ? await regenerateQuestions(slug)
        : await getQuestions(slug)
      setQuestions(data)
      // Regenerated questions are brand new -- drop any prior answers/results.
      if (regenerate) {
        setAnswers({})
        setResults({})
        setRowError({})
      } else {
        const attempts = await getAttempts(slug)
        const loaded: Record<string, Result> = {}
        for (const a of attempts) {
          loaded[a.question_id] = {
            score: a.score,
            missing_points: a.missing_points,
            comment: a.comment,
          }
        }
        setResults(loaded)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  async function submit(questionId: string) {
    const answer = (answers[questionId] ?? "").trim()
    if (!answer || grading[questionId]) return
    setGrading((g) => ({ ...g, [questionId]: true }))
    setRowError((e) => ({ ...e, [questionId]: "" }))
    try {
      const result = await gradeAnswer(questionId, answer)
      setResults((r) => ({
        ...r,
        [questionId]: {
          score: result.score,
          missing_points: result.missing_points,
          comment: result.comment,
        },
      }))
    } catch (err) {
      setRowError((e) => ({ ...e, [questionId]: errorMessage(err) }))
    } finally {
      setGrading((g) => ({ ...g, [questionId]: false }))
    }
  }

  function retry(questionId: string) {
    // Clear the shown result so the textarea returns; the answer is kept so the
    // learner can edit rather than retype.
    setResults((r) => {
      const next = { ...r }
      delete next[questionId]
      return next
    })
  }

  return (
    <section className="space-y-4 border-t pt-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">Câu hỏi ôn tập</h2>
        {questions && !loading && (
          <button
            type="button"
            onClick={() => void loadQuestions(true)}
            className="text-sm text-gray-500 underline"
          >
            Sinh lại
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading && <p className="text-sm text-gray-500">Đang tải…</p>}

      {!loading && questions === null && (
        <button
          type="button"
          onClick={() => void loadQuestions(false)}
          className="rounded-md border px-4 py-2 text-sm hover:bg-gray-50"
        >
          Sinh câu hỏi ôn tập
        </button>
      )}

      {!loading && questions !== null && (
        <ol className="space-y-6">
          {questions.map((q) => {
            const result = results[q.id]
            return (
              <li key={q.id} className="space-y-2">
                <div className="space-y-1">
                  <span className="inline-block rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                    {QUESTION_TYPE_LABELS[q.type]}
                  </span>
                  <p className="text-sm font-medium">{q.question_text}</p>
                </div>

                {result ? (
                  <div className="space-y-2 rounded-md border bg-gray-50 p-3">
                    <p className="text-sm font-semibold">Điểm: {result.score}/10</p>
                    {result.comment && (
                      <p className="text-sm">{result.comment}</p>
                    )}
                    {result.missing_points.length > 0 && (
                      <div className="text-sm">
                        <p className="font-medium">Ý còn thiếu:</p>
                        <ul className="list-disc pl-5">
                          {result.missing_points.map((m, i) => (
                            <li key={i}>{m}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => retry(q.id)}
                      className="text-sm text-gray-500 underline"
                    >
                      Làm lại
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <textarea
                      value={answers[q.id] ?? ""}
                      onChange={(e) =>
                        setAnswers((a) => ({ ...a, [q.id]: e.target.value }))
                      }
                      disabled={grading[q.id]}
                      rows={3}
                      className="w-full rounded-md border p-2 text-sm"
                      placeholder="Nhập câu trả lời của bạn…"
                    />
                    {rowError[q.id] && (
                      <p className="text-sm text-red-600">{rowError[q.id]}</p>
                    )}
                    <button
                      type="button"
                      onClick={() => void submit(q.id)}
                      disabled={grading[q.id] || !(answers[q.id] ?? "").trim()}
                      className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
                    >
                      {grading[q.id] ? "Đang chấm…" : "Nộp bài"}
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
