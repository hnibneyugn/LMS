import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { supabase } from "@/lib/supabase"

export function AuthCallback() {
  const navigate = useNavigate()

  useEffect(() => {
    // supabase-js (detectSessionInUrl) exchanges the URL token for a session on load.
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
      if (session) navigate("/", { replace: true })
    })
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) navigate("/", { replace: true })
    })
    // No session after a few seconds => the link is broken/expired.
    const timer = setTimeout(() => {
      supabase.auth.getSession().then(({ data }) => {
        if (!data.session) navigate("/login?error=invalid_code", { replace: true })
      })
    }, 3000)

    return () => {
      sub.subscription.unsubscribe()
      clearTimeout(timer)
    }
  }, [navigate])

  return <div className="p-8">Đang đăng nhập…</div>
}
