"""Reading lessons: the library list, one lesson's content, and progress."""

from datetime import datetime, timezone

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


class LessonNav(BaseModel):
    slug: str
    title: str


class LessonDetailOut(LessonOut):
    content_md: str
    prev: LessonNav | None = None
    next: LessonNav | None = None


class ProgressRequest(BaseModel):
    done: bool


class ProgressOut(BaseModel):
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

    def get_lesson_by_slug(self, user_id: str, slug: str) -> dict | None:
        # Slug is unique per user (lessons_user_slug_idx), not globally, so
        # both columns are needed to identify a row.
        result = (
            db.admin()
            .table("lessons")
            .select("*")
            .eq("user_id", user_id)
            .eq("slug", slug)
            .maybe_single()
            .execute()
        )
        # postgrest's maybe_single returns None itself when nothing matched.
        return result.data if result else None

    def get_lesson(self, lesson_id: str, user_id: str) -> dict | None:
        result = (
            db.admin()
            .table("lessons")
            .select("id")
            .eq("id", lesson_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def upsert_progress(self, values: dict) -> None:
        # lesson_progress's primary key is (user_id, lesson_id), so the
        # conflict target must name both -- the default `id` column does not
        # exist on this table.
        db.admin().table("lesson_progress").upsert(
            values, on_conflict="user_id,lesson_id"
        ).execute()


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


def _neighbours(row: dict, all_rows: list[dict]) -> tuple[dict | None, dict | None]:
    """Previous/next chapter within the SAME source file, by order_index.

    An orphan lesson has no file to be adjacent within, so it gets neither.
    """
    file_id = row.get("source_file_id")
    if file_id is None:
        return None, None

    siblings = sorted(
        (r for r in all_rows if r.get("source_file_id") == file_id),
        key=lambda r: r["order_index"],
    )
    ids = [r["id"] for r in siblings]
    if row["id"] not in ids:
        return None, None

    index = ids.index(row["id"])
    before = siblings[index - 1] if index > 0 else None
    after = siblings[index + 1] if index + 1 < len(siblings) else None

    def nav(target: dict | None) -> dict | None:
        return None if target is None else {"slug": target["slug"], "title": target["title"]}

    return nav(before), nav(after)


@router.get("/{slug}", response_model=LessonDetailOut)
def get_lesson(slug: str, user: CurrentUser = Depends(get_current_user)):
    row = repo.get_lesson_by_slug(user.user_id, slug)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    merged = _merge(row, repo.list_file_names(user.user_id), repo.list_progress(user.user_id))
    before, after = _neighbours(row, repo.list_lessons(user.user_id))
    return {**merged, "prev": before, "next": after}


@router.put("/{lesson_id}/progress", response_model=ProgressOut)
def set_progress(
    lesson_id: str,
    body: ProgressRequest,
    user: CurrentUser = Depends(get_current_user),
):
    if repo.get_lesson(lesson_id, user.user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)

    completed_at = (
        datetime.now(timezone.utc).isoformat() if body.done else None
    )
    repo.upsert_progress(
        {
            "user_id": user.user_id,
            "lesson_id": lesson_id,
            "status": "done" if body.done else "not_done",
            "completed_at": completed_at,
        }
    )
    return {"done": body.done, "completed_at": completed_at}
