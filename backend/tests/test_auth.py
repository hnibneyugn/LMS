import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# EC P-256 keypair generated once for the whole test module. Signing with this
# key and monkeypatching `_get_signing_key` to return its public key lets us
# exercise real ES256/JWKS verification logic without any network call.
_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _PRIVATE_KEY.public_key()

_OTHER_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(autouse=True)
def _stub_signing_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example-project.supabase.co")
    monkeypatch.setattr(
        "app.dependencies.auth._get_signing_key", lambda token: _PUBLIC_KEY
    )


def _token(payload: dict) -> str:
    return jwt.encode(payload, _PRIVATE_KEY, algorithm="ES256")


def test_me_without_header_is_401():
    res = client.get("/api/me")
    assert res.status_code == 401


def test_me_with_malformed_header_is_401():
    res = client.get("/api/me", headers={"Authorization": "Token abc"})
    assert res.status_code == 401


def test_me_with_invalid_signature_is_401():
    bad = jwt.encode(
        {"sub": "u1", "aud": "authenticated"},
        _OTHER_PRIVATE_KEY,
        algorithm="ES256",
    )
    res = client.get("/api/me", headers={"Authorization": f"Bearer {bad}"})
    assert res.status_code == 401


def test_me_with_wrong_audience_is_401():
    tok = _token({"sub": "u1", "email": "a@b.c", "aud": "anon"})
    res = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 401


def test_me_with_expired_token_is_401():
    tok = _token({"sub": "u1", "email": "a@b.c", "aud": "authenticated", "exp": 0})
    res = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 401


def test_me_with_valid_token_returns_user():
    tok = _token({"sub": "user-123", "email": "a@b.c", "aud": "authenticated"})
    res = client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 200
    assert res.json() == {"user_id": "user-123", "email": "a@b.c"}
