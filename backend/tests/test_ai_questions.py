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
    assert client_module.CHAT_MODEL == "gemini-3.5-flash"


from app.ai import questions as questions_module
from app.ai.questions import (
    GeneratedQuestion,
    QuestionGenerationError,
    generate_questions,
)


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise = raise_exc
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return self._response


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _patch_client(monkeypatch, models):
    monkeypatch.setattr(questions_module, "get_client", lambda: _FakeClient(models))


def test_generate_returns_validated_questions(monkeypatch):
    payload = (
        '[{"type": "recall", "question_text": "Câu 1?"},'
        ' {"type": "scenario", "question_text": "Câu 2?"}]'
    )
    _patch_client(monkeypatch, _FakeModels(_FakeResponse(payload)))

    result = generate_questions("nội dung bài học")

    assert result == [
        GeneratedQuestion(type="recall", question_text="Câu 1?"),
        GeneratedQuestion(type="scenario", question_text="Câu 2?"),
    ]


def test_generate_drops_items_with_unknown_type(monkeypatch):
    payload = (
        '[{"type": "recall", "question_text": "Giữ lại?"},'
        ' {"type": "bogus", "question_text": "Bỏ đi?"},'
        ' {"type": "explain", "question_text": "   "}]'
    )
    _patch_client(monkeypatch, _FakeModels(_FakeResponse(payload)))

    result = generate_questions("nội dung")

    # Unknown type dropped; blank text dropped; only the valid one survives.
    assert result == [GeneratedQuestion(type="recall", question_text="Giữ lại?")]


def test_generate_raises_when_nothing_valid_survives(monkeypatch):
    payload = '[{"type": "bogus", "question_text": "x"}]'
    _patch_client(monkeypatch, _FakeModels(_FakeResponse(payload)))

    with pytest.raises(QuestionGenerationError):
        generate_questions("nội dung")


def test_generate_raises_on_malformed_json(monkeypatch):
    _patch_client(monkeypatch, _FakeModels(_FakeResponse("not json")))

    with pytest.raises(QuestionGenerationError):
        generate_questions("nội dung")


def test_generate_raises_when_the_api_call_fails(monkeypatch):
    _patch_client(monkeypatch, _FakeModels(raise_exc=RuntimeError("quota")))

    with pytest.raises(QuestionGenerationError):
        generate_questions("nội dung")


def test_generate_rejects_empty_content_without_calling_the_model(monkeypatch):
    models = _FakeModels(_FakeResponse("[]"))
    _patch_client(monkeypatch, models)

    with pytest.raises(QuestionGenerationError):
        generate_questions("   ")

    assert models.calls == 0
