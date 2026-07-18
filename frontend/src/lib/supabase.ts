import { createClient } from "@supabase/supabase-js"

const url = import.meta.env.VITE_SUPABASE_URL as string
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string

if (!url || !anonKey) {
  throw new Error("Thiếu VITE_SUPABASE_URL hoặc VITE_SUPABASE_ANON_KEY")
}

// detectSessionInUrl (default true) handles the magic-link callback; persistSession keeps the session across reloads.
export const supabase = createClient(url, anonKey)
