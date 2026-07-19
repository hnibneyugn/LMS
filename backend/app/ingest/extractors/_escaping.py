"""Shared helper: keep accidental '#' in extracted body text from being
read by the splitter as a heading boundary.

The splitter's only rule is "cut on the shallowest markdown heading level
present in the document" (see app.ingest.splitter). PDF/PPTX/DOCX extractors
deliberately inject '#'..'###' headings to express source structure the
splitter cannot otherwise see, so any OTHER line that happens to start with
'#' -- a shell/Python comment, a shebang, a chat transcript -- would be
misread as a heading of its own and could outrank every deliberate boundary,
collapsing the whole document into one chapter. This is NOT used by
md.py: a .md upload is genuine markdown, where a leading '#' really is a
heading and must stay one.
"""


def escape_accidental_headings(text: str) -> str:
    """Escape a leading '#' on every line of `text` as '\\#'.

    Only lines that literally start with '#' are touched -- markdown escaping
    keeps the character visible when the chapter is later rendered, which is
    better than silently dropping it. Callers must only pass body text they
    did NOT deliberately turn into a heading; headings the extractor injects
    itself (e.g. f"## {title}") must never go through this function.
    """
    return "\n".join(
        f"\\{line}" if line.startswith("#") else line for line in text.split("\n")
    )
