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
# Deliberately case-sensitive (no re.IGNORECASE) and restricted to I/V/X --
# NOT the full Roman alphabet. Character-class membership alone can't tell a
# Roman-numeral heading from an ordinary word: "CLI" and "XL" are both
# well-formed Roman numerals (151 and 40) yet also a common abbreviation
# ("CLI. Cong cu...") and a clothing size ("XL. Kich thuoc lon"), and validating
# stricter Roman-numeral grammar wouldn't change that -- they'd still parse.
# What actually discriminates a real heading here is that section numbers are
# small and headings are uppercase. Dropping L/C/D/M caps what this can match
# at "XXXIX" (39) and dropping IGNORECASE rejects mixed-case words like
# "Civic."; combined with the length cap below this only recognises I..XX or
# so, which is every Roman-numbered chapter/section seen in practice. The
# tradeoff: a document that genuinely numbers a section "L" or higher in
# Roman numerals won't be detected -- accepted, because that doesn't occur in
# personal study documents.
_ROMAN = re.compile(r"^[IVX]{1,4}\.\s+\S")
# Captures the dotted number so its depth can set the heading level.
_DECIMAL = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")


def numbered_heading_level(text: str) -> int | None:
    """Markdown heading level (2..4) if `text` looks like a numbered heading.

    Returns None for anything else. Level 2 is the floor because real Word
    Heading styles already occupy 1..3 via docx._heading_level -- a heuristic
    hit is guaranteed to never outrank a genuine `Heading 1` (markdown `#`),
    since level 1 is never returned here. That guarantee does NOT extend to
    every real heading: in a document whose only heading style in use is
    `Heading 3` (markdown `###`), a heuristic level-2 hit is shallower and
    becomes the splitter's chapter boundary instead. This is accepted --
    such a document has no level-1/2 heading for the heuristic to lose to.
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
