import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import lessons as lessons_router
from tests.conftest import OTHER_USER_ID, USER_ID, auth_headers

client = TestClient(app)


class _FakeRepo:
    """Stands in for every db call the router makes.

    Mirrors the real _Repo's signatures, including the user_id scoping, so
    router tests still exercise the router's own logic faithfully. The real
    query-building code is exercised separately in test_lessons_repo.py.
    """

    def __init__(self):
        self.lessons: list[dict] = []
        self.files: dict[str, dict] = {}
        self.progress: list[dict] = []
        self.upserted: list[dict] = []

    def list_lessons(self, user_id):
        return [dict(r) for r in self.lessons if r["user_id"] == user_id]

    def get_lesson_by_slug(self, user_id, slug):
        for row in self.lessons:
            if row["user_id"] == user_id and row["slug"] == slug:
                return dict(row)
        return None

    def get_lesson(self, lesson_id, user_id):
        for row in self.lessons:
            if row["id"] == lesson_id and row["user_id"] == user_id:
                return dict(row)
        return None

    def list_file_names(self, user_id):
        return {
            fid: f["file_name"]
            for fid, f in self.files.items()
            if f["user_id"] == user_id
        }

    def list_progress(self, user_id):
        return {p["lesson_id"]: dict(p) for p in self.progress if p["user_id"] == user_id}

    def upsert_progress(self, values):
        self.upserted.append(dict(values))


def make_lesson(lesson_id, slug, title, order_index, file_id, user_id=USER_ID):
    return {
        "id": lesson_id,
        "user_id": user_id,
        "slug": slug,
        "title": title,
        "order_index": order_index,
        "source_file_id": file_id,
        "content_md": f"# {title}\n\nnội dung",
    }


@pytest.fixture
def repo(monkeypatch):
    fake = _FakeRepo()
    monkeypatch.setattr(lessons_router, "repo", fake)
    return fake


# --- list --------------------------------------------------------------------

def test_list_returns_only_my_lessons_with_file_name_and_progress(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "giao-trinh.docx"}
    repo.lessons = [
        make_lesson("l1", "gt-0", "Chương 1", 0, "f1"),
        make_lesson("l2", "gt-1", "Chương 2", 1, "f1"),
        make_lesson("l9", "khac-0", "Của người khác", 0, "f1", user_id=OTHER_USER_ID),
    ]
    repo.progress = [
        {"user_id": USER_ID, "lesson_id": "l1", "status": "done", "completed_at": "2026-07-20T10:00:00+00:00"}
    ]

    res = client.get("/api/lessons", headers=auth_headers())

    assert res.status_code == 200
    body = res.json()
    assert [r["slug"] for r in body] == ["gt-0", "gt-1"]
    assert body[0]["source_file_name"] == "giao-trinh.docx"
    assert body[0]["done"] is True
    assert body[0]["completed_at"] == "2026-07-20T10:00:00+00:00"
    # No lesson_progress row at all means not done, not an error.
    assert body[1]["done"] is False
    assert body[1]["completed_at"] is None


def test_list_sorts_orphan_lessons_last(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "b-sach.docx"}
    repo.files["f2"] = {"user_id": USER_ID, "file_name": "a-sach.pdf"}
    repo.lessons = [
        # source_file_id is ON DELETE SET NULL, so an orphan is a real state.
        make_lesson("l0", "mo-coi", "Mồ côi", 0, None),
        make_lesson("l1", "b-1", "B chương 2", 1, "f1"),
        make_lesson("l2", "b-0", "B chương 1", 0, "f1"),
        make_lesson("l3", "a-0", "A chương 1", 0, "f2"),
    ]

    body = client.get("/api/lessons", headers=auth_headers()).json()

    assert [r["slug"] for r in body] == ["a-0", "b-0", "b-1", "mo-coi"]
    assert body[-1]["source_file_name"] is None


def test_list_requires_a_token(repo):
    assert client.get("/api/lessons").status_code == 401


# --- detail ------------------------------------------------------------------

def test_detail_returns_content_and_neighbours(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "giao-trinh.docx"}
    repo.lessons = [
        make_lesson("l1", "gt-0", "Chương 1", 0, "f1"),
        make_lesson("l2", "gt-1", "Chương 2", 1, "f1"),
        make_lesson("l3", "gt-2", "Chương 3", 2, "f1"),
    ]

    body = client.get("/api/lessons/gt-1", headers=auth_headers()).json()

    assert body["content_md"] == "# Chương 2\n\nnội dung"
    assert body["source_file_name"] == "giao-trinh.docx"
    assert body["prev"] == {"slug": "gt-0", "title": "Chương 1"}
    assert body["next"] == {"slug": "gt-2", "title": "Chương 3"}


