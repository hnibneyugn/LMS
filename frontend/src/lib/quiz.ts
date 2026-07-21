import { apiFetch } from "@/lib/api"

export interface GradeResult {
  score: number
  missing_points: string[]
  comment: string
  created_at: string
}

/** Latest graded attempt for one question of a lesson. */
export interface Attempt {
  question_id: string
  user_answer: string
  score: number
  missing_points: string[]
  comment: string
  created_at: string
}

export function gradeAnswer(
  questionId: string,
  answer: string,
): Promise<GradeResult> {
  return apiFetch("/api/quiz/grade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_id: questionId, user_answer: answer }),
  })
}

export function getAttempts(slug: string): Promise<Attempt[]> {
  return apiFetch(`/api/quiz/attempts/${encodeURIComponent(slug)}`)
}
