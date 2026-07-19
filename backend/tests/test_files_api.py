import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.main import app
from app.routers import files as files_router

client = TestClient(app)

_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_USER_ID = "11111111-1111-1111-1111-111111111111"
_OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def _auth(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example-project.supabase.co")
    monkeypatch.setattr(
        "app.dependencies.auth._get_signing_key", lambda token: _PUBLIC_KEY
    )


def _headers(user_id: str = _USER_ID) -> dict:
    token = jwt.encode(
        {"sub": user_id, "email": "a@b.c", "aud": "authenticated"},
        _PRIVATE_KEY,
        algorithm="ES256",
    )
    return {"Authorization": f"Bearer {token}"}


class _FakeRepo:
    """Stands in for every db call the router makes.

    Mirrors the real _Repo's method signatures (including the user_id scoping
    on set_status/claim_for_processing) so the router-level tests below still
    exercise the router's own logic faithfully. The real query-building code
    inside _Repo is exercised separately by the `real_repo` fixture further
    down, against a fake supabase client rather than a fake repo.
    """

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.inserted: list[dict] = []

    def insert_file(self, values):
        self.rows[values["id"]] = dict(values)
        self.inserted.append(values)

    def get_file(self, file_id, user_id):
        row = self.rows.get(file_id)
        if row is None or row["user_id"] != user_id:
            return None
        return row

    def list_files(self, user_id):
        return [r for r in self.rows.values() if r["user_id"] == user_id]

    def set_status(self, file_id, user_id, status, error_message=None):
        row = self.rows.get(file_id)
        if row is None or row["user_id"] != user_id:
            return
        row["processing_status"] = status
        if error_message is not None:
            row["error_message"] = error_message

    def claim_for_processing(self, file_id, user_id):
        row = self.rows.get(file_id)
        if row is None or row["user_id"] != user_id:
            return []
        if row["processing_status"] == "processing":
            return []
        row["processing_status"] = "processing"
        row["error_message"] = None
        return [row]


@pytest.fixture
def repo(monkeypatch):
    fake = _FakeRepo()
    monkeypatch.setattr(files_router, "repo", fake)
    monkeypatch.setattr(files_router.r2, "presign_put", lambda k, n: f"https://r2/{k}")
    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: True)
    monkeypatch.setattr(files_router.pipeline, "process_file", lambda file_id: None)
    return fake


# --- presign -----------------------------------------------------------------

def test_presign_rejects_a_file_over_20mb(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.pdf", "file_type": "pdf", "file_size": 21 * 1024 * 1024},
        headers=_headers(),
    )
    assert res.status_code == 400
    assert repo.inserted == []


def test_presign_rejects_an_unknown_file_type(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.exe", "file_type": "exe", "file_size": 100},
        headers=_headers(),
    )
    assert res.status_code == 422


def test_presign_creates_a_pending_row_with_a_user_scoped_key(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.pdf", "file_type": "pdf", "file_size": 1000},
        headers=_headers(),
    )
    assert res.status_code == 200
    body = res.json()
    file_id = body["file_id"]
    assert body["storage_path"] == f"{_USER_ID}/{file_id}.pdf"
    assert repo.rows[file_id]["processing_status"] == "pending"
    assert repo.rows[file_id]["user_id"] == _USER_ID


def test_presign_requires_authentication(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.pdf", "file_type": "pdf", "file_size": 100},
    )
    assert res.status_code == 401


# --- process -----------------------------------------------------------------

def _make_row(repo, status="pending", user_id=_USER_ID):
    file_id = str(uuid.uuid4())
    repo.insert_file(
        {
            "id": file_id,
            "user_id": user_id,
            "file_name": "a.pdf",
            "file_type": "pdf",
            "storage_path": f"{user_id}/{file_id}.pdf",
            "processing_status": status,
        }
    )
    return file_id


def test_process_marks_processing_and_returns_202(repo):
    file_id = _make_row(repo)
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 202
    assert repo.rows[file_id]["processing_status"] == "processing"


def test_process_on_another_users_file_is_404_not_403(repo):
    file_id = _make_row(repo, user_id=_OTHER_USER_ID)
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 404


def test_process_while_already_processing_is_409(repo):
    file_id = _make_row(repo, status="processing")
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 409


def test_process_on_an_in_flight_file_is_409_even_when_r2_is_down(repo, monkeypatch):
    """A duplicate click must not be answered with a storage error.

    An already-processing file is short-circuited before R2 is consulted, so a
    transient outage cannot mask the real reason the request was refused.
    """
    calls = []

    def exploding_object_exists(key):
        calls.append(key)
        raise RuntimeError("R2 unreachable")

    monkeypatch.setattr(files_router.r2, "object_exists", exploding_object_exists)
    file_id = _make_row(repo, status="processing")

    res = client.post(f"/api/files/{file_id}/process", headers=_headers())

    assert res.status_code == 409
    assert calls == []


def test_process_retries_a_failed_file(repo):
    file_id = _make_row(repo, status="error")
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 202
    assert repo.rows[file_id]["processing_status"] == "processing"


