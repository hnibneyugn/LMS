import { apiFetch, apiStream } from "@/lib/api"

export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

/** Saved conversation for one lesson (empty array if none yet). */
export async function getChatHistory(lessonId: string): Promise<ChatMessage[]> {
  const data = await apiFetch(`/api/chat/${encodeURIComponent(lessonId)}`)
  return (data?.messages ?? []) as ChatMessage[]
}

/** Reset the conversation (server keeps the row, empties messages). */
export async function clearChat(lessonId: string): Promise<void> {
  await apiFetch(`/api/chat/${encodeURIComponent(lessonId)}`, { method: "DELETE" })
}

/**
 * Send a message and stream the Socratic reply. `onChunk` fires for each decoded
 * piece of text as it arrives; resolve when the stream ends.
 */
export async function streamChat(
  lessonId: string,
  message: string,
  onChunk: (text: string) => void,
): Promise<void> {
  const res = await apiStream(`/api/chat/${encodeURIComponent(lessonId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  })

  const reader = res.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    const text = decoder.decode(value, { stream: true })
    if (text) onChunk(text)
  }
  const tail = decoder.decode()
  if (tail) onChunk(tail)
}
