"""Grading free-text answers to review questions (#4).

quiz_attempts is immutable history (insert only). daily_activity increments
once per question per UTC day. db.admin() bypasses RLS, so every query filters
user_id explicitly and another user's question/lesson is 404, never 403.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import db
from app.ai.grading import GradingError, grade_answer
from app.dependencies.auth import CurrentUser, get_current_user

router = APIRouter(prefix="/api/quiz", tags=["quiz"])

QUESTION_NOT_FOUND = "Không tìm thấy câu hỏi."
LESSON_NOT_FOUND = "Không tìm thấy bài học."
EMPTY_ANSWER = "Câu trả lời không được để trống."


class GradeRequest(BaseModel):
    question_id: str
    # max_length guards a pathological payload; the emptiness check is in the
    # handler so the message can be Vietnamese (Pydantic's would not be).
    user_answer: str = Field(max_length=5000)


class GradeOut(BaseModel):
    score: float
    missing_points: list[str]
    comment: str
    created_at: str


class AttemptOut(BaseModel):
    question_id: str
    user_answer: str
    score: float
    missing_points: list[str]
    comment: str
    created_at: str


class _Repo:
    """Thin data layer on the service-role client. Every query filters user_id."""

    def get_question(self, user_id: str, question_id: str) -> dict | None:
        result = (
            db.admin()
            .table("questions")
            .select("id, lesson_id, question_text, type")
            .eq("id", question_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_lesson_content(self, user_id: str, lesson_id: str) -> dict | None:
        result = (
            db.admin()
            .table("lessons")
            .select("content_md")
            .eq("id", lesson_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def get_lesson_by_slug(self, user_id: str, slug: str) -> dict | None:
        result = (
            db.admin()
            .table("lessons")
            .select("id")
            .eq("user_id", user_id)
            .eq("slug", slug)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def list_lesson_question_ids(self, user_id: str, lesson_id: str) -> list[str]:
        result = (
            db.admin()
            .table("questions")
            .select("id")
            .eq("user_id", user_id)
            .eq("lesson_id", lesson_id)
            .execute()
        )
        return [row["id"] for row in (result.data or [])]

    def list_question_attempts(self, user_id: str, question_id: str) -> list[dict]:
        result = (
            db.admin()
            .table("quiz_attempts")
            .select("*")
            .eq("user_id", user_id)
            .eq("question_id", question_id)
            .execute()
        )
        return result.data or []

    def insert_attempt(self, row: dict) -> None:
        db.admin().table("quiz_attempts").insert(row).execute()

    def get_daily(self, user_id: str, activity_date: str) -> dict | None:
        result = (
            db.admin()
            .table("daily_activity")
            .select("questions_done_count")
            .eq("user_id", user_id)
            .eq("activity_date", activity_date)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def upsert_daily(self, values: dict) -> None:
        db.admin().table("daily_activity").upsert(
            values, on_conflict="user_id,activity_date"
        ).execute()


repo = _Repo()


def _attempt_date(attempt: dict):
    """UTC date of an attempt's created_at (ISO string with offset)."""
    return datetime.fromisoformat(attempt["created_at"]).astimezone(timezone.utc).date()


@router.post("/grade", response_model=GradeOut)
def grade(body: GradeRequest, user: CurrentUser = Depends(get_current_user)):
    answer = body.user_answer.strip()
    if not answer:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, EMPTY_ANSWER)

    question = repo.get_question(user.user_id, body.question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, QUESTION_NOT_FOUND)

    lesson = repo.get_lesson_content(user.user_id, question["lesson_id"])
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, LESSON_NOT_FOUND)

    try:
        result = grade_answer(
            lesson["content_md"], question["question_text"], question["type"], answer
        )
    except GradingError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    # Count attempts BEFORE inserting -- otherwise the new row makes the count
    # >=1 and questions_done_count would never increment.
    today = datetime.now(timezone.utc).date()
    prior = repo.list_question_attempts(user.user_id, body.question_id)
    first_today = not any(_attempt_date(a) == today for a in prior)

    created_at = datetime.now(timezone.utc).isoformat()
    repo.insert_attempt(
        {
            "id": str(uuid.uuid4()),
            "user_id": user.user_id,
            "question_id": body.question_id,
            "user_answer": answer,
            "ai_score": result.score,
            "ai_feedback": {
                "missing_points": result.missing_points,
                "comment": result.comment,
            },
            "created_at": created_at,
        }
    )

    if first_today:
        date_str = today.isoformat()
        existing = repo.get_daily(user.user_id, date_str)
        count = (existing["questions_done_count"] if existing else 0) + 1
        repo.upsert_daily(
            {
                "user_id": user.user_id,
                "activity_date": date_str,
                "questions_done_count": count,
            }
        )

    return GradeOut(
        score=result.score,
        missing_points=result.missing_points,
        comment=result.comment,
        created_at=created_at,
    )


@router.get("/attempts/{lesson_slug}", response_model=list[AttemptOut])
def attempts(lesson_slug: str, user: CurrentUser = Depends(get_current_user)):
    lesson = repo.get_lesson_by_slug(user.user_id, lesson_slug)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, LESSON_NOT_FOUND)

    out: list[dict] = []
    for question_id in repo.list_lesson_question_ids(user.user_id, lesson["id"]):
        rows = repo.list_question_attempts(user.user_id, question_id)
        if not rows:
            continue
        # created_at is a UTC ISO string (offset +00:00), so lexicographic max
        # is chronological max -- the latest attempt.
        latest = max(rows, key=lambda r: r["created_at"])
        feedback = latest.get("ai_feedback") or {}
        out.append(
            {
                "question_id": question_id,
                "user_answer": latest["user_answer"],
                "score": latest["ai_score"],
                "missing_points": feedback.get("missing_points", []),
                "comment": feedback.get("comment", ""),
                "created_at": latest["created_at"],
            }
        )
    return out
