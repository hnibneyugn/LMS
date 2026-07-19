import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import files as files_router
from tests.conftest import OTHER_USER_ID, USER_ID, FakeClient, auth_headers

client = TestClient(app)


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
        headers=auth_headers(),
    )
    assert res.status_code == 400
    assert repo.inserted == []


def test_presign_rejects_an_unknown_file_type(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.exe", "file_type": "exe", "file_size": 100},
        headers=auth_headers(),
    )
    assert res.status_code == 422


def test_presign_creates_a_pending_row_with_a_user_scoped_key(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.pdf", "file_type": "pdf", "file_size": 1000},
        headers=auth_headers(),
    )
    assert res.status_code == 200
    body = res.json()
    file_id = body["file_id"]
    assert body["storage_path"] == f"{USER_ID}/{file_id}.pdf"
    assert repo.rows[file_id]["processing_status"] == "pending"
    assert repo.rows[file_id]["user_id"] == USER_ID


def test_presign_requires_authentication(repo):
    res = client.post(
        "/api/files/presign",
        json={"file_name": "a.pdf", "file_type": "pdf", "file_size": 100},
    )
    assert res.status_code == 401


# --- process -----------------------------------------------------------------

def _make_row(repo, status="pending", user_id=USER_ID):
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
    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    assert res.status_code == 202
    assert repo.rows[file_id]["processing_status"] == "processing"


def test_process_on_another_users_file_is_404_not_403(repo):
    file_id = _make_row(repo, user_id=OTHER_USER_ID)
    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    assert res.status_code == 404


def test_process_while_already_processing_is_409(repo):
    file_id = _make_row(repo, status="processing")
    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
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

    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())

    assert res.status_code == 409
    assert calls == []


def test_process_retries_a_failed_file(repo):
    file_id = _make_row(repo, status="error")
    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    assert res.status_code == 202
    assert repo.rows[file_id]["processing_status"] == "processing"


def test_process_errors_when_the_object_is_missing_from_r2(repo, monkeypatch):
    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: False)
    file_id = _make_row(repo)
    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    assert res.status_code == 400
    assert repo.rows[file_id]["processing_status"] == "error"


def test_process_errors_when_the_object_is_missing_from_r2_sets_a_message(repo, monkeypatch):
    """The R2-missing path must not leave the row's status and message
    disagreeing with each other -- 'error' status with no (or a stale)
    message misleads the user about what actually happened."""
    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: False)
    file_id = _make_row(repo)
    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    assert res.status_code == 400
    assert repo.rows[file_id]["error_message"]


def test_process_retry_clears_the_previous_runs_error_message(repo):
    """A retry that succeeds in claiming the row for processing must not
    leave the previous failed run's error_message sitting on a row whose
    status now says 'processing' -- the poller would show a stale error for
    the whole processing window even though nothing is currently wrong."""
    file_id = _make_row(repo, status="error")
    repo.rows[file_id]["error_message"] = "Loi trich xuat lan truoc."

    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())

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

    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())

    assert res.status_code == 400
    assert repo.rows[file_id]["processing_status"] == "error"
    assert repo.rows[file_id]["error_message"] != old_message
    assert repo.rows[file_id]["error_message"]


def test_process_a_second_time_before_the_first_finishes_is_409(repo):
    """Calling process() twice in a row for the same file — the second call
    must see the first call's claim and be rejected, not silently queue a
    second background job."""
    file_id = _make_row(repo)
    first = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    second = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
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
        res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())

    assert res.status_code == 503
    assert "thử lại" in res.json()["detail"]
    assert repo.rows[file_id]["processing_status"] == "pending"
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_process_503_on_r2_outage_does_not_block_a_later_retry(repo, monkeypatch):
    file_id = _make_row(repo)

    def boom(_key):
        raise ConnectionError("R2 unreachable")

    monkeypatch.setattr(files_router.r2, "object_exists", boom)
    first = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    assert first.status_code == 503

    monkeypatch.setattr(files_router.r2, "object_exists", lambda k: True)
    second = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    assert second.status_code == 202


