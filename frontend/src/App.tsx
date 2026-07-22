import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Login } from "@/pages/Login"
import { AuthCallback } from "@/pages/AuthCallback"
import { Dashboard } from "@/pages/Dashboard"
import { Files } from "@/pages/Files"
import { Lessons } from "@/pages/Lessons"
import { LessonDetailPage } from "@/pages/LessonDetail"
import { ReviewChapters } from "@/pages/ReviewChapters"
import { Account } from "@/pages/Account"
import { AdminInvite } from "@/pages/AdminInvite"
import { ProtectedRoute } from "@/components/ProtectedRoute"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route
          path="/files"
          element={
            <ProtectedRoute>
              <Files />
            </ProtectedRoute>
          }
        />
        <Route
          path="/files/:fileId/review"
          element={
            <ProtectedRoute>
              <ReviewChapters />
            </ProtectedRoute>
          }
        />
        <Route
          path="/lessons"
          element={
            <ProtectedRoute>
              <Lessons />
            </ProtectedRoute>
          }
        />
        <Route
          path="/lessons/:slug"
          element={
            <ProtectedRoute>
              <LessonDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/account"
          element={
            <ProtectedRoute>
              <Account />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/invite"
          element={
            <ProtectedRoute>
              <AdminInvite />
            </ProtectedRoute>
          }
        />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
