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
  const [newPassword, setNewPassword] = useState("")
  const [newPassword2, setNewPassword2] = useState("")
  const [state, setState] = useState<"idle" | "error" | "notice">("idle")
  // Separate from `state` on purpose: a wrong code must set an error WITHOUT
  // collapsing the code form the user is standing in.
  const [linkSent, setLinkSent] = useState(false)
  // Why the code was requested. "reset" always ends at the set-password
  // screen; "login" only stops there for a member who has no password yet.
  const [otpPurpose, setOtpPurpose] = useState<"login" | "reset">("login")
  // Set once the code checks out and a password is still owed.
  const [mustSetPassword, setMustSetPassword] = useState(false)
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

  async function handleMagicLink(purpose: "login" | "reset" = "login") {
    setState("idle")
    setOtpPurpose(purpose)
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
      const { data, error } = await supabase.auth.verifyOtp({
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
      // The code was right, so there is a session now either way. Whether the
      // member gets to use it yet depends on why they asked for the code.
      const passwordSet = data.user?.user_metadata?.password_set === true
      if (otpPurpose === "reset" || !passwordSet) {
        setMustSetPassword(true)
        setLinkSent(false)
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

  async function handleSetPassword(e: React.FormEvent) {
    e.preventDefault()
    setState("idle")
    if (newPassword !== newPassword2) {
      setState("error")
      setMessage("Hai lần nhập mật khẩu không khớp.")
      return
    }
    if (newPassword.length < 8) {
      setState("error")
      setMessage("Mật khẩu phải dài ít nhất 8 ký tự.")
      return
    }
    setBusy(true)
    try {
      // Runs against the session the code just created, so the member sets
      // their own password and nobody else ever sees it. `password_set` is
      // what stops the login page asking again next time.
      const { error } = await supabase.auth.updateUser({
        password: newPassword,
        data: { password_set: true },
      })
      if (error) {
        console.error("updateUser", error.status, error.code, error.message)
        setState("error")
        setMessage(
          error.code === "same_password"
            ? "Mật khẩu mới phải khác mật khẩu cũ."
            : `Không đặt được mật khẩu. ${error.message}`,
        )
        return
      }
      // Deliberately do NOT enter the app on the OTP-created session. Drop it
      // and send the member back to the password form so they sign in once
      // with the password they just chose -- it proves the password works and
      // that they remember it before they get in. Email stays filled in.
      const wasReset = otpPurpose === "reset"
      await supabase.auth.signOut()
      setHasSession(false)
      setMustSetPassword(false)
      setLinkSent(false)
      setCode("")
      setPassword("")
      setNewPassword("")
      setNewPassword2("")
      setOtpPurpose("login")
      setState("notice")
      setMessage(
        wasReset
          ? "Đã đổi mật khẩu. Đăng nhập lại bằng mật khẩu mới."
          : "Đã đặt mật khẩu. Đăng nhập bằng mật khẩu vừa tạo để vào.",
      )
    } catch (err) {
      console.error("updateUser threw", err)
      setState("error")
      setMessage("Không đặt được mật khẩu. Vui lòng thử lại.")
    } finally {
      setBusy(false)
    }
  }

  if (checking) return null
  // Guard on mustSetPassword too: verifyOtp creates a session, which trips the
  // onAuthStateChange listener above and flips hasSession true. Without this
  // guard that redirect would fire before the forced set-password screen ever
  // renders, letting a just-invited member (or a password reset) slip into the
  // app without actually setting a password.
  if (hasSession && !mustSetPassword) return <Navigate to="/" replace />

  return (
    <div className="mx-auto max-w-sm p-8">
      <h1 className="mb-4 text-xl font-semibold">Đăng nhập</h1>
      {mustSetPassword ? (
        <form onSubmit={handleSetPassword} className="space-y-3">
          <p className="text-sm">
            {otpPurpose === "reset"
              ? "Đặt mật khẩu mới cho tài khoản của bạn."
              : "Tài khoản chưa có mật khẩu. Đặt một mật khẩu để lần sau đăng nhập thẳng, không cần mở mail."}
          </p>
          <Input
            type="password"
            required
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="Mật khẩu mới (ít nhất 8 ký tự)"
          />
          <Input
            type="password"
            required
            autoComplete="new-password"
            value={newPassword2}
            onChange={(e) => setNewPassword2(e.target.value)}
            placeholder="Nhập lại mật khẩu"
          />
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Đang lưu…" : "Lưu mật khẩu"}
          </Button>
          {state === "error" && <p className="text-sm text-red-600">{message}</p>}
        </form>
      ) : linkSent ? (
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
              // Keep the original purpose: resending during a password reset
              // must not silently turn into a plain login.
              onClick={() => handleMagicLink(otpPurpose)}
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
          {state === "notice" && <p className="text-sm text-green-700">{message}</p>}
          <div className="space-y-2 pt-3 text-sm">
            <div className="rounded-md border border-border p-3">
              <p className="mb-2 text-muted-foreground">
                Lần đầu đăng nhập, chưa có mật khẩu? Nhận mã qua email rồi đặt mật khẩu.
              </p>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                // The way in for a member who was just invited and has no
                // password at all -- they cannot use the form above yet.
                onClick={() => handleMagicLink("login")}
                disabled={busy || !email}
              >
                Gửi mã qua email
              </Button>
            </div>
            <button
              type="button"
              onClick={() => handleMagicLink("reset")}
              disabled={busy || !email}
              className="block w-full text-center text-muted-foreground underline disabled:opacity-50"
            >
              Quên mật khẩu? Đặt lại bằng mã qua email
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