def test_process_on_confirmed_file_is_409(repo):
    file_id = "f-done"
    repo.rows[file_id] = {
        "id": file_id,
        "user_id": USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "storage_path": f"{USER_ID}/{file_id}.docx",
        "processing_status": "done",
    }
    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    assert res.status_code == 409
    assert res.json()["detail"] == "File đã được duyệt."
    assert repo.rows[file_id]["processing_status"] == "done"


def test_process_on_ready_for_review_still_reruns(repo):
    file_id = "f-ready"
    repo.rows[file_id] = {
        "id": file_id,
        "user_id": USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "storage_path": f"{USER_ID}/{file_id}.docx",
        "processing_status": "ready_for_review",
    }
    res = client.post(f"/api/files/{file_id}/process", headers=auth_headers())
    assert res.status_code == 202


# --- _Repo query building (real client) ---------------------------------------
#
# Everything above replaces the module-level `repo` with `_FakeRepo`, whose
# filtering logic is hand-written and independent of `_Repo`. That means
# `_Repo`'s actual supabase-py query building (the `.eq("user_id", ...)`
# calls that are the whole point of this file) never ran under test. The
# tests below run the REAL `_Repo` against a fake supabase CLIENT instead —
# same approach as test_pipeline.py's `FakeTable`/`FakeClient` — so a
# dropped `user_id` filter fails a test here even though it would sail
# through every test above.


@pytest.fixture
def real_repo(monkeypatch):
    """A REAL `_Repo` wired to a fake supabase client with a multi-user
    store, so tests exercise `_Repo`'s actual query-building code rather
    than a hand-written substitute.

    Two separate table stores (`user_files`, `lessons`) are wired through
    `FakeClient(tables=...)` so a query against one table can never see rows
    that only exist in the other -- `_Repo.list_lesson_slugs` reads
    `lessons`, everything else here reads `user_files`.
    """
    store = {
        "f1": {
            "id": "f1",
            "user_id": USER_ID,
            "file_name": "mine.md",
            "file_type": "md",
            "storage_path": f"{USER_ID}/f1.md",
            "processing_status": "pending",
        },
        "f2": {
            "id": "f2",
            "user_id": OTHER_USER_ID,
            "file_name": "theirs.md",
            "file_type": "md",
            "storage_path": f"{OTHER_USER_ID}/f2.md",
            "processing_status": "pending",
        },
    }
    lessons_store: dict = {}
    client_ = FakeClient(store, tables={"user_files": store, "lessons": lessons_store})
    monkeypatch.setattr(files_router.db, "admin", lambda: client_)
    return files_router._Repo(), store, lessons_store


def test_real_repo_get_file_does_not_return_another_users_row(real_repo):
    repo_, _store, _lessons = real_repo
    assert repo_.get_file("f2", USER_ID) is None
    assert repo_.get_file("f1", USER_ID) is not None


def test_real_repo_list_files_only_returns_own_rows(real_repo):
    repo_, _store, _lessons = real_repo
    ids = [r["id"] for r in repo_.list_files(USER_ID)]
    assert ids == ["f1"]


def test_real_repo_set_status_does_not_modify_another_users_row(real_repo):
    repo_, store, _lessons = real_repo
    repo_.set_status("f2", USER_ID, "error")
    assert store["f2"]["processing_status"] == "pending"  # untouched

    repo_.set_status("f1", USER_ID, "error")
    assert store["f1"]["processing_status"] == "error"


def test_real_repo_claim_for_processing_does_not_claim_another_users_row(real_repo):
    repo_, store, _lessons = real_repo
    claimed = repo_.claim_for_processing("f2", USER_ID)
    assert claimed == []
    assert store["f2"]["processing_status"] == "pending"


def test_real_repo_claim_for_processing_clears_previous_error_message(real_repo):
    """A retry must not carry the previous run's error_message forward: once
    a row is claimed for a new processing attempt, any stale message from an
    earlier failed run has to be cleared, or a later failure (or the
    in-flight `processing` window itself) would keep showing the OLD
    extraction error while the status says something else is happening."""
    repo_, store, _lessons = real_repo
    store["f1"]["processing_status"] = "error"
    store["f1"]["error_message"] = "Loi trich xuat lan truoc."

    claimed = repo_.claim_for_processing("f1", USER_ID)

    assert claimed[0]["error_message"] is None
    assert store["f1"]["error_message"] is None


