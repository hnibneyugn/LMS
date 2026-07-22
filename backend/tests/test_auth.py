import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import CurrentUser, require_admin
from app.main import app
from tests.conftest import _PRIVATE_KEY, _PUBLIC_KEY, auth_headers

client = TestClient(app)

# Reuses conftest's keypair (rather than generating a second one) so that
# this module's own `_stub_signing_key` fixture and conftest's autouse `auth`
# fixture patch `_get_signing_key` to the same value -- both are function-
# scoped autouse fixtures with no ordering dependency between them, so
# whichever ran last would otherwise silently win, breaking tokens signed
# with the other module's key (e.g. `auth_headers` from conftest).
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
    assert res.json() == {"user_id": "user-123", "email": "a@b.c", "is_admin": False}


_probe = FastAPI()


@_probe.get("/probe")
def _probe_route(user: CurrentUser = Depends(require_admin)):
    return {"email": user.email}


_probe_client = TestClient(_probe)


def test_require_admin_allows_admin_case_insensitively(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "Boss@Example.com")
    res = _probe_client.get("/probe", headers=auth_headers(email="boss@example.com"))
    assert res.status_code == 200


def test_require_admin_rejects_non_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    res = _probe_client.get("/probe", headers=auth_headers(email="someone@else.com"))
    assert res.status_code == 403


def test_require_admin_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    assert _probe_client.get("/probe").status_code == 401
