import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { supabase } from "@/lib/supabase"
import { errorMessage } from "@/lib/files"
import { getDashboardMe, getLeaderboard, type DashboardMe, type LeaderRow } from "@/lib/dashboard"
import { Button } from "@/components/ui/button"

const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"]

/** "yyyy-mm-dd" -> Vietnamese short weekday, parsed as a local date (no TZ shift). */
function dayLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number)
  return WEEKDAYS[new Date(y, m - 1, d).getDay()]
}

export function Dashboard() {
  const navigate = useNavigate()
  const [email, setEmail] = useState<string | null>(null)
  const [me, setMe] = useState<DashboardMe | null>(null)
  const [board, setBoard] = useState<LeaderRow[] | null>(null)
  const [meError, setMeError] = useState<string | null>(null)
  const [boardError, setBoardError] = useState<string | null>(null)
  const [signOutError, setSignOutError] = useState<string | null>(null)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setEmail(data.user?.email ?? null))
    getDashboardMe().then(setMe).catch((e) => setMeError(errorMessage(e)))
    getLeaderboard().then(setBoard).catch((e) => setBoardError(errorMessage(e)))
  }, [])

  async function handleSignOut() {
    const { error } = await supabase.auth.signOut()
    if (error) {
      setSignOutError("Không đăng xuất được. Vui lòng thử lại.")
      return
    }
    navigate("/login", { replace: true })
  }

  const chartData = me?.weekly_questions.map((p) => ({ label: dayLabel(p.date), count: p.count })) ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Bảng điều khiển</h1>
          {email && <p className="text-sm text-gray-500">{email}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => navigate("/lessons")}>Bài học</Button>
          <Button variant="outline" onClick={() => navigate("/files")}>
            Tài liệu của tôi
          </Button>
          <Button variant="outline" onClick={() => navigate("/account")}>
            Tài khoản
          </Button>
          <Button variant="outline" onClick={handleSignOut}>
            Đăng xuất
          </Button>
        </div>
      </header>
      {signOutError && <p className="text-sm text-red-600">{signOutError}</p>}

      {/* Stat cards */}
      {meError ? (
        <p className="text-sm text-red-600">Không tải được thống kê: {meError}</p>
      ) : !me ? (
        <p className="text-sm text-gray-500">Đang tải thống kê…</p>
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Streak hiện tại" value={`${me.current_streak} 🔥`} sub="ngày liên tiếp" />
            <StatCard label="Streak dài nhất" value={`${me.longest_streak}`} sub="ngày" />
            <StatCard
              label="Hoàn thành bài học"
              value={`${me.completion_pct}%`}
              sub={`${me.lessons_completed}/${me.lessons_total} bài`}
            />
          </section>

          <section className="rounded-lg border p-4">
            <h2 className="mb-2 text-sm font-medium text-gray-700">Câu hỏi đã làm 7 ngày qua</h2>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={24} />
                  <Tooltip formatter={(v) => [`${v} câu`, "Đã làm"]} labelFormatter={() => ""} />
                  <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        </>
      )}

      {/* Leaderboard */}
      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-700">Bảng xếp hạng chuyên cần</h2>
        {boardError ? (
          <p className="text-sm text-red-600">Không tải được bảng xếp hạng: {boardError}</p>
        ) : !board ? (
          <p className="text-sm text-gray-500">Đang tải…</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-1 pr-2">#</th>
                <th className="py-1 pr-2">Tên</th>
                <th className="py-1 pr-2 text-right">Ngày học</th>
                <th className="py-1 pr-2 text-right">Bài xong</th>
                <th className="py-1 text-right">Câu hỏi</th>
              </tr>
            </thead>
            <tbody>
              {board.map((row, i) => (
                <tr
                  key={row.user_id}
                  className={row.is_me ? "rounded bg-blue-50 font-medium" : ""}
                >
                  <td className="py-1 pr-2">{i + 1}</td>
                  <td className="py-1 pr-2">{row.display_name}</td>
                  <td className="py-1 pr-2 text-right">{row.active_days}</td>
                  <td className="py-1 pr-2 text-right">{row.lessons_completed}</td>
                  <td className="py-1 text-right">{row.total_questions_done}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

function StatCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      <p className="text-xs text-gray-400">{sub}</p>
    </div>
  )
}
