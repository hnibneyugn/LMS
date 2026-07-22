import pytest

from app.config import settings


def test_r2_endpoint_is_built_from_account_id(monkeypatch):
    monkeypatch.setenv("R2_ACCOUNT_ID", "abc123")
    assert settings.r2_endpoint() == "https://abc123.r2.cloudflarestorage.com"


def test_missing_r2_config_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("R2_ACCOUNT_ID", raising=False)
    with pytest.raises(RuntimeError, match="R2_ACCOUNT_ID"):
        settings.r2_endpoint()


def test_limits_match_the_spec():
    assert settings.MAX_FILE_BYTES == 20 * 1024 * 1024
    assert settings.PRESIGN_EXPIRY_SECONDS == 900
    assert settings.ALLOWED_FILE_TYPES == frozenset({"md", "docx", "pptx", "pdf"})


def test_gemini_api_key_is_read_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-secret")
    assert settings.gemini_api_key() == "g-secret"


def test_missing_gemini_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        settings.gemini_api_key()


def test_admin_email_is_read_from_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    assert settings.admin_email() == "boss@example.com"


def test_missing_admin_email_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    with pytest.raises(RuntimeError, match="ADMIN_EMAIL"):
        settings.admin_email()
