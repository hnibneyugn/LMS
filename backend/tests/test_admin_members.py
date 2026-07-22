import httpx
import pytest

from app.admin import members


class _Resp:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


@pytest.fixture(autouse=True)
def _svc_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")


def _fake_httpx(monkeypatch, *, users=None, get_status=200, post=None):
    def fake_get(url, headers=None, params=None, timeout=None):
        return _Resp(get_status, {"users": users or []})

    def fake_post(url, headers=None, json=None, timeout=None):
        return post(json) if post else _Resp(201, json)

    monkeypatch.setattr(members.httpx, "get", fake_get)
    monkeypatch.setattr(members.httpx, "post", fake_post)


def test_list_members_summarizes_rows(monkeypatch):
    _fake_httpx(monkeypatch, users=[
        {"email": "A@X.com", "user_metadata": {"password_set": True}, "created_at": "2026-01-01"},
        {"email": "b@x.com", "user_metadata": {}, "created_at": "2026-01-02"},
    ])
    rows = members.list_members()
    assert rows == [
        {"email": "a@x.com", "password_set": True, "created_at": "2026-01-01"},
        {"email": "b@x.com", "password_set": False, "created_at": "2026-01-02"},
    ]


def test_invite_member_sends_proven_payload(monkeypatch):
    captured = {}

    def post(json):
        captured.update(json)
        return _Resp(201, {"email": json["email"], "user_metadata": json["user_metadata"], "created_at": "2026-07-22"})

    _fake_httpx(monkeypatch, users=[], post=post)
    out = members.invite_member("New@X.com")
    assert captured["email"] == "new@x.com"
    assert captured["email_confirm"] is True
    assert captured["user_metadata"] == {"password_set": False}
    assert out == {"email": "new@x.com", "password_set": False, "created_at": "2026-07-22"}


def test_invite_member_rejects_duplicate(monkeypatch):
    _fake_httpx(monkeypatch, users=[{"email": "dup@x.com", "user_metadata": {}, "created_at": "x"}])
    with pytest.raises(members.AlreadyMemberError):
        members.invite_member("DUP@x.com")


def test_invite_member_wraps_upstream_failure(monkeypatch):
    def post(json):
        return _Resp(500, {})

    _fake_httpx(monkeypatch, users=[], post=post)
    with pytest.raises(members.InviteError):
        members.invite_member("new@x.com")


def test_invite_member_wraps_transport_error_on_create(monkeypatch):
    def post(json):
        raise httpx.ConnectError("down")

    _fake_httpx(monkeypatch, users=[], post=post)
    with pytest.raises(members.InviteError):
        members.invite_member("new@x.com")
