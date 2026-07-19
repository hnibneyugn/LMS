"""File upload lifecycle: presign -> (browser PUTs to R2) -> process -> poll."""

import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import db
from app.config import settings
from app.dependencies.auth import CurrentUser, get_current_user
from app.ingest import pipeline
from app.storage import r2

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

    def set_status(self, file_id: str, status_value: str) -> None:
        db.admin().table("user_files").update(
            {"processing_status": status_value}
        ).eq("id", file_id).execute()


repo = _Repo()


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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="File đang được xử lý."
        )

    if not r2.object_exists(row["storage_path"]):
        repo.set_status(file_id, "error")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chưa thấy file trên kho lưu trữ — hãy tải lên lại.",
        )

    repo.set_status(file_id, "processing")
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
