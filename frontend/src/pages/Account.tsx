import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { supabase } from "@/lib/supabase"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function Account() {
  const [email, setEmail] = useState("")
  // A member who arrived through an emailed code and has not chosen a password
  // yet has no current password to type, so the form asks for one only when
  // there is genuinely something to check against.
  const [hasPassword, setHasPassword] = useState(true)
  const [loading, setLoading] = useState(true)
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [next2, setNext2] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [done, setDone] = useState(false)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? "")
      setHasPassword(data.user?.user_metadata?.password_set === true)
      setLoading(false)
    })
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setDone(false)

    if (next !== next2) {
      setError("Hai lần nhập mật khẩu mới không khớp.")
      return
    }
    if (next.length < 8) {
      setError("Mật khẩu phải dài ít nhất 8 ký tự.")
      return
    }

    setBusy(true)
    try {
      if (hasPassword) {
        // Re-authenticate before changing anything. Supabase does not require
        // it, but a session left open on a shared machine should not be enough
        // to take the account over -- whoever changes the password has to
        // prove they know the current one.
        const { error: reauth } = await supabase.auth.signInWithPassword({
          email,
          password: current,
        })
        if (reauth) {
          setError("Mật khẩu hiện tại không đúng.")
          return
        }
      }

      const { error: updateError } = await supabase.auth.updateUser({
        password: next,
        data: { password_set: true },
      })
      if (updateError) {
        console.error("updateUser", updateError.status, updateError.code, updateError.message)
        setError(
          updateError.code === "same_password"
            ? "Mật khẩu mới phải khác mật khẩu cũ."
            : `Không đổi được mật khẩu. ${updateError.message}`,
        )
        return
      }

      setDone(true)
      setCurrent("")
      setNext("")
      setNext2("")
      setHasPassword(true)
    } catch (err) {
      console.error("change password threw", err)
      setError("Không đổi được mật khẩu. Vui lòng thử lại.")
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <p className="p-8 text-sm text-gray-500">Đang tải…</p>

  return (
    <div className="mx-auto max-w-sm space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Tài khoản</h1>
        <Link to="/" className="text-sm text-gray-500 underline">
          Trang chủ
        </Link>
      </div>

      <p className="text-sm text-gray-600">
        Đang đăng nhập với <b>{email}</b>
      </p>

      <form onSubmit={handleSubmit} className="space-y-3">
        <h2 className="font-medium">
          {hasPassword ? "Đổi mật khẩu" : "Đặt mật khẩu"}
        </h2>
        {!hasPassword && (
          <p className="text-sm text-gray-600">
            Tài khoản chưa có mật khẩu. Đặt một mật khẩu để lần sau đăng nhập thẳng, không cần
            mở mail.
          </p>
        )}
        {hasPassword && (
          <Input
            type="password"
            required
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder="Mật khẩu hiện tại"
          />
        )}
        <Input
          type="password"
          required
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          placeholder="Mật khẩu mới (ít nhất 8 ký tự)"
        />
        <Input
          type="password"
          required
          autoComplete="new-password"
          value={next2}
          onChange={(e) => setNext2(e.target.value)}
          placeholder="Nhập lại mật khẩu mới"
        />
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Đang lưu…" : hasPassword ? "Đổi mật khẩu" : "Lưu mật khẩu"}
        </Button>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {done && <p className="text-sm text-green-700">Đã đổi mật khẩu.</p>}
      </form>
    </div>
  )
}
