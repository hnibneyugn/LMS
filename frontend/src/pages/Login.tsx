import { useEffect, useState } from "react"
import { Navigate, useSearchParams } from "react-router-dom"
import { supabase } from "@/lib/supabase"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function Login() {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const [state, setState] = useState<"idle" | "error">("idle")
  // Separate from `state` on purpose: a wrong code must set an error WITHOUT
  // collapsing the code form the user is standing in.
  const [linkSent, setLinkSent] = useState(false)
  const [message, setMessage] = useState("")
  const [checking, setChecking] = useState(true)
  const [hasSession, setHasSession] = useState(false)
  const [searchParams] = useSearchParams()

  useEffect(() => {
    // The listener covers the case where the magic link is opened in ANOTHER
    // TAB of this same browser: supabase-js writes the session to storage and
    // notifies every tab, so this one redirects itself instead of sitting on
    // a stale form the user has to reload by hand. It does nothing for a link
    // opened on a different device -- that session lives on the phone, and
    // nothing can travel back here. The OTP code below is what covers that.
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
      if (session) setHasSession(true)
    })
    supabase.auth.getSession().then(({ data }) => {
      setHasSession(!!data.session)
      setChecking(false)
    })
    return () => sub.subscription.unsubscribe()
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

  async function handlePasswordLogin(e: React.FormEvent) {
    e.preventDefault()
    setState("idle")
    setBusy(true)
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) {
        setState("error")
        // Supabase deliberately returns the same "Invalid login credentials"
        // for a wrong password and an unknown email, so it cannot be used to
        // discover who is a member. Keep the message equally vague.
        setMessage(
          error.status === 429
            ? "Bạn thử lại quá nhiều lần. Đợi một phút rồi thử lại."
            : "Email hoặc mật khẩu không đúng.",
        )
        return
      }
      // ProtectedRoute picks the session up; the redirect below handles the rest.
      setHasSession(true)
    } catch (err) {
      console.error("signInWithPassword threw", err)
      setState("error")
      setMessage("Không đăng nhập được. Vui lòng thử lại.")
    } finally {
      setBusy(false)
    }
  }

  async function handleMagicLink() {
    setState("idle")
    setBusy(true)
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
      setLinkSent(true)
    } catch (err) {
      // signInWithOtp normally resolves with { error }, but a network-layer throw
      // must not leave the button in limbo with no feedback.
      console.error("signInWithOtp threw", err)
      setState("error")
      setMessage("Không gửi được link đăng nhập. Vui lòng thử lại.")
    } finally {
      setBusy(false)
    }
  }

  async function handleVerifyCode(e: React.FormEvent) {
    e.preventDefault()
    setState("idle")
    setBusy(true)
    try {
      // Typing the code signs THIS device in, which is the whole point: the
      // member reads it off their phone without the session being stranded
      // there. `type: "email"` is the OTP that accompanies a magic link.
      const { error } = await supabase.auth.verifyOtp({
        email,
        token: code.trim(),
        type: "email",
      })
      if (error) {
        console.error("verifyOtp", error.status, error.code, error.message)
        setState("error")
        setMessage(
          error.status === 429
            ? "Bạn thử lại quá nhiều lần. Đợi một phút rồi thử lại."
            : "Mã không đúng hoặc đã hết hạn. Xin mã mới.",
        )
        return
      }
      setHasSession(true)
    } catch (err) {
      console.error("verifyOtp threw", err)
      setState("error")
      setMessage("Không xác nhận được mã. Vui lòng thử lại.")
    } finally {
      setBusy(false)
    }
  }

  if (checking) return null
  if (hasSession) return <Navigate to="/" replace />

  return (
    <div className="mx-auto max-w-sm p-8">
      <h1 className="mb-4 text-xl font-semibold">Đăng nhập</h1>
      {linkSent ? (
        <form onSubmit={handleVerifyCode} className="space-y-3">
          <p className="text-sm">
            Đã gửi mã đăng nhập tới <b>{email}</b>. Mở hộp thư và nhập mã vào đây.
          </p>
          <p className="text-sm text-gray-600">
            Mở mail trên điện thoại cũng được — nhập mã vào máy này là đăng nhập ngay tại đây.
            Hoặc bấm thẳng link trong mail nếu bạn mở nó trên chính máy này.
          </p>
          <Input
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            // Phone keyboards open to digits, and browsers offer the code from
            // the SMS/email autofill hint instead of a saved password.
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="Mã trong email"
          />
          <Button type="submit" className="w-full" disabled={busy || !code.trim()}>
            {busy ? "Đang xác nhận…" : "Xác nhận"}
          </Button>
          {state === "error" && <p className="text-sm text-red-600">{message}</p>}
          <div className="flex justify-between pt-2 text-sm">
            <button
              type="button"
              onClick={handleMagicLink}
              disabled={busy}
              className="text-gray-600 underline disabled:opacity-50"
            >
              Gửi lại mã
            </button>
            <button
              type="button"
              onClick={() => {
                setLinkSent(false)
                setCode("")
                setState("idle")
              }}
              className="text-gray-600 underline"
            >
              Quay lại
            </button>
          </div>
        </form>
      ) : (
        <form onSubmit={handlePasswordLogin} className="space-y-3">
          <Input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@example.com"
          />
          <Input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Mật khẩu"
          />
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Đang đăng nhập…" : "Đăng nhập"}
          </Button>
          {state === "error" && <p className="text-sm text-red-600">{message}</p>}
          <div className="pt-2 text-center">
            <button
              type="button"
              // Kept as the fallback for a forgotten password, and as the only
              // way in for a member who has not had one set yet.
              onClick={handleMagicLink}
              disabled={busy || !email}
              className="text-sm text-gray-600 underline disabled:opacity-50"
            >
              Quên mật khẩu? Gửi link đăng nhập
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
