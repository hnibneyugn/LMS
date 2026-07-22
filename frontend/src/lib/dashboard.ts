import { apiFetch } from "@/lib/api"

export interface WeeklyPoint {
  date: string // ISO yyyy-mm-dd
  count: number
}

export interface DashboardMe {
  current_streak: number
  longest_streak: number
  weekly_questions: WeeklyPoint[]
  lessons_completed: number
  lessons_total: number
  completion_pct: number
}

export interface LeaderRow {
  user_id: string
  display_name: string
  avatar_url: string | null
  active_days: number
  lessons_completed: number
  total_questions_done: number
  is_me: boolean
}

/** Personal streak / weekly-questions / completion stats for the current user. */
export async function getDashboardMe(): Promise<DashboardMe> {
  return (await apiFetch("/api/dashboard/me")) as DashboardMe
}

/** Group leaderboard, already ranked by number of study days. */
export async function getLeaderboard(): Promise<LeaderRow[]> {
  return (await apiFetch("/api/dashboard/leaderboard")) as LeaderRow[]
}
