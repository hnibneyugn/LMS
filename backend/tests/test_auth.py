import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app

SECRET = "test-secret-for-hs256"
client = TestClient(app)


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)


def _token(payload: dict) -> str:
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_me_without_header_is_401():
    res = client.get("/api/me")
    assert res.status_code == 401


def test_me_with_malformed_header_is_401():
    res = client.get("/api/me", headers={"Authorization": "Token abc"})
    assert res.status_code == 401


def test_me_with_invalid_signature_is_401():
    bad = jwt.encode({"sub": "u1", "aud": "authenticated"}, "wrong-secret", algorithm="HS256")
    res = client.get("/api/me", headers={"Authorization": f"Bearer {bad}"})
    assert res.status_code == 401


def test_me_with_wrong_audience_is_401():
    tok = _token({"sub": "u1", "email": "a@b.c", "aud": "anon"})
    res = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 401


def test_me_with_valid_token_returns_user():
    tok = _token({"sub": "user-123", "email": "a@b.c", "aud": "authenticated"})
    res = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 200
    assert res.json() == {"user_id": "user-123", "email": "a@b.c"}
