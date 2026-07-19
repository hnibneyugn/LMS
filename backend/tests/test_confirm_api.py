import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import files as files_router
from tests.conftest import OTHER_USER_ID, USER_ID, auth_headers

client = TestClient(app)


def _outline(count: int) -> list[dict]:
    return [
        {"title": f"Chương {i}", "content_md": f"Nội dung {i}", "order_index": i}
        for i in range(count)
    ]


class _FakeRepo:
    """Stands in for every db call `confirm` makes."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.lessons: list[dict] = []
        self.insert_should_fail = False

    def get_file(self, file_id, user_id):
        row = self.rows.get(file_id)
        if row is None or row["user_id"] != user_id:
            return None
        return row

    def set_status(self, file_id, user_id, status, error_message=None):
        row = self.rows.get(file_id)
        if row is None or row["user_id"] != user_id:
            return
        row["processing_status"] = status
        if error_message is not None:
            row["error_message"] = error_message

    def insert_lessons(self, rows):
        if self.insert_should_fail:
            raise RuntimeError("db down")
        self.lessons.extend(rows)

    def list_lesson_slugs(self, user_id):
        return [
            lesson["slug"] for lesson in self.lessons if lesson["user_id"] == user_id
        ]


@pytest.fixture
def repo(monkeypatch):
    fake = _FakeRepo()
    monkeypatch.setattr(files_router, "repo", fake)
    return fake


def _ready_file(repo, file_id="f1", user_id=USER_ID, chapters=3, name="Giáo trình.docx"):
    repo.rows[file_id] = {
        "id": file_id,
        "user_id": user_id,
        "file_name": name,
        "file_type": "docx",
        "processing_status": "ready_for_review",
        "draft_outline": _outline(chapters),
    }
    return file_id


def test_confirm_writes_one_lesson_per_chapter(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={
            "chapters": [
                {"title": "Bài một", "source_indexes": [0]},
                {"title": "Bài hai", "source_indexes": [1]},
                {"title": "Bài ba", "source_indexes": [2]},
            ]
        },
        headers=auth_headers(),
    )
    assert res.status_code == 200
    assert res.json() == {"lesson_count": 3}
    assert [lesson["title"] for lesson in repo.lessons] == ["Bài một", "Bài hai", "Bài ba"]
    assert [lesson["order_index"] for lesson in repo.lessons] == [0, 1, 2]
    assert all(lesson["user_id"] == USER_ID for lesson in repo.lessons)
    assert all(lesson["source_file_id"] == file_id for lesson in repo.lessons)
    assert repo.rows[file_id]["processing_status"] == "done"


def test_confirm_merges_adjacent_chapters(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={
            "chapters": [
                {"title": "Gộp", "source_indexes": [0, 1]},
                {"title": "Riêng", "source_indexes": [2]},
            ]
        },
        headers=auth_headers(),
    )
    assert res.status_code == 200
    assert res.json() == {"lesson_count": 2}
    assert repo.lessons[0]["content_md"] == "Nội dung 0\n\nNội dung 1"
    assert repo.lessons[1]["content_md"] == "Nội dung 2"


def test_confirm_drops_omitted_chapters(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "Chỉ giữ cái giữa", "source_indexes": [1]}]},
        headers=auth_headers(),
    )
    assert res.status_code == 200
    assert len(repo.lessons) == 1
    assert repo.lessons[0]["content_md"] == "Nội dung 1"


def test_confirm_trims_title(repo):
    file_id = _ready_file(repo)
    client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "  Có khoảng trắng  ", "source_indexes": [0]}]},
        headers=auth_headers(),
    )
    assert repo.lessons[0]["title"] == "Có khoảng trắng"


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"chapters": []}, "empty chapters"),
        ({"chapters": [{"title": "", "source_indexes": [0]}]}, "empty title"),
        ({"chapters": [{"title": "   ", "source_indexes": [0]}]}, "blank title"),
        ({"chapters": [{"title": "x" * 201, "source_indexes": [0]}]}, "title too long"),
        ({"chapters": [{"title": "ok", "source_indexes": []}]}, "empty indexes"),
    ],
)
def test_confirm_rejects_malformed_payload(repo, payload, reason):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm", json=payload, headers=auth_headers()
    )
    assert res.status_code == 422, reason
    assert repo.rows[file_id]["processing_status"] == "ready_for_review"


def test_confirm_rejects_out_of_range_index(repo):
    file_id = _ready_file(repo, chapters=2)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [5]}]},
        headers=auth_headers(),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Danh sách chương không hợp lệ."
    assert repo.lessons == []


def test_confirm_rejects_negative_index(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [-1]}]},
        headers=auth_headers(),
    )
    assert res.status_code == 400


def test_confirm_rejects_index_used_twice(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={
            "chapters": [
                {"title": "a", "source_indexes": [0]},
                {"title": "b", "source_indexes": [0]},
            ]
        },
        headers=auth_headers(),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Một chương gốc không thể nằm trong hai bài học."
    assert repo.lessons == []


def test_confirm_rejects_non_adjacent_merge(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "a", "source_indexes": [0, 2]}]},
        headers=auth_headers(),
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Chỉ gộp được các chương liền kề."


def test_confirm_rejects_descending_merge(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "a", "source_indexes": [1, 0]}]},
        headers=auth_headers(),
    )
    assert res.status_code == 400


@pytest.mark.parametrize(
    ("file_status", "detail"),
    [
        ("pending", "File chưa xử lý xong."),
        ("processing", "File chưa xử lý xong."),
        ("error", "File xử lý lỗi — hãy xử lý lại trước khi duyệt."),
        ("done", "File đã được duyệt."),
    ],
)
def test_confirm_rejects_wrong_status(repo, file_status, detail):
    file_id = _ready_file(repo)
    repo.rows[file_id]["processing_status"] = file_status
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
        headers=auth_headers(),
    )
    assert res.status_code == 409
    assert res.json()["detail"] == detail
    assert repo.lessons == []


def test_confirm_rejects_empty_outline(repo):
    """A `ready_for_review` row with no draft chapters is an inconsistent
    state (nothing was ever extracted), not a normal confirm -- it must be
    refused with the same "not done processing" 409 the pending/processing
    statuses get, not fall through to the range check below it."""
    file_id = _ready_file(repo, chapters=0)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
        headers=auth_headers(),
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "File chưa xử lý xong."
    assert repo.lessons == []


def test_confirm_on_another_users_file_is_404(repo):
    file_id = _ready_file(repo, user_id=OTHER_USER_ID)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
        headers=auth_headers(),
    )
    assert res.status_code == 404
    assert repo.lessons == []


def test_confirm_without_token_is_401(repo):
    file_id = _ready_file(repo)
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
    )
    assert res.status_code == 401


def test_confirm_leaves_file_reviewable_when_insert_fails(repo):
    file_id = _ready_file(repo)
    repo.insert_should_fail = True
    with pytest.raises(RuntimeError):
        client.post(
            f"/api/files/{file_id}/confirm",
            json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
            headers=auth_headers(),
        )
    assert repo.rows[file_id]["processing_status"] == "ready_for_review"
    assert repo.lessons == []


def test_confirm_avoids_slug_collision_with_existing_lessons(repo):
    repo.lessons.append(
        {"user_id": USER_ID, "slug": "giao-trinh-0", "title": "cũ"}
    )
    file_id = _ready_file(repo, chapters=1, name="Giáo trình.docx")
    res = client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "mới", "source_indexes": [0]}]},
        headers=auth_headers(),
    )
    assert res.status_code == 200
    assert repo.lessons[-1]["slug"] == "giao-trinh-0-2"


def test_confirm_falls_back_when_file_name_has_no_usable_characters(repo):
    file_id = _ready_file(repo, chapters=1, name="!!!.docx")
    client.post(
        f"/api/files/{file_id}/confirm",
        json={"chapters": [{"title": "ok", "source_indexes": [0]}]},
        headers=auth_headers(),
    )
    assert repo.lessons[0]["slug"] == "bai-0"
