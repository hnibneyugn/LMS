"""AI question generation: client wiring + generator logic (no real network)."""

import pytest

from app.ai import client as client_module


def test_get_client_uses_the_configured_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    captured = {}

    class FakeGenaiClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key

    monkeypatch.setattr(client_module.genai, "Client", FakeGenaiClient)
    client_module.get_client.cache_clear()

    client_module.get_client()

    assert captured["api_key"] == "test-key"
    client_module.get_client.cache_clear()


def test_chat_model_is_pinned():
    assert client_module.CHAT_MODEL == "gemini-2.5-flash"