def test_detail_neighbours_are_null_at_both_ends(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "giao-trinh.docx"}
    repo.lessons = [
        make_lesson("l1", "gt-0", "Chương 1", 0, "f1"),
        make_lesson("l2", "gt-1", "Chương 2", 1, "f1"),
    ]

    first = client.get("/api/lessons/gt-0", headers=auth_headers()).json()
    last = client.get("/api/lessons/gt-1", headers=auth_headers()).json()

    assert first["prev"] is None
    assert first["next"] == {"slug": "gt-1", "title": "Chương 2"}
    assert last["prev"] == {"slug": "gt-0", "title": "Chương 1"}
    assert last["next"] is None


def test_detail_neighbours_never_cross_into_another_file(repo):
    repo.files["f1"] = {"user_id": USER_ID, "file_name": "a.docx"}
    repo.files["f2"] = {"user_id": USER_ID, "file_name": "b.docx"}
    repo.lessons = [
        make_lesson("l1", "a-0", "A chương 1", 0, "f1"),
        make_lesson("l2", "b-0", "B chương 1", 0, "f2"),
    ]

    body = client.get("/api/lessons/a-0", headers=auth_headers()).json()

    assert body["prev"] is None
    assert body["next"] is None


def test_detail_of_an_orphan_lesson_has_no_neighbours(repo):
    repo.lessons = [make_lesson("l0", "mo-coi", "Mồ côi", 0, None)]

    body = client.get("/api/lessons/mo-coi", headers=auth_headers()).json()

    assert body["prev"] is None
    assert body["next"] is None
    assert body["source_file_name"] is None


def test_detail_of_another_users_lesson_is_404_not_403(repo):
    # 403 would confirm the slug exists; 404 gives nothing away.
    repo.lessons = [make_lesson("l9", "cua-ho", "Của họ", 0, None, user_id=OTHER_USER_ID)]

    res = client.get("/api/lessons/cua-ho", headers=auth_headers())

    assert res.status_code == 404
    assert res.json()["detail"] == "Không tìm thấy bài học."


def test_detail_of_an_unknown_slug_is_404(repo):
    res = client.get("/api/lessons/khong-co", headers=auth_headers())
    assert res.status_code == 404


def test_detail_requires_a_token(repo):
    assert client.get("/api/lessons/gt-0").status_code == 401


# --- progress ------------------------------------------------------------------

def test_marking_done_upserts_progress_with_a_timestamp(repo):
    repo.lessons = [make_lesson("l1", "gt-0", "Chương 1", 0, None)]

    res = client.put(
        "/api/lessons/l1/progress", json={"done": True}, headers=auth_headers()
    )

    assert res.status_code == 200
    assert res.json()["done"] is True
    assert res.json()["completed_at"] is not None
    written = repo.upserted[-1]
    assert written["user_id"] == USER_ID
    assert written["lesson_id"] == "l1"
    assert written["status"] == "done"
    assert written["completed_at"] == res.json()["completed_at"]


def test_unmarking_clears_the_timestamp(repo):
    repo.lessons = [make_lesson("l1", "gt-0", "Chương 1", 0, None)]

    client.put("/api/lessons/l1/progress", json={"done": True}, headers=auth_headers())
    res = client.put(
        "/api/lessons/l1/progress", json={"done": False}, headers=auth_headers()
    )

    assert res.json() == {"done": False, "completed_at": None}
    assert repo.upserted[-1]["status"] == "not_done"
    assert repo.upserted[-1]["completed_at"] is None


def test_progress_on_another_users_lesson_is_404_and_writes_nothing(repo):
    repo.lessons = [make_lesson("l9", "cua-ho", "Của họ", 0, None, user_id=OTHER_USER_ID)]

    res = client.put(
        "/api/lessons/l9/progress", json={"done": True}, headers=auth_headers()
    )

    assert res.status_code == 404
    assert repo.upserted == []


def test_progress_requires_a_token(repo):
    res = client.put("/api/lessons/l1/progress", json={"done": True})
    assert res.status_code == 401
