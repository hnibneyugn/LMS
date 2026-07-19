"""Detect numbered headings in paragraphs that carry no heading style.

Vietnamese Word documents routinely leave every paragraph as `Normal` and
express structure through numbering alone ("Chương 1", "1.1", "I."). Without
this, such a document reaches the splitter with no heading at all and gets
hard-cut into a few oversized chunks -- and #1b's review UI deliberately has
no "split chapter" action, so an oversized chapter cannot be fixed by hand.
Cutting too finely is recoverable (the user merges); cutting too coarsely is
not. That asymmetry is why this leans towards detecting.
"""

import re

# Long enough for a real heading, short enough to exclude prose. A numbered
# list item ("1. Điều thứ nhất là...") is the main false positive this and
# the trailing-punctuation rule below are aimed at.
_MAX_HEADING_CHARS = 120
_SENTENCE_ENDINGS = (".", ",", ";", ":")

_KEYWORD = re.compile(
    r"^(chương|bài|phần|mục|chapter)\s+\d+\b",
    re.IGNORECASE,
)
_ROMAN = re.compile(r"^[IVXLC]+\.\s+\S", re.IGNORECASE)
# Captures the dotted number so its depth can set the heading level.
_DECIMAL = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")


def numbered_heading_level(text: str) -> int | None:
    """Markdown heading level (2..4) if `text` looks like a numbered heading.

    Returns None for anything else. Level 2 is the floor because real Word
    Heading styles already occupy 1..3 via docx._heading_level -- a heuristic
    hit must never outrank a genuine top-level heading and change which level
    the splitter picks as its chapter boundary.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return None
    # A heading does not end mid-sentence. This is what keeps ordinary
    # numbered list items out.
    if stripped.endswith(_SENTENCE_ENDINGS):
        return None

    if _KEYWORD.match(stripped) or _ROMAN.match(stripped):
        return 2

    decimal = _DECIMAL.match(stripped)
    if decimal:
        depth = decimal.group(1).count(".") + 1
        return min(depth + 1, 4)
    return None
