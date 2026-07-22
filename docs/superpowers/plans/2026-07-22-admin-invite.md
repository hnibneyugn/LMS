# #7 `/admin/invite` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the admin an in-app, admin-only page to invite new members (and see who's already in) instead of running `invite_user.py` from a terminal.

**Architecture:** A thin FastAPI router (`/api/admin/*`) guarded by a `require_admin` dependency that compares the JWT email to `ADMIN_EMAIL`; the actual Supabase Admin API calls live in a small `app/admin/members.py` helper. The frontend learns whether the current user is admin via a new `is_admin` flag on `/api/me` (so `ADMIN_EMAIL` never reaches the browser), and shows a gated `/admin/invite` page.

**Tech Stack:** Python + FastAPI + httpx (backend), pytest; React + Vite + TypeScript + Shadcn (frontend). No new dependencies. No DB migration.

## Global Constraints

- **Isolation:** every admin endpoint depends on `require_admin`; the backend NEVER trusts the frontend for authorization.
- **Secrets server-side:** `ADMIN_EMAIL` and `SUPABASE_SERVICE_ROLE_KEY` stay in the backend; the browser only ever sees a boolean `is_admin`.
- **Graceful degradation (design principle #4):** Supabase/Admin-API failures become a 502 with a Vietnamese message, never a bare 500.
- **Language:** user-facing strings = Vietnamese; code/identifiers/comments = English.
- **Invite payload (proven in `invite_user.py`):** create user with `email_confirm: true` and `user_metadata: {password_set: false}` — NO password field. Do not send any invitation email (no `/auth/v1/invite`).
- **Verify style:** backend `pytest` from `backend/` must be green with clean output; frontend `npm run build` + `oxlint` clean; plus a real end-to-end `verify_7.py`.
- **Email compare is case-insensitive** everywhere (`.strip().lower()`).

---

### Task 1: `settings.admin_email()` + `require_admin` dependency

**Files:**
- Modify: `backend/app/config/settings.py`
- Modify: `backend/app/dependencies/auth.py`
- Modify: `backend/tests/conftest.py` (add optional `email` arg to `auth_headers`)
- Test: `backend/tests/test_settings.py`, `backend/tests/test_auth.py`

**Interfaces:**
- Produces: `settings.admin_email() -> str` (raises `RuntimeError` if `ADMIN_EMAIL` unset); `app.dependencies.auth.require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser` (raises `HTTPException(403)` for non-admin); `tests.conftest.auth_headers(user_id=USER_ID, email="a@b.c") -> dict`.

- [ ] **Step 1: Extend `auth_headers` in conftest to take an email**

In `backend/tests/conftest.py`, change the helper signature and its token payload:

```python
def auth_headers(user_id: str = USER_ID, email: str = "a@b.c") -> dict:
    token = jwt.encode(
        {"sub": user_id, "email": email, "aud": "authenticated"},
        _PRIVATE_KEY,
        algorithm="ES256",
    )
    return {"Authorization": f"Bearer {token}"}
```

- [ ] **Step 2: Write the failing settings test**

Add to `backend/tests/test_settings.py`:

```python
def test_admin_email_is_read_from_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    assert settings.admin_email() == "boss@example.com"


def test_missing_admin_email_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    with pytest.raises(RuntimeError, match="ADMIN_EMAIL"):
        settings.admin_email()
```

- [ ] **Step 3: Run it, verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_settings.py::test_admin_email_is_read_from_env -v` (from `backend/`)
Expected: FAIL — `AttributeError: module 'app.config.settings' has no attribute 'admin_email'`.

- [ ] **Step 4: Implement `admin_email()`**

In `backend/app/config/settings.py`, add next to the other `_required` helpers:

```python
def admin_email() -> str:
    return _required("ADMIN_EMAIL")
```

- [ ] **Step 5: Run settings tests, verify pass**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_settings.py -v`
Expected: PASS.

- [ ] **Step 6: Write the failing `require_admin` tests**

Add to `backend/tests/test_auth.py`:

```python
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import CurrentUser, require_admin
from tests.conftest import auth_headers

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
```

(If `test_auth.py` already imports `pytest`/`TestClient`, don't duplicate the imports.)

- [ ] **Step 7: Run them, verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_auth.py -k require_admin -v`
Expected: FAIL — `ImportError: cannot import name 'require_admin'`.

- [ ] **Step 8: Implement `require_admin`**

In `backend/app/dependencies/auth.py`, add the import at the top and the dependency at the bottom:

```python
from fastapi import Depends, Header, HTTPException, status

from app.config import settings
```

```python
def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Allow only the configured ADMIN_EMAIL. The real authorization boundary
    for every /api/admin/* route — never trust the frontend for this."""
    admin = settings.admin_email().strip().lower()
    if not user.email or user.email.strip().lower() != admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ admin mới được phép."
        )
    return user
```

(Merge the `Depends` into the existing `from fastapi import ...` line rather than adding a second import.)

- [ ] **Step 9: Run auth tests, verify pass**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_auth.py -v`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/config/settings.py backend/app/dependencies/auth.py backend/tests/conftest.py backend/tests/test_settings.py backend/tests/test_auth.py
git commit -m "feat(7): admin_email setting + require_admin dependency

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `/api/me` exposes `is_admin`

**Files:**
- Modify: `backend/app/routers/me.py`
- Test: `backend/tests/test_me_api.py` (create)

**Interfaces:**
- Produces: `GET /api/me` → `{user_id: str, email: str | None, is_admin: bool}`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_me_api.py`:

```python
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
```

- [ ] **Step 2: Run it, verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_me_api.py -v`
Expected: FAIL — `KeyError: 'is_admin'`.

- [ ] **Step 3: Implement**

Replace `backend/app/routers/me.py` with:

```python
from fastapi import APIRouter, Depends

from app.config import settings
from app.dependencies.auth import CurrentUser, get_current_user

router = APIRouter()


@router.get("/api/me")
def read_me(user: CurrentUser = Depends(get_current_user)):
    admin = settings.admin_email().strip().lower()
    is_admin = bool(user.email) and user.email.strip().lower() == admin
    return {"user_id": user.user_id, "email": user.email, "is_admin": is_admin}
```

- [ ] **Step 4: Run it, verify pass**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_me_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/me.py backend/tests/test_me_api.py
git commit -m "feat(7): /api/me returns is_admin flag

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `app/admin/members.py` — Supabase Admin API helper

**Files:**
- Create: `backend/app/admin/__init__.py` (empty)
- Create: `backend/app/admin/members.py`
- Test: `backend/tests/test_admin_members.py`

**Interfaces:**
- Consumes: `settings.supabase_url()`, `settings.supabase_service_role_key()`.
- Produces:
  - `members.list_members() -> list[dict]` — each `{"email": str, "password_set": bool, "created_at": str | None}`.
  - `members.find_member(email: str) -> dict | None` — raw Supabase user dict or None.
  - `members.invite_member(email: str) -> dict` — summarized member dict of the created user.
  - Exceptions `members.AlreadyMemberError`, `members.InviteError` (both `Exception` subclasses; `str(e)` is a Vietnamese message).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_members.py`:

```python
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
```

- [ ] **Step 2: Run them, verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_members.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.admin'`.

- [ ] **Step 3: Create the package + helper**

Create empty `backend/app/admin/__init__.py`. Create `backend/app/admin/members.py`:

```python
"""Supabase Admin API calls for member invites (#7).

Kept out of the router so the router stays thin. Mirrors the proven payload in
scripts/invite_user.py: create the auth user with no password, email_confirm
true, and password_set false so the login page forces them to set one.

Uses the service-role key (bypasses RLS) — backend only.
"""

import httpx

from app.config import settings


class AlreadyMemberError(Exception):
    """Email is already a member — surfaced to the caller as a 409."""


class InviteError(Exception):
    """Supabase/Admin API failed — surfaced as a 502 (graceful degradation)."""


def _base_and_headers() -> tuple[str, dict]:
    base = settings.supabase_url()
    key = settings.supabase_service_role_key()
    return base, {"apikey": key, "Authorization": f"Bearer {key}"}


def _summarize(user: dict) -> dict:
    """Only the fields the UI needs — never leak ids/tokens."""
    meta = user.get("user_metadata") or {}
    return {
        "email": (user.get("email") or "").lower(),
        "password_set": bool(meta.get("password_set", False)),
        "created_at": user.get("created_at"),
    }


def _fetch_users() -> list[dict]:
    base, headers = _base_and_headers()
    res = httpx.get(
        f"{base}/auth/v1/admin/users",
        headers=headers,
        params={"page": 1, "per_page": 200},
        timeout=30,
    )
    res.raise_for_status()
    return res.json().get("users", [])


def list_members() -> list[dict]:
    return [_summarize(u) for u in _fetch_users()]


def find_member(email: str) -> dict | None:
    wanted = email.strip().lower()
    return next(
        (u for u in _fetch_users() if (u.get("email") or "").lower() == wanted), None
    )


def invite_member(email: str) -> dict:
    email = email.strip().lower()
    try:
        existing = find_member(email)
    except httpx.HTTPError as err:
        raise InviteError("Không mời được lúc này, thử lại sau.") from err
    if existing is not None:
        raise AlreadyMemberError(f"{email} đã là thành viên rồi.")

    base, headers = _base_and_headers()
    res = httpx.post(
        f"{base}/auth/v1/admin/users",
        headers=headers,
        json={
            "email": email,
            "email_confirm": True,
            "user_metadata": {"password_set": False},
        },
        timeout=30,
    )
    if res.status_code not in (200, 201):
        raise InviteError("Không mời được lúc này, thử lại sau.")
    return _summarize(res.json())
```

- [ ] **Step 4: Run them, verify pass**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_members.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/admin/__init__.py backend/app/admin/members.py backend/tests/test_admin_members.py
git commit -m "feat(7): members helper for Supabase Admin API (invite/list)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `app/routers/admin.py` + wire into app

**Files:**
- Create: `backend/app/routers/admin.py`
- Modify: `backend/app/main.py` (import + `include_router`)
- Test: `backend/tests/test_admin_api.py`

**Interfaces:**
- Consumes: `members.list_members`, `members.invite_member`, `members.AlreadyMemberError`, `members.InviteError`; `require_admin`.
- Produces:
  - `POST /api/admin/invite` body `{email: str}` → `201 {email, password_set, created_at}`; `422` invalid email; `409` duplicate; `502` upstream.
  - `GET /api/admin/members` → `200 [{email, password_set, created_at}]`; `502` upstream.
  - Both require admin (`403` non-admin, `401` no token).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_api.py`:

```python
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
```

- [ ] **Step 2: Run them, verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin'`.

- [ ] **Step 3: Create the router**

Create `backend/app/routers/admin.py`:

```python
"""Admin-only member management (#7): invite a member, list members.

Thin router — Supabase Admin API calls live in app/admin/members.py. Every
route depends on require_admin (the real authorization boundary)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.admin import members
from app.dependencies.auth import CurrentUser, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


class InviteIn(BaseModel):
    email: str


class Member(BaseModel):
    email: str
    password_set: bool
    created_at: str | None = None


def _valid_email(email: str) -> bool:
    email = email.strip()
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain


@router.get("/members", response_model=list[Member])
def list_members(_: CurrentUser = Depends(require_admin)):
    try:
        return members.list_members()
    except httpx.HTTPError as err:
        raise HTTPException(502, "Không tải được danh sách thành viên.") from err


@router.post("/invite", response_model=Member, status_code=201)
def invite(body: InviteIn, _: CurrentUser = Depends(require_admin)):
    if not _valid_email(body.email):
        raise HTTPException(422, "Email không hợp lệ.")
    try:
        return members.invite_member(body.email)
    except members.AlreadyMemberError as err:
        raise HTTPException(409, str(err)) from err
    except members.InviteError as err:
        raise HTTPException(502, str(err)) from err
```

- [ ] **Step 4: Wire it into the app**

In `backend/app/main.py`, add `admin` to the routers import and include it:

```python
from app.routers import admin, chat, dashboard, files, health, lessons, me, quiz
```

```python
app.include_router(admin.router)
```

(Add the `include_router(admin.router)` line alongside the other includes.)

- [ ] **Step 5: Run the admin API tests, verify pass**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_admin_api.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite (clean output required)**

Run: `backend/.venv/Scripts/python.exe -m pytest`
Expected: all green, no warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/admin.py backend/app/main.py backend/tests/test_admin_api.py
git commit -m "feat(7): /api/admin/invite + /api/admin/members endpoints

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Frontend — `/admin/invite` page + admin-gated nav

**Files:**
- Create: `frontend/src/lib/admin.ts`
- Create: `frontend/src/pages/AdminInvite.tsx`
- Modify: `frontend/src/App.tsx` (add route)
- Modify: `frontend/src/pages/Dashboard.tsx` (admin-only nav button)

**Interfaces:**
- Consumes: `apiFetch` from `@/lib/api`, `errorMessage` from `@/lib/files`, `Button` from `@/components/ui/button`, `Input` from `@/components/ui/input`.
- Produces: `getMe(): Promise<Me>`, `listMembers(): Promise<Member[]>`, `inviteMember(email): Promise<Member>`; `Me = {user_id, email, is_admin}`, `Member = {email, password_set, created_at}`.

- [ ] **Step 1: Create the API wrapper**

Create `frontend/src/lib/admin.ts`:

```typescript
import { apiFetch } from "@/lib/api"

export interface Me {
  user_id: string
  email: string | null
  is_admin: boolean
}

export interface Member {
  email: string
  password_set: boolean
  created_at: string | null
}

/** Current user, including whether they are the admin (drives admin-only UI). */
export async function getMe(): Promise<Me> {
  return (await apiFetch("/api/me")) as Me
}

/** All members (admin only). */
export async function listMembers(): Promise<Member[]> {
  return (await apiFetch("/api/admin/members")) as Member[]
}

/** Invite a member by email (admin only). Returns the created member. */
export async function inviteMember(email: string): Promise<Member> {
  return (await apiFetch("/api/admin/invite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  })) as Member
}
```

- [ ] **Step 2: Create the page**

Create `frontend/src/pages/AdminInvite.tsx`:

```tsx
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { errorMessage } from "@/lib/files"
import { getMe, listMembers, inviteMember, type Member } from "@/lib/admin"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function AdminInvite() {
  const navigate = useNavigate()
  const [checking, setChecking] = useState(true)
  const [members, setMembers] = useState<Member[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [email, setEmail] = useState("")
  const [sending, setSending] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  // Gate on is_admin; the backend enforces this independently, this is just UX.
  useEffect(() => {
    getMe()
      .then((me) => {
        if (!me.is_admin) {
          navigate("/", { replace: true })
          return
        }
        setChecking(false)
        listMembers()
          .then(setMembers)
          .catch((e) => setLoadError(errorMessage(e)))
      })
      .catch(() => navigate("/", { replace: true }))
  }, [navigate])

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    setOk(null)
    setSending(true)
    try {
      const member = await inviteMember(email.trim())
      setMembers((prev) => [member, ...(prev ?? []).filter((m) => m.email !== member.email)])
      setOk(`Đã mời ${member.email}.`)
      setEmail("")
    } catch (err) {
      setFormError(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  if (checking) return <p className="p-8 text-sm text-gray-500">Đang tải…</p>

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Mời thành viên</h1>
        <Button variant="outline" onClick={() => navigate("/")}>
          Về bảng điều khiển
        </Button>
      </header>

      <form onSubmit={handleInvite} className="flex gap-2">
        <Input
          type="email"
          placeholder="email@thanhvien.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Button type="submit" disabled={sending || !email.trim()}>
          {sending ? "Đang mời…" : "Mời"}
        </Button>
      </form>
      {ok && <p className="text-sm text-green-600">{ok}</p>}
      {formError && <p className="text-sm text-red-600">{formError}</p>}

      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-700">Thành viên hiện có</h2>
        {loadError ? (
          <p className="text-sm text-red-600">Không tải được danh sách: {loadError}</p>
        ) : !members ? (
          <p className="text-sm text-gray-500">Đang tải…</p>
        ) : members.length === 0 ? (
          <p className="text-sm text-gray-500">Chưa có thành viên nào.</p>
        ) : (
          <ul className="divide-y text-sm">
            {members.map((m) => (
              <li key={m.email} className="flex items-center justify-between py-2">
                <span>{m.email}</span>
                <span className={m.password_set ? "text-green-600" : "text-gray-400"}>
                  {m.password_set ? "Đã đặt mật khẩu" : "Chưa đặt mật khẩu"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
```

- [ ] **Step 3: Register the route in App.tsx**

In `frontend/src/App.tsx`, add the import and a protected route (before the catch-all `/*`):

```tsx
import { AdminInvite } from "@/pages/AdminInvite"
```

```tsx
        <Route
          path="/admin/invite"
          element={
            <ProtectedRoute>
              <AdminInvite />
            </ProtectedRoute>
          }
        />
```

- [ ] **Step 4: Add the admin-only nav button on the Dashboard**

In `frontend/src/pages/Dashboard.tsx`:

Add the import:

```tsx
import { getMe } from "@/lib/admin"
```

Add state next to the other `useState` calls:

```tsx
  const [isAdmin, setIsAdmin] = useState(false)
```

In the existing `useEffect`, after the `supabase.auth.getUser()` block, add:

```tsx
    getMe().then((me) => setIsAdmin(me.is_admin)).catch(() => setIsAdmin(false))
```

In the header's button group, add as the first button (before "Bài học"):

```tsx
          {isAdmin && <Button onClick={() => navigate("/admin/invite")}>Mời thành viên</Button>}
```

- [ ] **Step 5: Build + lint, verify clean**

Run (from `frontend/`): `npm run build && npx oxlint`
Expected: no TypeScript errors, oxlint clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/admin.ts frontend/src/pages/AdminInvite.tsx frontend/src/App.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(7): /admin/invite page + admin-only nav button

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Real end-to-end verify + checklist update

**Files:**
- Create: `backend/scripts/verify_7.py`
- Modify: `check_list.md`

**Interfaces:**
- Consumes: `mint_access_token()` from `backend/scripts/verify_1b.py` (mints a live ADMIN session); `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` from env; API running on `http://localhost:8000`.

- [ ] **Step 1: Write the verify script**

Create `backend/scripts/verify_7.py`:

```python
"""Live check of #7 admin invite endpoints against the real API + Supabase Auth.

Mints an ADMIN session, invites a throwaway email through /api/admin/invite,
confirms the user now exists with password_set=false, checks the duplicate 409
and that the member list includes it, then DELETES the throwaway user so the
project returns to its original state.

The non-admin 403 boundary is covered by pytest (test_admin_api.py) — minting a
second real non-admin Supabase session would need a second password-set account.

Usage: PYTHONIOENCODING=utf-8 python scripts/verify_7.py
Requires the API on http://localhost:8000, SUPABASE_ANON_KEY in the env
(frontend/.env.local), and SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in backend/.env.
"""

import os
import sys
import uuid

import httpx
from dotenv import load_dotenv

from verify_1b import mint_access_token

load_dotenv()

API = "http://localhost:8000"


def _svc_headers(service_key):
    return {"apikey": service_key, "Authorization": f"Bearer {service_key}"}


def _find_user(base, service_key, email):
    res = httpx.get(
        f"{base}/auth/v1/admin/users",
        headers=_svc_headers(service_key),
        params={"page": 1, "per_page": 200},
        timeout=30,
    )
    res.raise_for_status()
    for u in res.json().get("users", []):
        if (u.get("email") or "").lower() == email:
            return u
    return None


def main() -> int:
    token = mint_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    base = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    throwaway = f"verify7-{uuid.uuid4().hex[:8]}@example.com"
    created_id = None
    try:
        # Invite through the real endpoint.
        r = httpx.post(f"{API}/api/admin/invite", headers=headers,
                       json={"email": throwaway}, timeout=30)
        print("invite:", r.status_code, r.text)
        assert r.status_code == 201, r.text
        assert r.json()["password_set"] is False

        # Confirm via Admin API + capture id for cleanup.
        user = _find_user(base, service_key, throwaway)
        assert user is not None, "invited user should exist"
        created_id = user["id"]
        assert (user.get("user_metadata") or {}).get("password_set") is False

        # Duplicate invite -> 409.
        dup = httpx.post(f"{API}/api/admin/invite", headers=headers,
                         json={"email": throwaway}, timeout=30)
        print("duplicate:", dup.status_code)
        assert dup.status_code == 409, dup.text

        # Member list includes it.
        members = httpx.get(f"{API}/api/admin/members", headers=headers, timeout=30).json()
        emails = {m["email"] for m in members}
        assert throwaway in emails, "member list should include the invited email"

        print("\nALL CHECKS PASSED")
        return 0
    finally:
        # Clean up: delete the throwaway user so nothing is left behind.
        if created_id is None:
            user = _find_user(base, service_key, throwaway)
            created_id = user["id"] if user else None
        if created_id:
            httpx.request("DELETE", f"{base}/auth/v1/admin/users/{created_id}",
                          headers=_svc_headers(service_key), timeout=30)
            print(f"cleaned up throwaway user {throwaway}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Start the backend (separate terminal) and run the verify**

Start (from `backend/`, with `.venv` active): `python -m uvicorn app.main:app --port 8000`
Run (from `backend/`): `PYTHONIOENCODING=utf-8 SUPABASE_ANON_KEY=<from frontend/.env.local> python scripts/verify_7.py`
Expected: prints `invite: 201 ...`, `duplicate: 409`, `cleaned up throwaway user ...`, then `ALL CHECKS PASSED`.

- [ ] **Step 3: Re-run the full backend suite + frontend build one more time**

Run (from `backend/`): `backend/.venv/Scripts/python.exe -m pytest`
Run (from `frontend/`): `npm run build && npx oxlint`
Expected: backend green + clean output; frontend clean.

- [ ] **Step 4: Mark #7 done in `check_list.md`**

Replace the `### #7 — /admin/invite` block (line ~280) with a completed entry that records: endpoints (`POST /api/admin/invite`, `GET /api/admin/members`), `require_admin` gate, `/api/me` `is_admin`, the page, no migration, test counts, and the `verify_7.py` evidence (invite 201 → user exists with `password_set:false` → duplicate 409 → member list → cleanup). Mirror the format of the #6 entry above it.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/verify_7.py check_list.md
git commit -m "test(7): live end-to-end verify_7 + mark #7 done

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** admin gate (Task 1), `/api/me is_admin` (Task 2), members helper with proven payload + graceful degradation (Task 3), both endpoints with the full error table 403/422/409/502 (Task 4), page with member list + form + admin nav gating + redirect (Task 5), real verify + no-migration confirmation + checklist (Task 6). All spec sections map to a task.
- **Type consistency:** `Member {email, password_set, created_at}` identical in `members.py` (`_summarize`), the router `Member` model, and frontend `admin.ts`. `Me {user_id, email, is_admin}` matches `/api/me` and `admin.ts`. `require_admin` signature matches its usage in the router.
- **No placeholders:** every code step is complete; the only prose step is the checklist wording (Task 6 Step 4), which is documentation, not code.
