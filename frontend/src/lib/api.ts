import { supabase } from "./supabase"

const BASE = import.meta.env.VITE_API_BASE_URL as string

/** An HTTP error from the backend, carrying its status and Vietnamese detail. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

/** Call the FastAPI backend, attaching the Bearer token from the Supabase session. */
export async function apiFetch(path: string, options: RequestInit = {}) {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error("Chưa đăng nhập")

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...(options.headers ?? {}), Authorization: `Bearer ${token}` },
  })

  if (!res.ok) {
    // The backend writes user-facing Vietnamese into `detail`; surfacing it
    // beats any message invented here. Falls back only when the body is not
    // the expected shape (a proxy error page, a network-level failure).
    let detail = `Yêu cầu thất bại (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === "string") detail = body.detail
    } catch {
      // Body was not JSON -- keep the fallback.
    }
    throw new ApiError(detail, res.status)
  }
  return res.json()
}
