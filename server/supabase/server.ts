import { createServerClient } from '@supabase/ssr';
import { cookies } from 'next/headers';
import type { Database } from '@/server/types/database.types';

/**
 * Supabase client for use in Server Components, Route Handlers, and Server Actions.
 * Uses the anon key (RLS-constrained) but reads the caller's session from cookies.
 *
 * Next.js 15+ `cookies()` is async, so this helper is async — await it at call sites.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Called from a Server Component where cookies are read-only.
            // Safe to ignore when middleware is responsible for refreshing sessions.
          }
        },
      },
    },
  );
}
