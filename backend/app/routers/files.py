"""File upload lifecycle: presign -> (browser PUTs to R2) -> process -> poll."""

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app import db
from app.config import settings
from app.dependencies.auth import CurrentUser, get_current_user
from app.ingest import pipeline
from app.lessons.slug import slugify, unique_slug
from app.storage import r2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

FileType = Literal["md", "docx", "pptx", "pdf"]


class PresignRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_type: FileType
    file_size: int = Field(gt=0)


class PresignResponse(BaseModel):
    file_id: str
    upload_url: str
    storage_path: str


class ConfirmChapter(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    source_indexes: list[int] = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def _trim_title(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Tiêu đề chương không được để trống.")
        return trimmed


class ConfirmRequest(BaseModel):
    chapters: list[ConfirmChapter] = Field(min_length=1)


class ConfirmResponse(BaseModel):
    lesson_count: int


# Every status other than ready_for_review is a 409 with its own explanation.
_CONFIRM_BLOCKED = {
    "pending": "File chưa xử lý xong.",
    "processing": "File chưa xử lý xong.",
    "error": "File xử lý lỗi — hãy xử lý lại trước khi duyệt.",
    "done": "File đã được duyệt.",
}


class _Repo:
    """Thin data layer. Isolated in a class so tests can swap it wholesale.

    Uses the service-role client, which bypasses RLS — every read here filters
    on user_id explicitly.
    """

    def insert_file(self, values: dict) -> None:
        db.admin().table("user_files").insert(values).execute()

    def get_file(self, file_id: str, user_id: str) -> dict | None:
        result = (
            db.admin()
            .table("user_files")
            .select("*")
            .eq("id", file_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result is not None else None

    def list_files(self, user_id: str) -> list[dict]:
        result = (
            db.admin()
            .table("user_files")
            .select("*")
            .eq("user_id", user_id)
            .order("uploaded_at", desc=True)
            .execute()
        )
        return result.data or []

    def set_status(
        self,
        file_id: str,
        user_id: str,
        status_value: str,
        error_message: str | None = None,
    ) -> None:
        """Update processing_status, and error_message alongside it whenever
        the caller passes one -- callers that report a failure must set both
        in the same write, or the row would show a status and a message from
        two different runs. `error_message` defaults to None (meaning "leave
        it untouched") rather than always being written, so plain status
        transitions that carry no message of their own (there are none left
        that report failure, but the parameter must not force every caller
        to pass one) don't clobber an existing value they know nothing about.
        """
        values: dict = {"processing_status": status_value}
        if error_message is not None:
            values["error_message"] = error_message
        db.admin().table("user_files").update(values).eq("id", file_id).eq(
            "user_id", user_id
        ).execute()

    def claim_for_processing(self, file_id: str, user_id: str) -> list[dict]:
        """Atomically transition a row to 'processing', but only if it is not
        already 'processing'.

        This is a single conditional UPDATE rather than a read-then-write, so
        it is atomic in Postgres: two concurrent calls for the same file_id
        can both pass a prior "is it already processing?" read, but only one
        of them will actually match this UPDATE's WHERE clause and flip the
        status, because the second one runs after the first has committed.
        The caller must have already confirmed the row exists and belongs to
        user_id (e.g. via get_file) to tell 404 apart from "lost the race":
        an empty result here means "already processing", not "not found".

        Also clears error_message: a claimed row is starting a fresh
        processing attempt, and a retry must not carry the previous run's
        error text into the new attempt's `processing` window (or into
        `error` again if the new attempt happens to fail before writing its
        own message).
        """
        result = (
            db.admin()
            .table("user_files")
            .update({"processing_status": "processing", "error_message": None})
            .eq("id", file_id)
            .eq("user_id", user_id)
            .neq("processing_status", "processing")
            .execute()
        )
        return result.data or []

    def insert_lessons(self, rows: list[dict]) -> None:
        """Insert every lesson of a confirmed file in one call.

        One batched insert rather than a loop: supabase-py has no transaction
        handle here, so a loop that fails halfway would leave a partially
        confirmed file behind. A single insert either lands whole or not at all.
        """
        db.admin().table("lessons").insert(rows).execute()

    def list_lesson_slugs(self, user_id: str) -> list[str]:
        result = (
            db.admin().table("lessons").select("slug").eq("user_id", user_id).execute()
        )
        return [row["slug"] for row in (result.data or [])]


repo = _Repo()


def _validate_source_indexes(
    chapters: list[ConfirmChapter], outline_length: int
) -> None:
    """Raise 400 if the requested chapter layout is not expressible in the UI.

    The rules mirror exactly what the review page can produce: merge only
    joins adjacent chapters, and a draft chapter is either used once or
    dropped. Anything else means a hand-crafted request, and accepting it
    would let content be duplicated or reordered in ways the user never saw.
    """
    seen: set[int] = set()
    for chapter in chapters:
        indexes = chapter.source_indexes
        for index in indexes:
            if not 0 <= index < outline_length:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Danh sách chương không hợp lệ.",
                )
            if index in seen:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Một chương gốc không thể nằm trong hai bài học.",
                )
            seen.add(index)
        if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chỉ gộp được các chương liền kề.",
            )


def _build_lesson_rows(
    chapters: list[ConfirmChapter],
    outline: list[dict],
    file_name: str,
    file_id: str,
    user_id: str,
    taken_slugs: set[str],
) -> list[dict]:
    base = slugify(file_name.rsplit(".", 1)[0])
    used = set(taken_slugs)
    rows: list[dict] = []
    for order, chapter in enumerate(chapters):
        candidate = f"{base}-{order}" if base else f"bai-{order}"
        slug = unique_slug(candidate, used)
        used.add(slug)
        rows.append(
            {
                "user_id": user_id,
                "source_file_id": file_id,
                "title": chapter.title,
                "slug": slug,
                "content_md": "\n\n".join(
                    outline[index]["content_md"] for index in chapter.source_indexes
                ),
                "order_index": order,
            }
        )
    return rows


@router.post("/presign", response_model=PresignResponse)
def presign(body: PresignRequest, user: CurrentUser = Depends(get_current_user)):
    if body.file_size > settings.MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File vượt quá giới hạn 20MB.",
        )

    file_id = str(uuid.uuid4())
    # user_id prefix: a leaked key still tells you nothing about other users.
    storage_path = f"{user.user_id}/{file_id}.{body.file_type}"

    repo.insert_file(
        {
            "id": file_id,
            "user_id": user.user_id,
            "file_name": body.file_name,
            "file_type": body.file_type,
            "storage_path": storage_path,
            "file_size": body.file_size,
            "processing_status": "pending",
        }
    )
    return PresignResponse(
        file_id=file_id,
        upload_url=r2.presign_put(storage_path, body.file_size),
        storage_path=storage_path,
    )


