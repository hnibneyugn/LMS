import { useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { errorMessage } from "@/lib/files"
import {
  clearChat,
  getChatHistory,
  streamChat,
  type ChatMessage,
} from "@/lib/chat"

/**
 * Socratic chat for one lesson (#5). A panel that slides in from the right over
 * the lesson page. Loads the saved conversation on first open; each send streams
 * the reply token-by-token. Never blocks reading -- close returns to the lesson.
 */
export function ChatPanel({
  lessonId,
  open,
  onClose,
}: {
  lessonId: string
  open: boolean
  onClose: () => void
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Load the saved conversation the first time the panel opens.
  useEffect(() => {
    if (!open || loaded) return
    let cancelled = false
    getChatHistory(lessonId)
      .then((history) => {
        if (!cancelled) setMessages(history)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [open, loaded, lessonId])

  // Lesson changed (prev/next nav without closing the panel): drop the old
  // conversation so the new lesson's history loads fresh on next open.
  useEffect(() => {
    setMessages([])
    setLoaded(false)
    setError(null)
  }, [lessonId])

  // Keep the newest message in view as it streams.
  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight)
  }, [messages])

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setInput("")
    setError(null)
    setSending(true)
    // Show the user turn + an empty assistant turn that the stream fills in.
    setMessages((m) => [
      ...m,
      { role: "user", content: text },
      { role: "assistant", content: "" },
    ])
    try {
      await streamChat(lessonId, text, (chunk) => {
        setMessages((m) => {
          const next = [...m]
          const last = next[next.length - 1]
          next[next.length - 1] = { ...last, content: last.content + chunk }
          return next
        })
      })
    } catch (err) {
      // Drop the empty assistant turn and surface the Vietnamese error.
      setMessages((m) => {
        const next = [...m]
        if (next.length && next[next.length - 1].role === "assistant" && !next[next.length - 1].content) {
          next.pop()
        }
        return next
      })
      setError(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  async function reset() {
    if (sending) return
    if (!window.confirm("Xóa toàn bộ hội thoại của bài này?")) return
    setError(null)
    try {
      await clearChat(lessonId)
      setMessages([])
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <>
      {/* Backdrop: click to close. */}
      <div
        className={`fixed inset-0 z-40 bg-black/20 transition-opacity ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
      />
      <aside
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l bg-white shadow-xl transition-transform ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
        aria-hidden={!open}
      >
        <header className="flex items-center justify-between border-b p-4">
          <h2 className="text-sm font-semibold">Hỏi đáp Socratic</h2>
          <div className="flex items-center gap-3 text-sm">
            <button type="button" onClick={() => void reset()} className="text-gray-500 underline">
              Xóa hội thoại
            </button>
            <button type="button" onClick={onClose} aria-label="Đóng" className="text-gray-500">
              ✕
            </button>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 && (
            <p className="text-sm text-gray-500">
              Hỏi về nội dung bài; trợ giảng sẽ gợi mở bằng câu hỏi thay vì đưa đáp án.
            </p>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
            >
              <div
                className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                  m.role === "user" ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-800"
                }`}
              >
                {m.role === "assistant" ? (
                  <div className="prose prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {m.content || "…"}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <span className="whitespace-pre-wrap">{m.content}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {error && <p className="px-4 pb-2 text-sm text-red-600">{error}</p>}

        <div className="flex gap-2 border-t p-4">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            disabled={sending}
            rows={2}
            maxLength={4000}
            className="flex-1 resize-none rounded-md border p-2 text-sm"
            placeholder="Nhập câu hỏi… (Enter để gửi)"
          />
          <button
            type="button"
            onClick={() => void send()}
            disabled={sending || !input.trim()}
            className="self-end rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
          >
            {sending ? "…" : "Gửi"}
          </button>
        </div>
      </aside>
    </>
  )
}
