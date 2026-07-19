"""Background job: R2 object -> markdown -> chapters -> draft_outline.

Runs inside the API process via FastAPI BackgroundTasks (D4 — under 10 users
does not justify a queue). Nothing here may raise: a failure must land in the
row as an actionable Vietnamese message so #1b can offer a retry.
"""

import logging
from pathlib import Path

from app import db
from app.ingest.extractors import EXTRACTORS, ExtractError
from app.ingest.splitter import split_into_chapters
from app.storage import r2

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Xử lý file thất bại do lỗi hệ thống. Hãy thử lại sau ít phút."
EMPTY_ERROR = "Không trích xuất được nội dung nào từ file này."


def process_file(file_id: str) -> None:
    row: dict | None = None
    try:
        row = _load(file_id)
        if row is None:
            logger.warning("process_file: %s no longer exists", file_id)
            return

        data = r2.download(row["storage_path"])
        raw_md = EXTRACTORS[row["file_type"]](data)

        fallback = Path(row["file_name"]).stem
        chapters = split_into_chapters(raw_md, fallback_title=fallback)
        if not chapters:
            _fail(file_id, row["user_id"], EMPTY_ERROR)
            return

        _finish(file_id, row["user_id"], [chapter.to_dict() for chapter in chapters])
    except ExtractError as err:
        _fail(file_id, row["user_id"] if row else None, str(err))
    except Exception:
        # Anything unexpected (network, R2, DB) — log the detail for us, show
        # the user something generic rather than a stack trace.
        logger.exception("process_file failed for %s", file_id)
        _fail(file_id, row["user_id"] if row else None, GENERIC_ERROR)


def _load(file_id: str) -> dict | None:
    result = (
        db.admin()
        .table("user_files")
        .select("id, user_id, file_name, file_type, storage_path")
        .eq("id", file_id)
        .maybe_single()
        .execute()
    )
    # supabase-py's maybe_single().execute() returns None itself (not an
    # object whose .data is None) when zero rows match.
    return result.data if result is not None else None


def _finish(file_id: str, user_id: str, outline: list[dict]) -> None:
    _update(
        file_id,
        user_id,
        {
            "processing_status": "ready_for_review",
            "draft_outline": outline,
            "error_message": None,
        },
    )


def _fail(file_id: str, user_id: str | None, message: str) -> None:
    try:
        _update(file_id, user_id, {"processing_status": "error", "error_message": message})
    except Exception:
        # If even the failure write fails the row stays 'processing'; #1b's
        # stuck-file retry button is the backstop.
        logger.exception("could not record failure for %s", file_id)


def _update(file_id: str, user_id: str | None, values: dict) -> None:
    # This client bypasses RLS (service role), so every query filters on
    # user_id explicitly wherever it is known. It is only unknown here if the
    # initial row load itself failed (e.g. a DB error), in which case the
    # id filter alone is the best we can do.
    query = db.admin().table("user_files").update(values).eq("id", file_id)
    if user_id is not None:
        query = query.eq("user_id", user_id)
    query.execute()
