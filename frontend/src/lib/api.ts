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

  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...options,
      headers: { ...(options.headers ?? {}), Authorization: `Bearer ${token}` },
    })
  } catch (err) {
    // fetch rejects (rather than resolving with a status) when the request
    // never reached a server at all: the backend is not running, the machine
    // is offline, CORS blocked it. The browser's own message for this is
    // "Failed to fetch", in English, which tells the user nothing -- and it
    // cost a real debugging session once already.
    console.error("apiFetch network failure", path, err)
    throw new ApiError(
      "Không kết nối được máy chủ. Kiểm tra kết nối mạng rồi thử lại.",
      0,
    )
  }

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

/**
 * Like apiFetch but returns the raw Response so the caller can read a stream.
 * apiFetch always does res.json(), which consumes the body — useless for the
 * token-by-token chat reply. Same Bearer + Vietnamese network-error handling.
 */
export async function apiStream(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error("Chưa đăng nhập")

  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...options,
      headers: { ...(options.headers ?? {}), Authorization: `Bearer ${token}` },
    })
  } catch (err) {
    console.error("apiStream network failure", path, err)
    throw new ApiError(
      "Không kết nối được máy chủ. Kiểm tra kết nối mạng rồi thử lại.",
      0,
    )
  }

  if (!res.ok) {
    let detail = `Yêu cầu thất bại (${res.status})`
    try {
      const body = await res.json()
      if (typeof body?.detail === "string") detail = body.detail
    } catch {
      // Body was not JSON -- keep the fallback.
    }
    throw new ApiError(detail, res.status)
  }
  return res
}
