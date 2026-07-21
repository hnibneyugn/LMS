import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { errorMessage } from "@/lib/files"
import { groupLessons, listLessons, type Lesson } from "@/lib/lessons"

type Filter = "all" | "todo" | "done"

const FILTER_LABELS: Record<Filter, string> = {
  all: "Tất cả",
  todo: "Chưa học",
  done: "Đã học",
}

function matches(lesson: Lesson, filter: Filter): boolean {
  if (filter === "todo") return !lesson.done
  if (filter === "done") return lesson.done
  return true
}

export function Lessons() {
  const [lessons, setLessons] = useState<Lesson[]>([])
  const [filter, setFilter] = useState<Filter>("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setLessons(await listLessons())
      setError(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Filter first, then group: a group whose every lesson is filtered out
  // should disappear rather than render as an empty heading.
  const groups = groupLessons(lessons.filter((l) => matches(l, filter))).filter(
    (g) => g.lessons.length > 0,
  )

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Bài học của tôi</h1>
        <div className="space-x-4 text-sm text-gray-500">
          <Link to="/files" className="underline">
            Tài liệu
          </Link>
          <Link to="/" className="underline">
            Trang chủ
          </Link>
        </div>
      </div>

      <div className="flex gap-2">
        {(Object.keys(FILTER_LABELS) as Filter[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={
              filter === key
                ? "rounded-md bg-gray-900 px-3 py-1 text-sm text-white"
                : "rounded-md border px-3 py-1 text-sm text-gray-600"
            }
          >
            {FILTER_LABELS[key]}
          </button>
        ))}
      </div>

      {error && (
        <div className="space-y-2">
          <p className="text-sm text-red-600">{error}</p>
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-md border px-3 py-1 text-sm"
          >
            Thử lại
          </button>
        </div>
      )}

      {loading ? (
        <p className="py-8 text-center text-sm text-gray-500">Đang tải…</p>
      ) : lessons.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-500">
          Chưa có bài học nào.{" "}
          <Link to="/files" className="underline">
            Hãy tải tài liệu lên.
          </Link>
        </p>
      ) : groups.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-500">
          Không có bài học nào khớp bộ lọc.
        </p>
      ) : (
        <div className="space-y-6">
          {groups.map((group) => (
            <section key={group.fileId ?? "orphans"} className="space-y-2">
              <div className="flex items-baseline justify-between">
                <h2 className="font-medium">{group.fileName}</h2>
                <span className="text-xs text-gray-500">
                  {group.lessons.filter((l) => l.done).length}/{group.lessons.length} đã học
                </span>
              </div>
              <ul className="divide-y rounded-md border">
                {group.lessons.map((lesson) => (
                  <li key={lesson.id}>
                    <Link
                      to={`/lessons/${lesson.slug}`}
                      className="flex items-center justify-between px-4 py-3 hover:bg-gray-50"
                    >
                      <span className="text-sm">{lesson.title}</span>
                      {lesson.done && (
                        <span className="text-xs text-green-700">Đã học</span>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
