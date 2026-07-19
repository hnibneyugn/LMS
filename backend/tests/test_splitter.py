from app.ingest.splitter import split_into_chapters


def test_splits_on_h1_when_present():
    md = "# A\nnoi dung a\n\n# B\nnoi dung b\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.title for c in chapters] == ["A", "B"]
    assert "noi dung a" in chapters[0].content_md
    assert "noi dung b" in chapters[1].content_md


def test_falls_back_to_h2_when_no_h1():
    md = "## A\nx\n\n## B\ny\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.title for c in chapters] == ["A", "B"]


def test_deeper_headings_stay_inside_their_chapter():
    md = "# A\n## A1\nx\n### A2\ny\n\n# B\nz\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters) == 2
    assert "A1" in chapters[0].content_md
    assert "A2" in chapters[0].content_md


def test_long_preamble_becomes_its_own_chapter():
    md = "loi noi dau " * 30 + "\n\n# A\nx\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert chapters[0].title == "Mở đầu"
    assert chapters[1].title == "A"


def test_short_preamble_is_merged_into_the_first_chapter():
    md = "ngan gon\n\n# A\nx\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters) == 1
    assert chapters[0].title == "A"
    assert "ngan gon" in chapters[0].content_md


def test_document_without_any_heading_becomes_one_chapter_named_after_the_file():
    md = "chi co van ban thuan tuy, khong heading nao ca"
    chapters = split_into_chapters(md, fallback_title="giao-trinh")
    assert len(chapters) == 1
    assert chapters[0].title == "giao-trinh"


def test_empty_chapters_are_dropped():
    md = "# A\nx\n\n# Rong\n\n   \n\n# B\ny\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.title for c in chapters] == ["A", "B"]


def test_order_index_is_sequential_from_zero():
    md = "# A\nx\n\n# B\ny\n\n# C\nz\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.order_index for c in chapters] == [0, 1, 2]


def test_oversized_chapter_is_split_on_sub_headings():
    body = "chu " * 3000  # ~12000 chars, over the 8000 cap
    md = f"# A\n## A1\n{body}\n## A2\n{body}\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters) >= 2
    assert all(len(c.content_md) <= 8000 for c in chapters)


def test_oversized_chapter_without_sub_headings_is_hard_split():
    md = "# A\n" + ("mot doan van rat dai. " * 1200)
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters) >= 2
    assert all(len(c.content_md) <= 8000 for c in chapters)


def test_title_is_truncated_to_200_chars():
    md = "# " + ("t" * 300) + "\nx\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert len(chapters[0].title) == 200


def test_headings_inside_fenced_code_blocks_are_not_boundaries():
    md = "# A\n```\n# khong phai heading\n```\nx\n\n# B\ny\n"
    chapters = split_into_chapters(md, fallback_title="tai-lieu")
    assert [c.title for c in chapters] == ["A", "B"]


def test_empty_document_yields_no_chapters():
    assert split_into_chapters("   \n\n  ", fallback_title="tai-lieu") == []


def test_chapter_serialises_to_the_draft_outline_shape():
    chapters = split_into_chapters("# A\nx\n", fallback_title="tai-lieu")
    assert chapters[0].to_dict() == {
        "title": "A",
        "content_md": chapters[0].content_md,
        "order_index": 0,
    }
