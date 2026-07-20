import pytest

from app.ingest import pipeline
from tests.conftest import FakeClient


class _Row(dict):
    """A store row that also exposes the write-attempt log recorded by
    FakeTable, so tests can assert on attempted writes without disturbing
    the plain `fake_db["field"]` access the rest of the suite relies on.
    """

    write_log: list[dict]


@pytest.fixture
def fake_db(monkeypatch):
    row = _Row(
        id="f1",
        user_id="u1",
        file_name="giao-trinh.md",
        file_type="md",
        storage_path="u1/f1.md",
        processing_status="processing",
        draft_outline=None,
        error_message=None,
    )
    store = {"f1": row}
    write_log: list[dict] = []
    row.write_log = write_log
    client = FakeClient(store, write_log)
    monkeypatch.setattr(pipeline.db, "admin", lambda: client)
    return row


def test_successful_run_stores_the_outline_and_marks_ready(fake_db, monkeypatch):
    monkeypatch.setattr(
        pipeline.r2, "download", lambda key: b"# A\nnoi dung a\n\n# B\nnoi dung b\n"
    )
    pipeline.process_file("f1")

    assert fake_db["processing_status"] == "ready_for_review"
    assert [c["title"] for c in fake_db["draft_outline"]] == ["A", "B"]
    assert fake_db["error_message"] is None


def test_extract_error_is_recorded_as_a_vietnamese_message(fake_db, monkeypatch):
    fake_db["file_type"] = "pdf"
    fake_db["storage_path"] = "u1/f1.pdf"
    monkeypatch.setattr(pipeline.r2, "download", lambda key: b"khong phai pdf")

    pipeline.process_file("f1")

    assert fake_db["processing_status"] == "error"
    assert "pdf" in fake_db["error_message"].lower()


def test_unexpected_exception_does_not_escape(fake_db, monkeypatch):
    def boom(_key):
        raise ConnectionError("R2 down")

    monkeypatch.setattr(pipeline.r2, "download", boom)

    pipeline.process_file("f1")  # must not raise

    assert fake_db["processing_status"] == "error"
    assert fake_db["error_message"]


def test_document_with_no_usable_content_is_an_error(fake_db, monkeypatch):
    monkeypatch.setattr(pipeline.r2, "download", lambda key: b"   \n  ")

    pipeline.process_file("f1")

    assert fake_db["processing_status"] == "error"
    assert "nội dung" in fake_db["error_message"]


def test_missing_row_is_a_no_op(fake_db, monkeypatch, caplog):
    """maybe_single().execute() returns None itself when nothing matches --
    process_file must treat that as "file was deleted before the job ran" and
    leave the row (there isn't one) alone, not crash on `.data` of `None`.

    A row that merely disappeared is a *normal* condition, not an error: no
    write of any kind should be attempted, and the generic-error branch
    (which logs at ERROR and then tries to record a failure) must not run.
    Against the naive `_load` that does `return result.data` on a bare
    `None`, `.data` raises AttributeError, which the outer `except
    Exception:` swallows and turns into exactly such an unwanted write
    attempt -- even though that attempt never matches "f1" and so leaves
    fake_db looking untouched. Asserting only on fake_db's final state can't
    tell these two cases apart; the write log and the log records can.
    """
    monkeypatch.setattr(pipeline.r2, "download", lambda key: b"unused")

    with caplog.at_level("WARNING", logger="app.ingest.pipeline"):
        pipeline.process_file("does-not-exist")  # must not raise

    assert fake_db["processing_status"] == "processing"
    assert fake_db["error_message"] is None
    assert fake_db.write_log == []
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert "no longer exists" in caplog.records[0].message


def test_update_does_not_leak_into_another_users_row(monkeypatch):
    """_update() filters on BOTH `id` and `user_id` as defence-in-depth,
    because db.admin() bypasses RLS entirely -- id alone is trusted only as
    far as the code that produced it, and this is the backstop if that trust
    is ever misplaced.

    Every other test's store holds a single row, so `id` alone already
    identifies it uniquely and an `id`-only update would look identical to a
    correctly-scoped one -- the user_id filter could be deleted and nothing
    would notice. To exercise it, this store deliberately holds two rows
    that share the same `id` but belong to different users (the kind of
    anomaly the defence-in-depth is there for). With the real `user_id`
    filter in place, only the row for the acting user ("u1") is touched. If
    that filter were dropped, the `id`-only query would match both rows and
    silently overwrite the other user's ("u2") data too.
    """
    row_u1 = {
        "id": "f1",
        "user_id": "u1",
        "file_name": "a.md",
        "file_type": "md",
        "storage_path": "u1/f1.md",
        "processing_status": "processing",
        "draft_outline": None,
        "error_message": None,
    }
    row_u2 = {
        "id": "f1",  # same id as row_u1 -- simulates an id-only-filter collision
        "user_id": "u2",
        "file_name": "b.md",
        "file_type": "md",
        "storage_path": "u2/f1.md",
        "processing_status": "processing",
        "draft_outline": None,
        "error_message": None,
    }
    store = {"row_u1": row_u1, "row_u2": row_u2}
    write_log: list[dict] = []
    client = FakeClient(store, write_log)
    monkeypatch.setattr(pipeline.db, "admin", lambda: client)
    monkeypatch.setattr(
        pipeline.r2, "download", lambda key: b"# A\nnoi dung a\n\n# B\nnoi dung b\n"
    )

    pipeline.process_file("f1")

    # The acting user's row was updated as expected.
    assert row_u1["processing_status"] == "ready_for_review"
    assert row_u1["draft_outline"] is not None

    # The other user's row -- same id, different user_id -- must be untouched.
    assert row_u2["processing_status"] == "processing"
    assert row_u2["draft_outline"] is None
    assert row_u2["error_message"] is None

    # Exactly one write was attempted, and it was scoped to u1.
    assert len(write_log) == 1
    assert write_log[0]["filters"] == {"id": "f1", "user_id": "u1"}
