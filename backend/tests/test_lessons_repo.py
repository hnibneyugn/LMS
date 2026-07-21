"""_Repo query building (real client) -- see test_files_api.py's `real_repo`
fixture, which this mirrors.

test_lessons_api.py swaps `repo` out wholesale for `_FakeRepo`, whose
filtering logic is hand-written and independent of `_Repo`. That means the
REAL `_Repo`'s supabase-py query building -- the `.eq("user_id", ...)` calls
that are the only thing standing between one user's data and another's, since
`db.admin()` is a service-role client that bypasses RLS -- never runs under
those tests. The tests here run the REAL `_Repo` against a fake supabase
CLIENT instead, so a dropped `user_id` filter fails a test here even though
it would sail straight through test_lessons_api.py.

Task 3 extends this file with `get_lesson` and upsert coverage below.
"""

import pytest

from app.routers import lessons as lessons_router
from tests.conftest import OTHER_USER_ID, USER_ID, FakeClient


@pytest.fixture
def real_repo(monkeypatch):
    """A REAL `_Repo` wired to a fake supabase client with a multi-user
    store, so tests exercise `_Repo`'s actual query-building code rather
    than `_FakeRepo`'s hand-written substitute.

    Three separate table stores (`lessons`, `user_files`, `lesson_progress`)
    are wired through `FakeClient(tables=...)` so a query against one table
    can never see rows that only exist in another. `l1`/`l2` belong to
    USER_ID; `l9` belongs to OTHER_USER_ID and deliberately reuses the slug
    "gt-0" -- a naive query that forgets the `user_id` filter would still
    "work" by accident if the two users' rows never collided.
    """
    lessons_store = {
        "l1": {
            "id": "l1",
            "user_id": USER_ID,
            "slug": "gt-0",
            "title": "Chương 1",
            "order_index": 0,
            "source_file_id": "f1",
            "content_md": "# Chương 1\n\nnội dung",
        },
        "l2": {
            "id": "l2",
            "user_id": USER_ID,
            "slug": "gt-1",
            "title": "Chương 2",
            "order_index": 1,
            "source_file_id": "f1",
            "content_md": "# Chương 2\n\nnội dung",
        },
        "l9": {
            "id": "l9",
            "user_id": OTHER_USER_ID,
            "slug": "gt-0",
            "title": "Của họ",
            "order_index": 0,
            "source_file_id": None,
            "content_md": "riêng tư",
        },
    }
    files_store = {
        "f1": {"id": "f1", "user_id": USER_ID, "file_name": "mine.docx"},
        "f2": {"id": "f2", "user_id": OTHER_USER_ID, "file_name": "theirs.docx"},
    }
    progress_store = {
        "p1": {
            "user_id": USER_ID,
            "lesson_id": "l1",
            "status": "done",
            "completed_at": "2026-07-20T10:00:00+00:00",
        },
        "p9": {
            "user_id": OTHER_USER_ID,
            "lesson_id": "l9",
            "status": "done",
            "completed_at": "2026-07-19T10:00:00+00:00",
        },
    }
    client_ = FakeClient(
        lessons_store,
        tables={
            "lessons": lessons_store,
            "user_files": files_store,
            "lesson_progress": progress_store,
        },
    )
    monkeypatch.setattr(lessons_router.db, "admin", lambda: client_)
    return lessons_router._Repo()


def test_real_repo_list_lessons_only_returns_own_rows(real_repo):
    ids = {r["id"] for r in real_repo.list_lessons(USER_ID)}
    assert ids == {"l1", "l2"}


def test_real_repo_list_file_names_only_returns_own_files(real_repo):
    assert real_repo.list_file_names(USER_ID) == {"f1": "mine.docx"}


def test_real_repo_list_progress_only_returns_own_rows(real_repo):
    progress = real_repo.list_progress(USER_ID)
    assert list(progress.keys()) == ["l1"]


def test_real_repo_get_lesson_by_slug_does_not_return_another_users_row(real_repo):
    mine = real_repo.get_lesson_by_slug(USER_ID, "gt-0")
    theirs = real_repo.get_lesson_by_slug(OTHER_USER_ID, "gt-0")

    assert mine["id"] == "l1"
    assert theirs["id"] == "l9"


def test_real_repo_get_lesson_by_slug_returns_none_for_an_unknown_slug(real_repo):
    assert real_repo.get_lesson_by_slug(USER_ID, "khong-co") is None


# --- progress (Task 3) --------------------------------------------------------


@pytest.fixture
def stores(monkeypatch):
    """Empty per-table stores, routed the same way `real_repo` does, but
    starting blank -- the progress/get_lesson tests below want full control
    over exactly what rows exist rather than `real_repo`'s fixed fixtures.
    """
    tables = {
        "lessons": {},
        "user_files": {},
        "lesson_progress": {},
    }
    client_ = FakeClient({}, tables=tables)
    monkeypatch.setattr(lessons_router.db, "admin", lambda: client_)
    return tables


def test_real_repo_get_lesson_does_not_return_another_users_row(stores):
    stores["lessons"]["l1"] = {"id": "l1", "user_id": USER_ID, "slug": "gt-0"}

    repo = lessons_router._Repo()

    assert repo.get_lesson("l1", USER_ID)["id"] == "l1"
    assert repo.get_lesson("l1", OTHER_USER_ID) is None


def test_real_repo_upsert_progress_keys_on_user_and_lesson(stores):
    repo = lessons_router._Repo()

    repo.upsert_progress(
        {"user_id": USER_ID, "lesson_id": "l1", "status": "done", "completed_at": "t"}
    )
    repo.upsert_progress(
        {"user_id": USER_ID, "lesson_id": "l1", "status": "not_done", "completed_at": None}
    )

    # Second call must replace the first, not add a second row.
    assert len(stores["lesson_progress"]) == 1
    stored = next(iter(stores["lesson_progress"].values()))
    assert stored["status"] == "not_done"
    assert stored["completed_at"] is None
