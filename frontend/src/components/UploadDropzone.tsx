import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  ACCEPTED_EXTENSIONS,
  errorMessage,
  uploadFile,
  type UploadStep,
} from "@/lib/files"

const STEP_LABEL: Record<UploadStep, string> = {
  presigning: "Đang chuẩn bị tải lên…",
  uploading: "Đang tải file lên…",
  processing: "Đang bắt đầu xử lý…",
}

export function UploadDropzone({ onUploaded }: { onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [step, setStep] = useState<UploadStep | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  async function handleFile(file: File) {
    setError(null)
    try {
      await uploadFile(file, setStep)
      onUploaded()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setStep(null)
      // Clear the input so picking the same file again still fires onChange.
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        const file = e.dataTransfer.files[0]
        if (file) void handleFile(file)
      }}
      className={`rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
        dragging ? "border-primary bg-primary/5" : "border-gray-300"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS.join(",")}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) void handleFile(file)
        }}
      />
      {step ? (
        <p className="text-sm text-gray-600">{STEP_LABEL[step]}</p>
      ) : (
        <>
          <p className="mb-3 text-sm text-gray-600">
            Kéo thả tài liệu vào đây, hoặc
          </p>
          <Button onClick={() => inputRef.current?.click()}>Chọn file</Button>
          <p className="mt-3 text-xs text-gray-500">
            Nhận .md, .docx, .pptx, .pdf — tối đa 20MB
          </p>
        </>
      )}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
  )
}