def test_process_errors_when_the_object_is_missing_from_r2(repo, monkeypatch):
    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: False)
    file_id = _make_row(repo)
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 400
    assert repo.rows[file_id]["processing_status"] == "error"


def test_process_errors_when_the_object_is_missing_from_r2_sets_a_message(repo, monkeypatch):
    """The R2-missing path must not leave the row's status and message
    disagreeing with each other -- 'error' status with no (or a stale)
    message misleads the user about what actually happened."""
    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: False)
    file_id = _make_row(repo)
    res = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert res.status_code == 400
    assert repo.rows[file_id]["error_message"]


def test_process_retry_clears_the_previous_runs_error_message(repo):
    """A retry that succeeds in claiming the row for processing must not
    leave the previous failed run's error_message sitting on a row whose
    status now says 'processing' -- the poller would show a stale error for
    the whole processing window even though nothing is currently wrong."""
    file_id = _make_row(repo, status="error")
    repo.rows[file_id]["error_message"] = "Loi trich xuat lan truoc."

    res = client.post(f"/api/files/{file_id}/process", headers=_headers())

    assert res.status_code == 202
    assert repo.rows[file_id]["error_message"] is None


def test_retry_failing_the_r2_check_does_not_keep_the_previous_runs_error_message(
    repo, monkeypatch
):
    """A retry that fails the R2 head-check must land in 'error' showing the
    NEW reason (file missing from storage), not the previous run's
    extraction failure message -- status and message must always agree."""
    file_id = _make_row(repo, status="error")
    old_message = "Loi trich xuat lan truoc: dinh dang khong hop le."
    repo.rows[file_id]["error_message"] = old_message
    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: False)

    res = client.post(f"/api/files/{file_id}/process", headers=_headers())

    assert res.status_code == 400
    assert repo.rows[file_id]["processing_status"] == "error"
    assert repo.rows[file_id]["error_message"] != old_message
    assert repo.rows[file_id]["error_message"]


def test_process_a_second_time_before_the_first_finishes_is_409(repo):
    """Calling process() twice in a row for the same file — the second call
    must see the first call's claim and be rejected, not silently queue a
    second background job."""
    file_id = _make_row(repo)
    first = client.post(f"/api/files/{file_id}/process", headers=_headers())
    second = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert first.status_code == 202
    assert second.status_code == 409
    assert repo.rows[file_id]["processing_status"] == "processing"


def test_process_returns_503_when_r2_is_unreachable(repo, monkeypatch, caplog):
    """A raised exception from r2.object_exists (bad credentials, R2 outage)
    is not the same thing as "the object is missing" -- it must surface as a
    503 with a Vietnamese retry message, and must NOT mark the row 'error'
    since the file itself is fine and a retry should just work."""

    def boom(_key):
        raise ConnectionError("R2 unreachable")

    monkeypatch.setattr(files_router.r2, "object_exists", boom)
    file_id = _make_row(repo)

    with caplog.at_level("ERROR", logger="app.routers.files"):
        res = client.post(f"/api/files/{file_id}/process", headers=_headers())

    assert res.status_code == 503
    assert "thử lại" in res.json()["detail"]
    assert repo.rows[file_id]["processing_status"] == "pending"
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_process_503_on_r2_outage_does_not_block_a_later_retry(repo, monkeypatch):
    file_id = _make_row(repo)

    def boom(_key):
        raise ConnectionError("R2 unreachable")

    monkeypatch.setattr(files_router.r2, "object_exists", boom)
    first = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert first.status_code == 503

    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: True)
    second = client.post(f"/api/files/{file_id}/process", headers=_headers())
    assert second.status_code == 202


# --- _Repo query building (real client) ---------------------------------------
#
# Everything above replaces the module-level `repo` with `_FakeRepo`, whose
# filtering logic is hand-written and independent of `_Repo`. That means
# `_Repo`'s actual supabase-py query building (the `.eq("user_id", ...)`
# calls that are the whole point of this file) never ran under test. The
# tests below run the REAL `_Repo` against a fake supabase CLIENT instead —
# same approach as test_pipeline.py's `_FakeTable`/`_FakeClient` — so a
# dropped `user_id` filter fails a test here even though it would sail
# through every test above.


