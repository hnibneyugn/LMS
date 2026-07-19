import io

import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from pptx import Presentation
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.ingest.extractors import EXTRACTORS, ExtractError
from app.ingest.extractors import md as md_extractor
from app.ingest.extractors import pdf as pdf_extractor
from app.ingest.splitter import split_into_chapters


def test_registry_covers_all_four_formats():
    assert set(EXTRACTORS) == {"md", "docx", "pptx", "pdf"}


def test_md_keeps_the_body_and_drops_frontmatter():
    raw = b"---\ntitle: Bai 1\n---\n\n# Chuong 1\nnoi dung\n"
    result = md_extractor.extract(raw)
    assert "# Chuong 1" in result
    assert "title: Bai 1" not in result


def test_md_without_frontmatter_is_unchanged():
    raw = b"# Chuong 1\nnoi dung\n"
    assert md_extractor.extract(raw).strip() == "# Chuong 1\nnoi dung"


def test_docx_maps_headings_and_lists_to_markdown():
    document = Document()
    document.add_heading("Chuong mot", level=1)
    document.add_paragraph("doan van thuong")
    document.add_paragraph("mot muc", style="List Bullet")
    document.add_heading("Muc con", level=2)
    buffer = io.BytesIO()
    document.save(buffer)

    result = EXTRACTORS["docx"](buffer.getvalue())
    assert "# Chuong mot" in result
    assert "## Muc con" in result
    assert "- mot muc" in result
    assert "doan van thuong" in result


def test_docx_custom_style_based_on_builtin_heading_is_recognised():
    """A style with a localized/custom display name (e.g. a Vietnamese Word
    template's "Tieu de 1") that is *based on* the built-in "Heading 2"
    style must still be detected as a level-2 heading -- matching only the
    English display name would silently drop the document's structure."""
    document = Document()
    custom_style = document.styles.add_style("Tieu de 1", WD_STYLE_TYPE.PARAGRAPH)
    custom_style.base_style = document.styles["Heading 2"]
    paragraph = document.add_paragraph("Tieu de tuy chinh")
    paragraph.style = custom_style
    buffer = io.BytesIO()
    document.save(buffer)

    result = EXTRACTORS["docx"](buffer.getvalue())
    assert "## Tieu de tuy chinh" in result


def test_pptx_turns_each_slide_into_an_h2():
    presentation = Presentation()
    for title_text in ("Slide mot", "Slide hai"):
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = title_text
        slide.placeholders[1].text = f"noi dung {title_text}"
    buffer = io.BytesIO()
    presentation.save(buffer)

    result = EXTRACTORS["pptx"](buffer.getvalue())
    assert "## Slide mot" in result
    assert "## Slide hai" in result
    assert "noi dung Slide hai" in result


def test_pdf_without_text_layer_raises_a_vietnamese_error():
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(ExtractError) as err:
        pdf_extractor.extract(buffer.getvalue())
    assert "không có văn bản" in str(err.value)


def _pdf_with_text_pages(page_texts: list[str], outline: list[tuple[int, str]] | None = None) -> bytes:
    """Build a real in-memory PDF whose pages carry an actual extractable
    text layer, optionally with top-level outline (bookmark) entries.

    pypdf is a manipulation library, not a generator: `PdfWriter` has no
    public API to draw text into a page, only `add_blank_page`. To get a
    page pypdf's own `extract_text()` can read back, this hand-assembles the
    minimal PDF content stream ("BT ... Tj ET") plus the Type1/Helvetica
    font resource every page needs, using pypdf's internal `_add_object` --
    there is no public alternative for this and no other project dependency
    can generate PDF bytes, so this is the smallest honest way to produce a
    PDF with a genuine text layer without a binary fixture.
    """
    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=200, height=200)
        content = f"BT /F1 24 Tf 10 100 Td ({text}) Tj ET".encode("latin-1")
        stream = DecodedStreamObject()
        stream.set_data(content)
        stream_ref = writer._add_object(stream)

        font = DictionaryObject()
        font[NameObject("/Type")] = NameObject("/Font")
        font[NameObject("/Subtype")] = NameObject("/Type1")
        font[NameObject("/BaseFont")] = NameObject("/Helvetica")
        font_ref = writer._add_object(font)

        resources = DictionaryObject()
        font_dict = DictionaryObject()
        font_dict[NameObject("/F1")] = font_ref
        resources[NameObject("/Font")] = font_dict

        page[NameObject("/Contents")] = stream_ref
        page[NameObject("/Resources")] = resources

    for page_index, title in outline or []:
        writer.add_outline_item(title, page_index)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_pdf_outline_bookmarks_produce_one_h2_per_top_level_bookmark():
    page_texts = [
        "Page zero body text for the outline mapping fixture.",
        "Page one body text with no bookmark of its own.",
        "Page two body text starting a brand new chapter.",
    ]
    pdf_bytes = _pdf_with_text_pages(
        page_texts, outline=[(0, "Chuong mot"), (2, "Chuong ba")]
    )

    result = pdf_extractor.extract(pdf_bytes)

    assert "## Chuong mot" in result
    assert "## Chuong ba" in result
    # The bookmark heading lands right before the page it points at, and the
    # un-bookmarked middle page stays inside the first chapter rather than
    # getting a heading of its own.
    chuong_mot_at = result.index("## Chuong mot")
    chuong_ba_at = result.index("## Chuong ba")
    assert chuong_mot_at < result.index(page_texts[0]) < chuong_ba_at
    assert chuong_mot_at < result.index(page_texts[1]) < chuong_ba_at
    assert chuong_ba_at < result.index(page_texts[2])


