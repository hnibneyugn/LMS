import { useCallback, useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { FileTable } from "@/components/FileTable"
import { UploadDropzone } from "@/components/UploadDropzone"
import { errorMessage, listFiles, processFile, type UserFile } from "@/lib/files"

const POLL_INTERVAL_MS = 3000

export function Files() {
  const [files, setFiles] = useState<UserFile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      setFiles(await listFiles())
      setError(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Poll only while something is actually running, and never while the tab is
  // hidden -- a forgotten tab must not keep hitting the API forever.
  //
  // Depending on the derived boolean (not `files` itself) is deliberate: every
  // poll tick replaces `files` with a new array reference, so depending on
  // `files` would tear down and rebuild the listener + interval on every
  // single tick. That doesn't tight-loop or leak (the effect's cleanup always
  // clears the previous interval before a new one is armed, and setInterval's
  // own 3s cadence is what paces `refresh`, not the effect re-running), but
  // it does churn work for no reason. `anyProcessing` only flips when a file
  // actually starts or stops processing, so the effect re-runs -- and the
  // listener gets re-attached -- only on those real transitions.
  const anyProcessing = files.some((f) => f.processing_status === "processing")

  useEffect(() => {
    function stop() {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current)
        timerRef.current = null
      }
    }

    function sync() {
      if (anyProcessing && document.visibilityState === "visible") {
        if (timerRef.current === null) {
          timerRef.current = window.setInterval(() => void refresh(), POLL_INTERVAL_MS)
        }
      } else {
        stop()
      }
    }

    sync()
    document.addEventListener("visibilitychange", sync)
    return () => {
      document.removeEventListener("visibilitychange", sync)
      stop()
    }
  }, [anyProcessing, refresh])

  async function handleProcess(fileId: string) {
    setBusyId(fileId)
    setError(null)
    try {
      await processFile(fileId)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusyId(null)
      // Refetch either way: on success to pick up `processing`, on failure to
      // resync with whatever state the backend actually holds.
      await refresh()
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Tài liệu của tôi</h1>
        <Link to="/" className="text-sm text-gray-500 underline">
          Trang chủ
        </Link>
      </div>

      <UploadDropzone onUploaded={refresh} />

      {error && <p className="text-sm text-red-600">{error}</p>}

      {loading ? (
        <p className="py-8 text-center text-sm text-gray-500">Đang tải…</p>
      ) : (
        <FileTable files={files} onProcess={handleProcess} busyId={busyId} />
      )}
    </div>
  )
}
