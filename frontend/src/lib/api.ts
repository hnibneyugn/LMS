import { supabase } from "./supabase"

const BASE = import.meta.env.VITE_API_BASE_URL as string

/** Call the FastAPI backend, attaching the Bearer token from the Supabase session. */
export async function apiFetch(path: string, options: RequestInit = {}) {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error("Chưa đăng nhập")

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...(options.headers ?? {}), Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`API ${path} lỗi ${res.status}`)
  return res.json()
}
