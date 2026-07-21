import { apiFetch } from "@/lib/api"

export interface Lesson {
  id: string
  slug: string
  title: string
  order_index: number
  source_file_id: string | null
  source_file_name: string | null
  done: boolean
  completed_at: string | null
}

export interface LessonNav {
  slug: string
  title: string
}

export interface LessonDetail extends Lesson {
  content_md: string
  prev: LessonNav | null
  next: LessonNav | null
}

export interface LessonProgress {
  done: boolean
  completed_at: string | null
}

/** Lessons of one source file -- a "book" and its chapters. */
export interface LessonGroup {
  fileId: string | null
  fileName: string
  lessons: Lesson[]
}

export function listLessons(): Promise<Lesson[]> {
  return apiFetch("/api/lessons")
}

export function getLesson(slug: string): Promise<LessonDetail> {
  return apiFetch(`/api/lessons/${encodeURIComponent(slug)}`)
}

export function setLessonProgress(
  lessonId: string,
  done: boolean,
): Promise<LessonProgress> {
  return apiFetch(`/api/lessons/${lessonId}/progress`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ done }),
  })
}

/**
 * Group by source file for display.
 *
 * Relies on the backend already sorting by file name then order_index (with
 * orphans last), so insertion order into the Map is the display order and
 * this does no sorting of its own. Orphans -- lessons whose source file was
 * deleted, source_file_id being ON DELETE SET NULL -- share one "Khác" group.
 */
export function groupLessons(lessons: Lesson[]): LessonGroup[] {
  const groups = new Map<string, LessonGroup>()
  for (const lesson of lessons) {
    const key = lesson.source_file_id ?? ""
    let group = groups.get(key)
    if (!group) {
      group = {
        fileId: lesson.source_file_id,
        fileName: lesson.source_file_name ?? "Khác",
        lessons: [],
      }
      groups.set(key, group)
    }
    group.lessons.push(lesson)
  }
  return [...groups.values()]
}

export type QuestionType = "recall" | "scenario" | "compare" | "explain"

export interface ReviewQuestion {
  id: string
  type: QuestionType
  question_text: string
  order_index: number
}

/** Vietnamese badge label per question type. */
export const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  recall: "Ghi nhớ",
  scenario: "Tình huống",
  compare: "So sánh",
  explain: "Giải thích",
}

/** Cached-or-generate: the backend generates on first call, then serves from DB. */
export function getQuestions(slug: string): Promise<ReviewQuestion[]> {
  return apiFetch(`/api/lessons/${encodeURIComponent(slug)}/questions`)
}

export function regenerateQuestions(slug: string): Promise<ReviewQuestion[]> {
  return apiFetch(
    `/api/lessons/${encodeURIComponent(slug)}/questions/regenerate`,
    { method: "POST" },
  )
}
