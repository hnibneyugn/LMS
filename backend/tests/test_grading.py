"""AI grading: grade_answer logic against a fake Gemini client (no network)."""

import pytest

from app.ai import grading as grading_module
from app.ai.grading import GradeResult, GradingError, grade_answer


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


def _patch(monkeypatch, models):
    monkeypatch.setattr(grading_module, "get_client", lambda: _FakeClient(models))


def test_grade_returns_validated_result(monkeypatch):
    payload = '{"score": 7.5, "missing_points": ["Thiếu ví dụ"], "comment": "Khá tốt."}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    result = grade_answer("nội dung", "Câu hỏi?", "recall", "câu trả lời")

    assert result == GradeResult(
        score=7.5, missing_points=["Thiếu ví dụ"], comment="Khá tốt."
    )


def test_grade_clamps_score_into_range(monkeypatch):
    payload = '{"score": 42, "missing_points": [], "comment": "ok"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    assert grade_answer("nd", "q", "recall", "a").score == 10.0

    payload2 = '{"score": -3, "missing_points": [], "comment": "ok"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload2)))

    assert grade_answer("nd", "q", "recall", "a").score == 0.0


def test_grade_drops_blank_missing_points(monkeypatch):
    payload = '{"score": 5, "missing_points": ["Ý A", "  ", ""], "comment": "c"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    assert grade_answer("nd", "q", "recall", "a").missing_points == ["Ý A"]


def test_grade_raises_when_score_is_not_a_number(monkeypatch):
    payload = '{"score": "bảy", "missing_points": [], "comment": "c"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "a")


def test_grade_raises_when_missing_points_is_not_a_list(monkeypatch):
    payload = '{"score": 5, "missing_points": "Ý A", "comment": "c"}'
    _patch(monkeypatch, _FakeModels(_FakeResponse(payload)))

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "a")


def test_grade_raises_on_malformed_json(monkeypatch):
    _patch(monkeypatch, _FakeModels(_FakeResponse("not json")))

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "a")


def test_grade_raises_when_api_call_fails(monkeypatch):
    _patch(monkeypatch, _FakeModels(raise_exc=RuntimeError("quota")))

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "a")


def test_grade_rejects_empty_answer_without_calling_the_model(monkeypatch):
    models = _FakeModels(_FakeResponse("{}"))
    _patch(monkeypatch, models)

    with pytest.raises(GradingError):
        grade_answer("nd", "q", "recall", "   ")

    assert models.calls == 0
