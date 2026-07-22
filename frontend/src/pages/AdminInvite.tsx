import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { errorMessage } from "@/lib/files"
import { getMe, listMembers, inviteMember, type Member } from "@/lib/admin"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function AdminInvite() {
  const navigate = useNavigate()
  const [checking, setChecking] = useState(true)
  const [members, setMembers] = useState<Member[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [email, setEmail] = useState("")
  const [sending, setSending] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  // Gate on is_admin; the backend enforces this independently, this is just UX.
  useEffect(() => {
    getMe()
      .then((me) => {
        if (!me.is_admin) {
          navigate("/", { replace: true })
          return
        }
        setChecking(false)
        listMembers()
          .then(setMembers)
          .catch((e) => setLoadError(errorMessage(e)))
      })
      .catch(() => navigate("/", { replace: true }))
  }, [navigate])

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault()
    if (sending) return
    setFormError(null)
    setOk(null)
    setSending(true)
    try {
      const member = await inviteMember(email.trim())
      setMembers((prev) => [member, ...(prev ?? []).filter((m) => m.email !== member.email)])
      setOk(`Đã mời ${member.email}.`)
      setEmail("")
    } catch (err) {
      setFormError(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  if (checking) return <p className="p-8 text-sm text-gray-500">Đang tải…</p>

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Mời thành viên</h1>
        <Button variant="outline" onClick={() => navigate("/")}>
          Về bảng điều khiển
        </Button>
      </header>

      <form onSubmit={handleInvite} className="flex gap-2">
        <Input
          type="email"
          placeholder="email@thanhvien.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          disabled={sending}
        />
        <Button type="submit" disabled={sending || !email.trim()}>
          {sending ? "Đang mời…" : "Mời"}
        </Button>
      </form>
      {ok && <p className="text-sm text-green-600">{ok}</p>}
      {formError && <p className="text-sm text-red-600">{formError}</p>}

      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-700">Thành viên hiện có</h2>
        {loadError ? (
          <p className="text-sm text-red-600">Không tải được danh sách: {loadError}</p>
        ) : !members ? (
          <p className="text-sm text-gray-500">Đang tải…</p>
        ) : members.length === 0 ? (
          <p className="text-sm text-gray-500">Chưa có thành viên nào.</p>
        ) : (
          <ul className="divide-y text-sm">
            {members.map((m) => (
              <li key={m.email} className="flex items-center justify-between py-2">
                <span>{m.email}</span>
                <span className={m.password_set ? "text-green-600" : "text-gray-400"}>
                  {m.password_set ? "Đã đặt mật khẩu" : "Chưa đặt mật khẩu"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
