import { useEffect, useState } from "react"
import { Navigate, useSearchParams } from "react-router-dom"
import { supabase } from "@/lib/supabase"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function Login() {
  const [email, setEmail] = useState("")
  const [state, setState] = useState<"idle" | "sent" | "error">("idle")
  const [message, setMessage] = useState("")
  const [checking, setChecking] = useState(true)
  const [hasSession, setHasSession] = useState(false)
  const [searchParams] = useSearchParams()

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setHasSession(!!data.session)
      setChecking(false)
    })
  }, [])

  // Surface an error handed back by /auth/callback (e.g. an expired/used link).
  useEffect(() => {
    const err = searchParams.get("error")
    if (!err) return
    setState("error")
    setMessage(
      err === "invalid_code"
        ? "Link đăng nhập đã hết hạn hoặc đã được dùng. Xin link mới."
        : "Không đăng nhập được. Xin link mới.",
    )
  }, [searchParams])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    try {
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: {
          shouldCreateUser: false,
          emailRedirectTo: `${window.location.origin}/auth/callback`,
        },
      })
      if (error) {
        // Log the real error code to verify the mapping (spec §6) before trusting it.
        console.error("signInWithOtp", error.status, error.code, error.message)
        setState("error")
        if (error.status === 422 || error.code === "otp_disabled") {
          setMessage("Email này chưa được mời vào hệ thống.")
        } else if (error.status === 429) {
          setMessage("Bạn thử lại quá nhiều lần. Đợi một phút rồi thử lại.")
        } else {
          setMessage(`Không gửi được link đăng nhập. ${error.message}`)
        }
        return
      }
      setState("sent")
    } catch (err) {
      // signInWithOtp normally resolves with { error }, but a network-layer throw
      // must not leave the button in limbo with no feedback.
      console.error("signInWithOtp threw", err)
      setState("error")
      setMessage("Không gửi được link đăng nhập. Vui lòng thử lại.")
    }
  }

  if (checking) return null
  if (hasSession) return <Navigate to="/" replace />

  return (
    <div className="mx-auto max-w-sm p-8">
      <h1 className="mb-4 text-xl font-semibold">Đăng nhập</h1>
      {state === "sent" ? (
        <p>
          Đã gửi link đăng nhập tới <b>{email}</b>. Kiểm tra hộp thư.
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@example.com"
          />
          <Button type="submit" className="w-full">
            Gửi link đăng nhập
          </Button>
          {state === "error" && <p className="text-sm text-red-600">{message}</p>}
        </form>
      )}
    </div>
  )
}
