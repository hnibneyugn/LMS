"""Socratic chat module against a fake Gemini stream client (no network)."""

import pytest

from app.ai import chat as chat_module
from app.ai.chat import ChatError, _build_system_prompt, stream_socratic_reply


class _Chunk:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, chunks=None, raise_exc=None):
        self._chunks = chunks or []
        self._raise = raise_exc
        self.calls = 0
        self.last_kwargs = None

    def generate_content_stream(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self._raise is not None:
            raise self._raise
        for c in self._chunks:
            yield _Chunk(c)


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _patch(monkeypatch, models):
    monkeypatch.setattr(chat_module, "get_client", lambda: _FakeClient(models))


def test_system_prompt_embeds_content_and_forbids_direct_answers():
    prompt = _build_system_prompt("NỘI DUNG BÀI ABC")
    assert "NỘI DUNG BÀI ABC" in prompt
    # Socratic: must instruct not to give the answer directly.
    assert "không" in prompt.lower() and "đáp án" in prompt.lower()


def test_stream_yields_each_chunk(monkeypatch):
    models = _FakeModels(chunks=["Bạn nghĩ ", "sao về X?"])
    _patch(monkeypatch, models)

    out = list(stream_socratic_reply("nội dung", [], "câu hỏi"))

    assert out == ["Bạn nghĩ ", "sao về X?"]
    assert models.calls == 1


def test_stream_maps_history_roles_to_gemini_contents(monkeypatch):
    models = _FakeModels(chunks=["ok"])
    _patch(monkeypatch, models)

    history = [
        {"role": "user", "content": "trước"},
        {"role": "assistant", "content": "đáp trước"},
    ]
    list(stream_socratic_reply("nd", history, "mới"))

    contents = models.last_kwargs["contents"]
    roles = [c["role"] for c in contents]
    # assistant -> "model"; the new user message is appended last as "user".
    assert roles == ["user", "model", "user"]
    assert contents[-1]["parts"][0]["text"] == "mới"


def test_stream_raises_chaterror_when_api_fails(monkeypatch):
    _patch(monkeypatch, _FakeModels(raise_exc=RuntimeError("quota")))

    with pytest.raises(ChatError):
        list(stream_socratic_reply("nd", [], "câu hỏi"))


def test_stream_rejects_empty_message(monkeypatch):
    models = _FakeModels(chunks=["x"])
    _patch(monkeypatch, models)

    with pytest.raises(ChatError):
        list(stream_socratic_reply("nd", [], "   "))
    assert models.calls == 0
