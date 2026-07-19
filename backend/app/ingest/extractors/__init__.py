from collections.abc import Callable

from app.ingest.extractors import docx, md, pdf, pptx
from app.ingest.extractors.errors import ExtractError

EXTRACTORS: dict[str, Callable[[bytes], str]] = {
    "md": md.extract,
    "docx": docx.extract,
    "pptx": pptx.extract,
    "pdf": pdf.extract,
}

__all__ = ["EXTRACTORS", "ExtractError"]
