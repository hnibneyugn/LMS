"""DOCX: headings 1-3 become #/##/###, bullets become '-', rest stays prose."""

import io
import re

from docx import Document

from app.ingest.extractors.errors import ExtractError

_STYLE_ID_HEADING = re.compile(r"^heading(\d+)$")
# Guards against a corrupt/cyclic base_style chain -- Word doesn't nest
# styles this deep in practice, so hitting this is proof of a cycle, not a
# legitimately deep template.
_MAX_STYLE_DEPTH = 20


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
        level = _heading_level(paragraph.style)
        if level is not None:
            parts.append(f"{'#' * level} {text}")
        elif "list" in (paragraph.style.name or "").lower():
            parts.append(f"- {text}")
        else:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _heading_level(style) -> int | None:
    """Return the heading level 1..3 for `style`, or None if it isn't one.

    Detection has to be locale-independent: a Vietnamese Word install (or a
    custom template) can carry heading styles under a localized or fully
    custom display name -- e.g. a style named "Tieu de 1" that is *based on*
    the built-in "Heading 2" style rather than named "Heading" at all.
    python-docx exposes two signals that survive that:
      - `style.style_id`, which for built-in heading styles stays the fixed
        English token ("Heading1".."Heading9") no matter the UI language;
      - `style.base_style`, which lets a custom style be walked up to the
        built-in style it derives from, inheriting that style's level.
    The plain English display-name check ("heading 2") is kept as a third
    signal, for styles that happen to carry that name without a `base_style`
    link to a built-in heading style.
    """
    seen_ids: set[int] = set()
    current = style
    depth = 0
    while current is not None and depth < _MAX_STYLE_DEPTH and id(current) not in seen_ids:
        seen_ids.add(id(current))
        depth += 1
        level = _level_from_style_id(getattr(current, "style_id", None))
        if level is None:
            level = _level_from_name(getattr(current, "name", None))
        if level is not None:
            return level
        current = getattr(current, "base_style", None)
    return None


def _level_from_style_id(style_id: str | None) -> int | None:
    match = _STYLE_ID_HEADING.match((style_id or "").lower())
    if not match:
        return None
    return min(max(int(match.group(1)), 1), 3)


def _level_from_name(style_name: str | None) -> int | None:
    """'heading 2' -> 2, clamped to 1..3 as the spec only maps three levels."""
    name = (style_name or "").lower()
    if not name.startswith("heading"):
        return None
    tail = name.replace("heading", "").strip()
    try:
        return min(max(int(tail), 1), 3)
    except ValueError:
        return 1
