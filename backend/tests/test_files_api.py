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
    """Stands in for every db call the router makes."""

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

    def set_status(self, file_id, status):
        self.rows[file_id]["processing_status"] = status


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