class _FakeTable:
    """Mimics the slice of supabase-py's fluent query builder `_Repo` uses.

    Same shape as test_pipeline.py's fake: filters accumulate across chained
    `.eq()`/`.neq()` calls and are applied together in `execute()`.
    """

    def __init__(self, store):
        self._store = store
        self._filters: dict[str, object] = {}
        self._neq_filters: dict[str, object] = {}
        self._update_values: dict | None = None
        self._insert_values: dict | None = None
        self._maybe_single = False

    def select(self, *_columns):
        return self

    def insert(self, values):
        self._insert_values = values
        return self

    def update(self, values):
        self._update_values = values
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def neq(self, column, value):
        self._neq_filters[column] = value
        return self

    def order(self, _column, desc=False):
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def _matches(self):
        return [
            row
            for row in self._store.values()
            if all(row.get(k) == v for k, v in self._filters.items())
            and all(row.get(k) != v for k, v in self._neq_filters.items())
        ]

    def execute(self):
        if self._insert_values is not None:
            self._store[self._insert_values["id"]] = dict(self._insert_values)
            return type("Res", (), {"data": [dict(self._insert_values)]})()
        matches = self._matches()
        if self._update_values is not None:
            for row in matches:
                row.update(self._update_values)
            return type("Res", (), {"data": [dict(row) for row in matches]})()
        if self._maybe_single:
            if not matches:
                return None
            return type("Res", (), {"data": dict(matches[0])})()
        return type("Res", (), {"data": [dict(row) for row in matches]})()


class _FakeClient:
    def __init__(self, store):
        self._store = store

    def table(self, _name):
        return _FakeTable(self._store)


@pytest.fixture
def real_repo(monkeypatch):
    """A REAL `_Repo` wired to a fake supabase client with a multi-user
    store, so tests exercise `_Repo`'s actual query-building code rather
    than a hand-written substitute."""
    store = {
        "f1": {
            "id": "f1",
            "user_id": _USER_ID,
            "file_name": "mine.md",
            "file_type": "md",
            "storage_path": f"{_USER_ID}/f1.md",
            "processing_status": "pending",
        },
        "f2": {
            "id": "f2",
            "user_id": _OTHER_USER_ID,
            "file_name": "theirs.md",
            "file_type": "md",
            "storage_path": f"{_OTHER_USER_ID}/f2.md",
            "processing_status": "pending",
        },
    }
    client_ = _FakeClient(store)
    monkeypatch.setattr(files_router.db, "admin", lambda: client_)
    return files_router._Repo(), store


def test_real_repo_get_file_does_not_return_another_users_row(real_repo):
    repo_, _store = real_repo
    assert repo_.get_file("f2", _USER_ID) is None
    assert repo_.get_file("f1", _USER_ID) is not None


def test_real_repo_list_files_only_returns_own_rows(real_repo):
    repo_, _store = real_repo
    ids = [r["id"] for r in repo_.list_files(_USER_ID)]
    assert ids == ["f1"]


def test_real_repo_set_status_does_not_modify_another_users_row(real_repo):
    repo_, store = real_repo
    repo_.set_status("f2", _USER_ID, "error")
    assert store["f2"]["processing_status"] == "pending"  # untouched

    repo_.set_status("f1", _USER_ID, "error")
    assert store["f1"]["processing_status"] == "error"


def test_real_repo_claim_for_processing_does_not_claim_another_users_row(real_repo):
    repo_, store = real_repo
    claimed = repo_.claim_for_processing("f2", _USER_ID)
    assert claimed == []
    assert store["f2"]["processing_status"] == "pending"


def test_real_repo_claim_for_processing_clears_previous_error_message(real_repo):
    """A retry must not carry the previous run's error_message forward: once
    a row is claimed for a new processing attempt, any stale message from an
    earlier failed run has to be cleared, or a later failure (or the
    in-flight `processing` window itself) would keep showing the OLD
    extraction error while the status says something else is happening."""
    repo_, store = real_repo
    store["f1"]["processing_status"] = "error"
    store["f1"]["error_message"] = "Loi trich xuat lan truoc."

    claimed = repo_.claim_for_processing("f1", _USER_ID)

    assert claimed[0]["error_message"] is None
    assert store["f1"]["error_message"] is None


def test_real_repo_claim_for_processing_only_lets_one_caller_win(real_repo):
    """Exercises the conditional UPDATE (`.neq("processing_status",
    "processing")`) that closes the check-then-act race: of two sequential
    claims on the same not-yet-processing row, only the first may succeed."""
    repo_, _store = real_repo
    first = repo_.claim_for_processing("f1", _USER_ID)
    second = repo_.claim_for_processing("f1", _USER_ID)
    assert len(first) == 1
    assert second == []


# --- read --------------------------------------------------------------------

def test_get_file_returns_status_and_outline(repo):
    file_id = _make_row(repo, status="ready_for_review")
    repo.rows[file_id]["draft_outline"] = [
        {"title": "A", "content_md": "x", "order_index": 0}
    ]
    res = client.get(f"/api/files/{file_id}", headers=_headers())
    assert res.status_code == 200
    assert res.json()["processing_status"] == "ready_for_review"
    assert res.json()["draft_outline"][0]["title"] == "A"


def test_get_another_users_file_is_404(repo):
    file_id = _make_row(repo, user_id=_OTHER_USER_ID)
    res = client.get(f"/api/files/{file_id}", headers=_headers())
    assert res.status_code == 404


def test_list_files_only_returns_own_files(repo):
    mine = _make_row(repo)
    _make_row(repo, user_id=_OTHER_USER_ID)
    res = client.get("/api/files", headers=_headers())
    assert res.status_code == 200
    assert [f["id"] for f in res.json()] == [mine]
