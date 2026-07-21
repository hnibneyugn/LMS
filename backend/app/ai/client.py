"""Google Gemini client, shared by every AI feature (question gen, grading, chat).

One lazily-built, cached client so the whole backend talks to Gemini the same
way. The model is pinned here so a change is one edit, not a scatter of literals.
"""

import functools

import google.genai as genai

from app.config import settings

CHAT_MODEL = "gemini-3.1-flash-lite"


@functools.lru_cache(maxsize=1)
def get_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key())
