import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { supabase } from "@/lib/supabase"
import { apiFetch } from "@/lib/api"
import { Button } from "@/components/ui/button"

export function Home() {
  const navigate = useNavigate()
  const [email, setEmail] = useState<string | null>(null)
  const [apiResult, setApiResult] = useState("")

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setEmail(data.user?.email ?? null))
  }, [])

  async function handleSignOut() {
    await supabase.auth.signOut()
    navigate("/login", { replace: true })
  }

  async function pingApi() {
    try {
      const data = await apiFetch("/api/me")
      setApiResult(JSON.stringify(data))
    } catch (e) {
      setApiResult(`Lỗi: ${(e as Error).message}`)
    }
  }

  return (
    <div className="space-y-4 p-8">
      <h1 className="text-xl font-semibold">Personal LMS</h1>
      <p>
        Đăng nhập với: <b>{email}</b>
      </p>
      <div className="flex gap-2">
        <Button onClick={pingApi}>Gọi /api/me</Button>
        <Button variant="outline" onClick={handleSignOut}>
          Đăng xuất
        </Button>
      </div>
      {apiResult && <pre className="rounded bg-gray-100 p-2 text-sm">{apiResult}</pre>}
    </div>
  )
}
