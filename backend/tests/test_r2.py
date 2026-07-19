"""object_exists must distinguish "not there" from "storage is broken"."""

import pytest
from botocore.exceptions import ClientError

from app.storage import r2


class _FakeClient:
    exceptions = type("Exceptions", (), {"ClientError": ClientError})

    def __init__(self, error: ClientError | None):
        self._error = error
        self.calls: list[dict] = []

    def head_object(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return {}


def _client_error(status_code: int, code: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        "HeadObject",
    )


@pytest.fixture
def use_fake(monkeypatch):
    monkeypatch.setenv("R2_BUCKET", "test-bucket")

    def install(error: ClientError | None) -> _FakeClient:
        fake = _FakeClient(error)
        monkeypatch.setattr(r2, "_client", lambda: fake)
        return fake

    return install


def test_present_object_returns_true(use_fake):
    fake = use_fake(None)
    assert r2.object_exists("u1/f1.pdf") is True
    assert fake.calls == [{"Bucket": "test-bucket", "Key": "u1/f1.pdf"}]


def test_missing_object_returns_false(use_fake):
    use_fake(_client_error(404, "404"))
    assert r2.object_exists("u1/missing.pdf") is False


def test_permission_error_is_raised_not_reported_as_missing(use_fake):
    use_fake(_client_error(403, "AccessDenied"))
    with pytest.raises(ClientError):
        r2.object_exists("u1/f1.pdf")


def test_server_error_is_raised_not_reported_as_missing(use_fake):
    use_fake(_client_error(500, "InternalError"))
    with pytest.raises(ClientError):
        r2.object_exists("u1/f1.pdf")
