import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

# EC P-256 keypair generated once for the whole test session. Signing with
# this key and monkeypatching `_get_signing_key` to return its public key
# lets tests exercise real ES256/JWKS verification logic without any network
# call.
_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())
_PUBLIC_KEY = _PRIVATE_KEY.public_key()

USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture(autouse=True)
def auth(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example-project.supabase.co")
    monkeypatch.setattr(
        "app.dependencies.auth._get_signing_key", lambda token: _PUBLIC_KEY
    )


def auth_headers(user_id: str = USER_ID) -> dict:
    token = jwt.encode(
        {"sub": user_id, "email": "a@b.c", "aud": "authenticated"},
        _PRIVATE_KEY,
        algorithm="ES256",
    )
    return {"Authorization": f"Bearer {token}"}


class FakeTable:
    """Mimics the slice of supabase-py's fluent query builder `_Repo` and
    pipeline.py use.

    Real supabase-py chains as `table(name).select(...).eq(...).maybe_single()
    .execute()`, `table(name).update(...).eq(...).execute()` and
    `table(name).insert(...).execute()`. `.eq()`/`.neq()` can each be chained
    more than once (callers filter updates on both `id` and `user_id`), so
    filters accumulate and `execute()` applies them together against the
    store. Two behaviours matter here because production code depends on
    them:

    - `.maybe_single().execute()` returns `None` itself (not an object whose
      `.data` is `None`) when nothing matches -- see postgrest's
      `SyncMaybeSingleRequestBuilder.execute`.
    - `.update(...).execute()` returns a response whose `.data` is a *list* of
      the updated rows (representation), even though usually only one row
      matches here.
    """

    def __init__(self, store, write_log=None):
        self._store = store
        # Records every attempted write (a call to .update(...).execute()),
        # regardless of whether it actually matched a row. Tests use this to
        # tell "no write was attempted" apart from "a write was attempted but
        # happened to match nothing" -- those are very different outcomes for
        # process_file's error handling even though the store ends up
        # unchanged in both cases.
        self._write_log = write_log if write_log is not None else []
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
            self._write_log.append(
                {
                    "filters": dict(self._filters),
                    "values": dict(self._update_values),
                    "matched_ids": [row.get("id") for row in matches],
                }
            )
            for row in matches:
                row.update(self._update_values)
            return type("Res", (), {"data": [dict(row) for row in matches]})()
        if self._maybe_single:
            if not matches:
                return None
            return type("Res", (), {"data": dict(matches[0])})()
        return type("Res", (), {"data": [dict(row) for row in matches]})()


class FakeClient:
    def __init__(self, store, write_log=None):
        self._store = store
        self._write_log = write_log if write_log is not None else []

    def table(self, _name):
        return FakeTable(self._store, self._write_log)
