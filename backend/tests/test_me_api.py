from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import auth_headers

client = TestClient(app)


def test_me_flags_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "Boss@Example.com")
    body = client.get("/api/me", headers=auth_headers(email="boss@example.com")).json()
    assert body["is_admin"] is True
    assert body["email"] == "boss@example.com"


def test_me_flags_non_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    body = client.get("/api/me", headers=auth_headers(email="someone@else.com")).json()
    assert body["is_admin"] is False


def test_me_requires_a_token():
    assert client.get("/api/me").status_code == 401


def test_me_tolerates_unset_admin_email(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    resp = client.get("/api/me", headers=auth_headers(email="someone@else.com"))
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False
