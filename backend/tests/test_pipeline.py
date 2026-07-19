import pytest

from app.ingest import pipeline


class _FakeTable:
    """Mimics the slice of supabase-py's fluent query builder pipeline.py uses.

    Real supabase-py chains as `table(name).select(...).eq(...).maybe_single()
    .execute()` and `table(name).update(...).eq(...).execute()`. `.eq()` can be
    chained more than once (pipeline.py filters updates on both `id` and
    `user_id`), so filters accumulate and `execute()` applies them against the
    store. Two behaviours matter here because pipeline.py depends on them:

    - `.maybe_single().execute()` returns `None` itself (not an object whose
      `.data` is `None`) when nothing matches -- see postgrest's
      `SyncMaybeSingleRequestBuilder.execute`.
    - `.update(...).execute()` returns a response whose `.data` is a *list* of
      the updated rows (representation), even though only one row matches here.
    """

    def __init__(self, store):
        self._store = store
        self._filters: dict[str, object] = {}
        self._update_values: dict | None = None
        self._maybe_single = False

    def select(self, *_columns):
        return self

    def update(self, values):
        self._update_values = values
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def _matches(self):
        return [
            row
            for row in self._store.values()
            if all(row.get(k) == v for k, v in self._filters.items())
        ]

    def execute(self):
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
def fake_db(monkeypatch):
    row = {
        "id": "f1",
        "user_id": "u1",
        "file_name": "giao-trinh.md",
        "file_type": "md",
        "storage_path": "u1/f1.md",
        "processing_status": "processing",
        "draft_outline": None,
        "error_message": None,
    }
    store = {"f1": row}
    client = _FakeClient(store)
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


def test_missing_row_is_a_no_op(fake_db, monkeypatch):
    """maybe_single().execute() returns None itself when nothing matches --
    process_file must treat that as "file was deleted before the job ran" and
    leave the row (there isn't one) alone, not crash on `.data` of `None`.
    """
    monkeypatch.setattr(pipeline.r2, "download", lambda key: b"unused")

    pipeline.process_file("does-not-exist")  # must not raise

    assert fake_db["processing_status"] == "processing"
