"""Supabase client using the SERVICE ROLE key — it bypasses RLS.

Every query issued through this client MUST filter by user_id explicitly;
the database will not do it for us here. The key never leaves the backend.
"""

import functools

from supabase import Client, create_client

from app.config import settings


@functools.lru_cache(maxsize=1)
def admin() -> Client:
    return create_client(
        settings.supabase_url(), settings.supabase_service_role_key()
    )
