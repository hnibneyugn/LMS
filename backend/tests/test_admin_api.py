import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import admin
from tests.conftest import auth_headers

client = TestClient(app)

ADMIN = "boss@example.com"


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN)


def _as_admin():
    return auth_headers(email=ADMIN)


def test_invite_requires_admin():
    r = client.post("/api/admin/invite", json={"email": "x@y.com"},
                    headers=auth_headers(email="nobody@else.com"))
    assert r.status_code == 403


def test_invite_requires_token():
    assert client.post("/api/admin/invite", json={"email": "x@y.com"}).status_code == 401


def test_invite_rejects_bad_email(monkeypatch):
    monkeypatch.setattr(admin.members, "invite_member", lambda e: pytest.fail("should not be called"))
    r = client.post("/api/admin/invite", json={"email": "not-an-email"}, headers=_as_admin())
    assert r.status_code == 422


def test_invite_happy_path(monkeypatch):
    monkeypatch.setattr(admin.members, "invite_member",
                        lambda e: {"email": e.lower(), "password_set": False, "created_at": "2026-07-22"})
    r = client.post("/api/admin/invite", json={"email": "New@Y.com"}, headers=_as_admin())
    assert r.status_code == 201
    assert r.json() == {"email": "new@y.com", "password_set": False, "created_at": "2026-07-22"}


def test_invite_duplicate_is_409(monkeypatch):
    def boom(e):
        raise admin.members.AlreadyMemberError("new@y.com đã là thành viên rồi.")
    monkeypatch.setattr(admin.members, "invite_member", boom)
    r = client.post("/api/admin/invite", json={"email": "new@y.com"}, headers=_as_admin())
    assert r.status_code == 409
    assert "thành viên" in r.json()["detail"]


def test_invite_upstream_failure_is_502(monkeypatch):
    def boom(e):
        raise admin.members.InviteError("Không mời được lúc này, thử lại sau.")
    monkeypatch.setattr(admin.members, "invite_member", boom)
    r = client.post("/api/admin/invite", json={"email": "new@y.com"}, headers=_as_admin())
    assert r.status_code == 502


def test_members_lists_for_admin(monkeypatch):
    monkeypatch.setattr(admin.members, "list_members",
                        lambda: [{"email": "a@x.com", "password_set": True, "created_at": "d"}])
    r = client.get("/api/admin/members", headers=_as_admin())
    assert r.status_code == 200
    assert r.json() == [{"email": "a@x.com", "password_set": True, "created_at": "d"}]


def test_members_requires_admin():
    assert client.get("/api/admin/members", headers=auth_headers(email="x@y.com")).status_code == 403


def test_members_upstream_failure_is_502(monkeypatch):
    def boom():
        raise httpx.HTTPError("down")
    monkeypatch.setattr(admin.members, "list_members", boom)
    r = client.get("/api/admin/members", headers=_as_admin())
    assert r.status_code == 502
