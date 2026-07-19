"""PDF: text layer only (no OCR).

The PDF is the one format that carries structure the splitter cannot see, so
this extractor injects '## ' headings itself — from the document outline when
there is one, otherwise every PAGES_PER_CHAPTER pages.
"""

import io

from pypdf import PdfReader

from app.ingest.extractors.errors import ExtractError

PAGES_PER_CHAPTER = 10
MIN_USABLE_CHARS = 100


def extract(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as err:
        raise ExtractError(
            "Không mở được file .pdf — file có thể hỏng hoặc được đặt mật khẩu."
        ) from err

    if sum(len(text) for text in pages) < MIN_USABLE_CHARS:
        raise ExtractError(
            "File PDF này không có văn bản (có thể là bản scan/ảnh). "
            "Hãy dùng bản PDF có text, hoặc chuyển sang .docx rồi tải lại."
        )

    titles = _outline_titles(reader, len(pages))
    parts: list[str] = []
    for index, text in enumerate(pages):
        if index in titles:
            parts.append(f"## {titles[index]}")
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _outline_titles(reader: PdfReader, page_count: int) -> dict[int, str]:
    """Map page index -> chapter heading, from bookmarks or a fixed page stride."""
    titles: dict[int, str] = {}
    try:
        for item in reader.outline or []:
            # Nested outline levels come through as lists; only top level is used.
            if isinstance(item, list):
                continue
            page_index = reader.get_page_number(item.page)
            titles.setdefault(page_index, str(item.title).strip())
    except Exception:
        # A broken outline must not sink an otherwise readable PDF.
        titles = {}

    if titles:
        return titles
    return {
        index: f"Phần {index // PAGES_PER_CHAPTER + 1}"
        for index in range(0, page_count, PAGES_PER_CHAPTER)
    }
