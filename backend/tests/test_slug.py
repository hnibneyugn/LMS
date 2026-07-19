import pytest

from app.lessons.slug import slugify, unique_slug


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bài giảng số 1", "bai-giang-so-1"),
        ("Tiếng Việt có dấu", "tieng-viet-co-dau"),
        ("Đường lối Đảng", "duong-loi-dang"),
        ("  khoảng  trắng  thừa  ", "khoang-trang-thua"),
        ("Ký!tự@lạ#nhiều", "ky-tu-la-nhieu"),
        ("UPPER Case", "upper-case"),
        ("---đầu-cuối---", "dau-cuoi"),
    ],
)
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_slugify_returns_empty_when_nothing_survives():
    assert slugify("!!!") == ""
    assert slugify("") == ""


def test_slugify_truncates_to_80_chars():
    result = slugify("a" * 200)
    assert len(result) == 80


def test_slugify_does_not_end_with_dash_after_truncation():
    # 79 chars, then a separator, then more -- naive truncation would leave a
    # trailing dash.
    result = slugify("a" * 79 + " bcd")
    assert not result.endswith("-")


def test_unique_slug_returns_base_when_free():
    assert unique_slug("bai-1", set()) == "bai-1"


def test_unique_slug_appends_counter_when_taken():
    assert unique_slug("bai-1", {"bai-1"}) == "bai-1-2"
    assert unique_slug("bai-1", {"bai-1", "bai-1-2"}) == "bai-1-3"