@router.post("/{file_id}/process", status_code=status.HTTP_202_ACCEPTED)
def process(
    file_id: str,
    background: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    row = repo.get_file(file_id, user.user_id)
    if row is None:
        # 404, never 403 — do not confirm that someone else's file exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file."
        )

    if row["processing_status"] == "processing":
        # Fast path for the common duplicate click. Correctness still rests on
        # the atomic claim below — this only spares an in-flight file a pointless
        # R2 round trip, and stops a transient storage blip from being reported
        # as 503 "storage down" when the real answer is 409 "already running".
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="File đang được xử lý."
        )

    try:
        exists = r2.object_exists(row["storage_path"])
    except Exception:
        # R2 itself is unreachable (bad credentials, outage) — this is not
        # the user's fault and not evidence the file is broken, so the row
        # is left untouched and the user is told to simply retry shortly.
        logger.exception("r2.object_exists failed for file %s", file_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kho lưu trữ tạm thời không khả dụng. Vui lòng thử lại sau ít phút.",
        )

    if not exists:
        missing_object_message = "Chưa thấy file trên kho lưu trữ — hãy tải lên lại."
        repo.set_status(file_id, user.user_id, "error", error_message=missing_object_message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=missing_object_message,
        )

    # A single conditional UPDATE, not a read-then-write: closes the race
    # where two concurrent requests for the same file both see "not
    # processing" and both queue a background job.
    claimed = repo.claim_for_processing(file_id, user.user_id)
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="File đang được xử lý."
        )

    background.add_task(pipeline.process_file, file_id)
    return {"status": "processing"}


@router.get("/{file_id}")
def get_file(file_id: str, user: CurrentUser = Depends(get_current_user)):
    row = repo.get_file(file_id, user.user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file."
        )
    return row


@router.get("")
def list_files(user: CurrentUser = Depends(get_current_user)):
    return repo.list_files(user.user_id)


@router.post("/{file_id}/confirm", response_model=ConfirmResponse)
def confirm(
    file_id: str,
    body: ConfirmRequest,
    user: CurrentUser = Depends(get_current_user),
):
    row = repo.get_file(file_id, user.user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file."
        )

    current_status = row["processing_status"]
    if current_status != "ready_for_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CONFIRM_BLOCKED.get(current_status, "File chưa xử lý xong."),
        )

    outline = row.get("draft_outline") or []
    if not outline:
        # ready_for_review with nothing to review means the row is
        # inconsistent -- refuse rather than write zero lessons and mark done.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="File chưa xử lý xong."
        )

    _validate_source_indexes(body.chapters, len(outline))

    rows = _build_lesson_rows(
        body.chapters,
        outline,
        row["file_name"],
        file_id,
        user.user_id,
        set(repo.list_lesson_slugs(user.user_id)),
    )

    # Insert first, mark done second. A failure here leaves the file at
    # ready_for_review so the user can simply confirm again -- the reverse
    # order would strand a `done` file with no lessons.
    repo.insert_lessons(rows)
    repo.set_status(file_id, user.user_id, "done")
    return ConfirmResponse(lesson_count=len(rows))