def test_pdf_without_outline_gets_a_phan_n_heading_every_ten_pages():
    page_texts = [f"Filler body text for page number {i}." for i in range(25)]
    pdf_bytes = _pdf_with_text_pages(page_texts)

    result = pdf_extractor.extract(pdf_bytes)

    assert "## Phần 1" in result
    assert "## Phần 2" in result
    assert "## Phần 3" in result
    assert "## Phần 4" not in result


def test_pdf_extractor_output_splits_into_more_than_one_chapter():
    """The contract that actually matters: whatever headings the PDF
    extractor injects (from bookmarks, or from the page-stride fallback)
    must be enough for the splitter to cut the document into multiple
    chapters instead of collapsing it into one giant unusable block."""
    with_outline = pdf_extractor.extract(
        _pdf_with_text_pages(
            [
                "Page zero body text for the outline mapping fixture.",
                "Page one body text with no bookmark of its own.",
                "Page two body text starting a brand new chapter.",
            ],
            outline=[(0, "Chuong mot"), (2, "Chuong ba")],
        )
    )
    without_outline = pdf_extractor.extract(
        _pdf_with_text_pages([f"Filler body text for page number {i}." for i in range(25)])
    )

    assert len(split_into_chapters(with_outline, "fallback")) > 1
    assert len(split_into_chapters(without_outline, "fallback")) > 1


def test_corrupt_bytes_raise_extract_error_not_a_library_exception():
    for file_type in ("docx", "pptx", "pdf"):
        with pytest.raises(ExtractError):
            EXTRACTORS[file_type](b"day khong phai file hop le")


# --- stray '#' in body text must not fabricate heading boundaries ------------
#
# Slides, PDFs, and DOCX bodies routinely contain shell/Python snippets
# ("# comment") or other lines that happen to start with '#'. The splitter's
# only rule is "cut on the shallowest heading level present" -- one such body
# line at level 1 would outrank every deliberately injected '## ...' boundary
# and collapse the whole document into a single chapter. The extractors must
# neutralise accidental leading '#' in body text they did NOT turn into a
# heading themselves.


def test_pptx_body_text_with_a_leading_hash_does_not_collapse_the_document():
    presentation = Presentation()
    bodies = ("noi dung binh thuong", "# not a real heading\nnoi dung tiep theo")
    for title_text, body_text in zip(("Slide mot", "Slide hai"), bodies):
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = title_text
        slide.placeholders[1].text = body_text
    buffer = io.BytesIO()
    presentation.save(buffer)

    result = EXTRACTORS["pptx"](buffer.getvalue())
    chapters = split_into_chapters(result, fallback_title="tai-lieu")

    assert [c.title for c in chapters] == ["Slide mot", "Slide hai"]
    # The stray '#' must still be readable in the rendered body, just not as
    # a heading marker.
    assert "not a real heading" in chapters[1].content_md


def test_pdf_body_text_with_a_leading_hash_does_not_collapse_the_document():
    page_texts = [
        "Trang mot noi dung binh thuong day du de vuot qua nguong toi thieu can thiet.",
        "# khong phai heading that",
        "Trang ba noi dung tiep theo cung day du de vuot qua nguong toi thieu can thiet.",
    ]
    pdf_bytes = _pdf_with_text_pages(
        page_texts, outline=[(0, "Phan mot"), (2, "Phan hai")]
    )

    result = pdf_extractor.extract(pdf_bytes)
    chapters = split_into_chapters(result, fallback_title="tai-lieu")

    assert [c.title for c in chapters] == ["Phan mot", "Phan hai"]
    assert "khong phai heading that" in chapters[0].content_md


def test_docx_body_text_with_a_leading_hash_does_not_collapse_the_document():
    document = Document()
    document.add_heading("Chuong mot", level=2)
    document.add_paragraph("noi dung mot")
    document.add_heading("Chuong hai", level=2)
    document.add_paragraph("# khong phai heading that")
    document.add_paragraph("noi dung hai")
    buffer = io.BytesIO()
    document.save(buffer)

    result = EXTRACTORS["docx"](buffer.getvalue())
    chapters = split_into_chapters(result, fallback_title="tai-lieu")

    assert [c.title for c in chapters] == ["Chuong mot", "Chuong hai"]
    assert "khong phai heading that" in chapters[1].content_md
