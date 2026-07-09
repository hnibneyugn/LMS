import 'server-only';
import { createClient } from '@supabase/supabase-js';
import type { Database } from '@/server/types/database.types';

/**
 * Service-role Supabase client. Bypasses Row Level Security, so it is SERVER-ONLY and
 * must never be imported into a Client Component. Used by trusted server code such as the
 * GitHub sync webhook (/api/sync) to write shared content (lessons, questions).
 *
 * The `server-only` import above makes the build fail if this file is pulled into a client bundle.
 */
export function createAdminClient() {
  return createClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
      },
    },
  );
}
