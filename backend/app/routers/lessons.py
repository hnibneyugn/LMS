"""Reading lessons: the library list, one lesson's content, and progress."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app import db
from app.dependencies.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/lessons", tags=["lessons"])

NOT_FOUND = "Không tìm thấy bài học."


class LessonOut(BaseModel):
    """A row of the library list.

    `content_md` is deliberately absent: the list would carry every lesson's
    full text otherwise, and nothing on that screen renders it.
    """

    id: str
    slug: str
    title: str
    order_index: int
    source_file_id: str | None = None
    source_file_name: str | None = None
    done: bool
    completed_at: str | None = None


class _Repo:
    """Thin data layer. Isolated in a class so tests can swap it wholesale.

    Uses the service-role client, which bypasses RLS -- every read here
    filters on user_id explicitly.
    """

    def list_lessons(self, user_id: str) -> list[dict]:
        result = (
            db.admin()
            .table("lessons")
            .select("id, slug, title, order_index, source_file_id")
            .eq("user_id", user_id)
            .execute()
        )
        return result.data or []

    def list_file_names(self, user_id: str) -> dict[str, str]:
        result = (
            db.admin()
            .table("user_files")
            .select("id, file_name")
            .eq("user_id", user_id)
            .execute()
        )
        return {row["id"]: row["file_name"] for row in (result.data or [])}

    def list_progress(self, user_id: str) -> dict[str, dict]:
        result = (
            db.admin()
            .table("lesson_progress")
            .select("lesson_id, status, completed_at")
            .eq("user_id", user_id)
            .execute()
        )
        return {row["lesson_id"]: row for row in (result.data or [])}


repo = _Repo()


def _merge(row: dict, file_names: dict[str, str], progress: dict[str, dict]) -> dict:
    """Lesson row + its file name + its progress -> one flat response dict."""
    entry = progress.get(row["id"]) or {}
    return {
        **row,
        "source_file_name": file_names.get(row.get("source_file_id")),
        "done": entry.get("status") == "done",
        "completed_at": entry.get("completed_at"),
    }


def _sort_key(row: dict) -> tuple:
    """By file name, then chapter order. Orphans (no source file) go last."""
    name = row["source_file_name"]
    return (name is None, name or "", row["order_index"])


@router.get("", response_model=list[LessonOut])
def list_lessons(user: CurrentUser = Depends(get_current_user)):
    file_names = repo.list_file_names(user.user_id)
    progress = repo.list_progress(user.user_id)
    rows = [_merge(r, file_names, progress) for r in repo.list_lessons(user.user_id)]
    rows.sort(key=_sort_key)
    return rows
