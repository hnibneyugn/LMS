import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Login } from "@/pages/Login"
import { AuthCallback } from "@/pages/AuthCallback"
import { Home } from "@/pages/Home"
import { ProtectedRoute } from "@/components/ProtectedRoute"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Home />
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
