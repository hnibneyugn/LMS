import pytest

from app.ingest.extractors._numbering import numbered_heading_level


@pytest.mark.parametrize(
    "text",
    [
        "Chương 1 Tổng quan",
        "Chương 12: Kết luận",
        "Bài 3 Câu điều kiện",
        "Phần 2 — Ứng dụng",
        "Mục 4 Thực hành",
        "Chapter 5 Overview",
        "I. Mở đầu",
        "IV. Tổng kết",
    ],
)
def test_word_and_roman_patterns_are_level_two(text):
    assert numbered_heading_level(text) == 2


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1. Giới thiệu", 2),
        ("2 Giới thiệu", 2),
        ("1.1 Bối cảnh", 3),
        ("1.1. Bối cảnh", 3),
        ("1.1.1 Chi tiết", 4),
        ("1.1.1.1 Sâu hơn", 4),  # clamped: markdown level never exceeds 4
    ],
)
def test_decimal_depth_maps_to_heading_level(text, expected):
    assert numbered_heading_level(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Đoạn văn bình thường không đánh số.",
        "1. Điều thứ nhất là phải giữ cho câu này kết thúc bằng dấu chấm.",
        "2. Tiếp theo,",
        "3. Sau đó;",
        "4. Cuối cùng:",
        "",
        "   ",
        "Chương",  # keyword with no number
        "Chapter",
        "1234",  # a bare number is not a heading
    ],
)
def test_non_headings_return_none(text):
    assert numbered_heading_level(text) is None


def test_long_line_is_not_a_heading():
    assert numbered_heading_level("Chương 1 " + "x" * 200) is None


def test_leading_and_trailing_space_is_tolerated():
    assert numbered_heading_level("  Chương 1 Tổng quan  ") == 2
