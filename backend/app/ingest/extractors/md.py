"""Markdown files: strip YAML frontmatter, keep the body verbatim."""

import frontmatter

from app.ingest.extractors.errors import ExtractError


def extract(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as err:
        raise ExtractError(
            "File markdown không đọc được — hãy lưu lại ở dạng UTF-8."
        ) from err
    try:
        post = frontmatter.loads(text)
    except Exception:
        # Malformed frontmatter is not worth failing over — keep the raw text.
        return text.strip()
    return post.content.strip()
