"""Cut a markdown document into chapter-sized pieces.

Pure markdown in, chapters out — no knowledge of the source format. Format
specific structure (PDF page breaks, PPTX slides) is turned into headings by
the extractors before the text reaches here, so there is exactly one rule.
"""

import re

from app.config.settings import MAX_CHAPTER_CHARS
from app.ingest.chapter import Chapter

MAX_TITLE_CHARS = 200
MIN_PREAMBLE_CHARS = 200
PREAMBLE_TITLE = "Mở đầu"

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def _fences_balanced(lines: list[str]) -> bool:
    """Whether every ``` / ~~~ fence marker in `lines` has a matching partner.

    Each fence line simply flips an open/closed flag, so a balanced document
    has an even number of fence markers.
    """
    return sum(1 for line in lines if _FENCE.match(line)) % 2 == 0


def _heading_lines(lines: list[str], track_fences: bool = True) -> list[tuple[int, int, str]]:
    """Return (line_index, level, text) for headings outside fenced code.

    `track_fences` is set to False by callers when the document's fences are
    unbalanced (see `split_into_chapters`) so an unclosed fence can't latch
    "inside code" for the rest of the document and hide every later heading.
    """
    found: list[tuple[int, int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        if track_fences and _FENCE.match(line):
            in_fence = not in_fence
            continue
        if track_fences and in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            found.append((index, len(match.group(1)), match.group(2).strip()))
    return found


def _sections(
    lines: list[str], level: int, track_fences: bool = True
) -> list[tuple[str, list[str]]]:
    """Split `lines` at headings of exactly `level`.

    Returns (title, body_lines) pairs. Text before the first heading comes back
    with the sentinel title "" so the caller can decide what to do with it.
    """
    boundaries = [i for i, lvl, _ in _heading_lines(lines, track_fences) if lvl == level]
    titles = {i: text for i, lvl, text in _heading_lines(lines, track_fences) if lvl == level}

    sections: list[tuple[str, list[str]]] = []
    preamble_end = boundaries[0] if boundaries else len(lines)
    sections.append(("", lines[:preamble_end]))

    for position, start in enumerate(boundaries):
        end = boundaries[position + 1] if position + 1 < len(boundaries) else len(lines)
        sections.append((titles[start], lines[start + 1 : end]))
    return sections


def _hard_split(text: str) -> list[str]:
    """Last resort: pack paragraphs into <= MAX_CHAPTER_CHARS pieces."""
    pieces: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= MAX_CHAPTER_CHARS:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        # A single paragraph can still be too long — chop it on the char cap.
        while len(paragraph) > MAX_CHAPTER_CHARS:
            pieces.append(paragraph[:MAX_CHAPTER_CHARS])
            paragraph = paragraph[MAX_CHAPTER_CHARS:]
        current = paragraph
    if current.strip():
        pieces.append(current)
    return pieces


def _numbered_label(title: str, n: int) -> str:
    """Build a "<title> (<n>)" label that never exceeds MAX_TITLE_CHARS.

    `title` may already be at the cap, so the suffix is reserved first and
    the title is trimmed to make room for it -- truncation must never eat
    into the suffix, or callers lose the only thing telling pieces apart.
    """
    suffix = f" ({n})"
    room_for_title = max(0, MAX_TITLE_CHARS - len(suffix))
    return f"{title[:room_for_title]}{suffix}"[:MAX_TITLE_CHARS]


def _shrink(
    title: str, body: str, level: int, track_fences: bool = True
) -> list[tuple[str, str]]:
    """Break an oversized chapter down until every piece fits the cap."""
    if len(body) <= MAX_CHAPTER_CHARS:
        return [(title, body)]

    lines = body.splitlines()
    deeper = [lvl for _, lvl, _ in _heading_lines(lines, track_fences) if lvl > level]
    if deeper:
        next_level = min(deeper)
        result: list[tuple[str, str]] = []
        for sub_title, sub_lines in _sections(lines, next_level, track_fences):
            sub_body = "\n".join(sub_lines).strip()
            if not sub_body:
                continue
            label = sub_title[:MAX_TITLE_CHARS] if sub_title else title
            result.extend(_shrink(label, sub_body, next_level, track_fences))
        if result:
            return result

    return [
        (_numbered_label(title, n + 1), piece)
        for n, piece in enumerate(_hard_split(body))
    ]


def split_into_chapters(md: str, fallback_title: str) -> list[Chapter]:
    if not md.strip():
        return []

    lines = md.splitlines()
    # This module is fed by DOCX/PPTX/PDF extraction, not hand-written
    # markdown, so a fence opened but never closed is a realistic failure
    # mode. If we kept tracking fence state regardless, "inside code" would
    # latch true for the rest of the document and every later heading would
    # be swallowed as body text of one giant chapter. Per the project's
    # graceful-degradation principle, a malformed input should degrade to a
    # usable (if imperfectly split) result rather than lose all structure --
    # mis-splitting inside a stray fence is far less damaging than that, and
    # the user reviews/corrects the chapter list afterwards anyway. So: only
    # trust fence tracking when the fences in the document are balanced.
    track_fences = _fences_balanced(lines)
    levels = [lvl for _, lvl, _ in _heading_lines(lines, track_fences)]
    if not levels:
        pairs = [(fallback_title[:MAX_TITLE_CHARS], md.strip())]
        return _to_chapters(pairs)

    top_level = min(levels)
    sections = _sections(lines, top_level, track_fences)

    pairs: list[tuple[str, str]] = []
    preamble = "\n".join(sections[0][1]).strip()
    rest = sections[1:]

    if preamble and len(preamble) >= MIN_PREAMBLE_CHARS:
        pairs.append((PREAMBLE_TITLE, preamble))
        preamble = ""

    for position, (title, body_lines) in enumerate(rest):
        body = "\n".join(body_lines).strip()
        # A short preamble is glued onto the first real chapter instead of
        # becoming a stub of its own.
        if position == 0 and preamble:
            body = f"{preamble}\n\n{body}".strip()
        if not body:
            continue
        pairs.append((title[:MAX_TITLE_CHARS], body))

    expanded: list[tuple[str, str]] = []
    for title, body in pairs:
        expanded.extend(_shrink(title, body, top_level, track_fences))
    return _to_chapters(expanded)


def _to_chapters(pairs: list[tuple[str, str]]) -> list[Chapter]:
    return [
        Chapter(title=title, content_md=body, order_index=index)
        for index, (title, body) in enumerate(
            (t, b) for t, b in pairs if b.strip()
        )
    ]
