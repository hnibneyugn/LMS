"""Single place that reads and validates environment configuration.

Values are read lazily (inside functions, not at import time) so tests can
monkeypatch the environment and so importing the app never fails on a machine
with incomplete config.
"""

import os

MAX_FILE_BYTES = 20 * 1024 * 1024
PRESIGN_EXPIRY_SECONDS = 900
ALLOWED_FILE_TYPES = frozenset({"md", "docx", "pptx", "pdf"})
MAX_CHAPTER_CHARS = 8000


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def r2_endpoint() -> str:
    return f"https://{_required('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"


def r2_bucket() -> str:
    return _required("R2_BUCKET")


def r2_access_key_id() -> str:
    return _required("R2_ACCESS_KEY_ID")


def r2_secret_access_key() -> str:
    return _required("R2_SECRET_ACCESS_KEY")


def supabase_url() -> str:
    return _required("SUPABASE_URL")


def supabase_service_role_key() -> str:
    return _required("SUPABASE_SERVICE_ROLE_KEY")


def gemini_api_key() -> str:
    return _required("GEMINI_API_KEY")