def test_real_repo_claim_for_processing_only_lets_one_caller_win(real_repo):
    """Exercises the conditional UPDATE (`.neq("processing_status",
    "processing")`) that closes the check-then-act race: of two sequential
    claims on the same not-yet-processing row, only the first may succeed."""
    repo_, _store, _lessons = real_repo
    first = repo_.claim_for_processing("f1", USER_ID)
    second = repo_.claim_for_processing("f1", USER_ID)
    assert len(first) == 1
    assert second == []


def test_real_repo_list_lesson_slugs_only_returns_own_slugs(real_repo):
    """`_Repo.list_lesson_slugs` backs the uniqueness check `confirm` runs
    before writing new lessons. Without its `user_id` filter this would read
    every user's slugs, so user A's new lesson could silently collide with
    (and get suffixed against) a slug that only exists because user B has a
    lesson with that name -- a cross-user side channel through slug clashes.
    """
    repo_, _store, lessons_store = real_repo
    lessons_store["l1"] = {"id": "l1", "user_id": USER_ID, "slug": "mine-0"}
    lessons_store["l2"] = {"id": "l2", "user_id": OTHER_USER_ID, "slug": "theirs-0"}

    assert repo_.list_lesson_slugs(USER_ID) == ["mine-0"]


# --- read --------------------------------------------------------------------

def test_get_file_returns_status_and_outline(repo):
    file_id = _make_row(repo, status="ready_for_review")
    repo.rows[file_id]["draft_outline"] = [
        {"title": "A", "content_md": "x", "order_index": 0}
    ]
    res = client.get(f"/api/files/{file_id}", headers=auth_headers())
    assert res.status_code == 200
    assert res.json()["processing_status"] == "ready_for_review"
    assert res.json()["draft_outline"][0]["title"] == "A"


def test_get_another_users_file_is_404(repo):
    file_id = _make_row(repo, user_id=OTHER_USER_ID)
    res = client.get(f"/api/files/{file_id}", headers=auth_headers())
    assert res.status_code == 404


def test_list_files_only_returns_own_files(repo):
    mine = _make_row(repo)
    _make_row(repo, user_id=OTHER_USER_ID)
    res = client.get("/api/files", headers=auth_headers())
    assert res.status_code == 200
    assert [f["id"] for f in res.json()] == [mine]


def test_list_files_hides_storage_path_and_user_id(repo):
    repo.rows["f-list"] = {
        "id": "f-list",
        "user_id": USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "file_size": 123,
        "storage_path": f"{USER_ID}/f-list.docx",
        "processing_status": "ready_for_review",
        "draft_outline": [
            {"title": "a", "content_md": "aa", "order_index": 0},
            {"title": "b", "content_md": "bb", "order_index": 1},
        ],
    }
    res = client.get("/api/files", headers=auth_headers())
    assert res.status_code == 200
    row = res.json()[0]
    assert "storage_path" not in row
    assert "user_id" not in row
    assert "draft_outline" not in row
    assert row["chapter_count"] == 2


def test_list_files_reports_null_chapter_count_before_processing(repo):
    repo.rows["f-pending"] = {
        "id": "f-pending",
        "user_id": USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "file_size": 1,
        "storage_path": f"{USER_ID}/f-pending.docx",
        "processing_status": "pending",
    }
    res = client.get("/api/files", headers=auth_headers())
    assert res.json()[0]["chapter_count"] is None


def test_get_file_includes_draft_outline_but_not_storage_path(repo):
    repo.rows["f-one"] = {
        "id": "f-one",
        "user_id": USER_ID,
        "file_name": "x.docx",
        "file_type": "docx",
        "file_size": 5,
        "storage_path": f"{USER_ID}/f-one.docx",
        "processing_status": "ready_for_review",
        "draft_outline": [{"title": "a", "content_md": "aa", "order_index": 0}],
    }
    res = client.get("/api/files/f-one", headers=auth_headers())
    assert res.status_code == 200
    body = res.json()
    assert "storage_path" not in body
    assert "user_id" not in body
    assert body["draft_outline"] == [
        {"title": "a", "content_md": "aa", "order_index": 0}
    ]
    assert body["chapter_count"] == 1
