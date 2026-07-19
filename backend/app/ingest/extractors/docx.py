"""DOCX: headings 1-3 become #/##/###, bullets become '-', rest stays prose."""

import io

from docx import Document

from app.ingest.extractors.errors import ExtractError


def extract(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
    except Exception as err:
        raise ExtractError(
            "Không mở được file .docx — file có thể hỏng hoặc không đúng định dạng."
        ) from err

    parts: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower()
        if style.startswith("heading"):
            level = _heading_level(style)
            parts.append(f"{'#' * level} {text}")
        elif "list" in style:
            parts.append(f"- {text}")
        else:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _heading_level(style_name: str) -> int:
    """'heading 2' -> 2, clamped to 1..3 as the spec only maps three levels."""
    tail = style_name.replace("heading", "").strip()
    try:
        return min(max(int(tail), 1), 3)
    except ValueError:
        return 1
