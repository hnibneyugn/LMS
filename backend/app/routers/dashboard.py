"""Dashboard stats (#6): personal streak/weekly/completion + group leaderboard.

The pure functions here take `today` explicitly so they are deterministic and
timezone-agnostic; the route handler passes vn_today(). db.admin() bypasses RLS,
so every per-user _Repo query filters user_id explicitly; leaderboard() reads the
aggregate view unfiltered (cross-user, non-sensitive counts only)."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import db
from app.dependencies.auth import CurrentUser, get_current_user
from app.util.dates import vn_today

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def compute_streaks(active_dates: set[date], today: date) -> tuple[int, int]:
    """(current, longest) study-day streaks.

    current: consecutive days ending EXACTLY at `today` (0 if today is absent --
    past VN midnight with no study the streak resets). longest: the longest run
    of consecutive days anywhere in history.
    """
    if not active_dates:
        return 0, 0

    ordered = sorted(active_dates)
    longest = run = 1
    for prev, cur in zip(ordered, ordered[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        longest = max(longest, run)

    current = 0
    day = today
    while day in active_dates:
        current += 1
        day -= timedelta(days=1)
    return current, longest


def build_weekly(counts_by_date: dict[date, int], today: date) -> list[dict]:
    """7 points oldest->newest (today-6 .. today), zero-filled."""
    out = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        out.append({"date": day.isoformat(), "count": int(counts_by_date.get(day, 0))})
    return out


def completion_pct(completed: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(100 * completed / total)


class WeeklyPoint(BaseModel):
    date: str
    count: int


class MeOut(BaseModel):
    current_streak: int
    longest_streak: int
    weekly_questions: list[WeeklyPoint]
    lessons_completed: int
    lessons_total: int
    completion_pct: int


class LeaderRow(BaseModel):
    user_id: str
    display_name: str
    avatar_url: str | None = None
    active_days: int
    lessons_completed: int
    total_questions_done: int
    is_me: bool


class _Repo:
    """Thin data layer on the service-role client. Every per-user query filters
    user_id explicitly. leaderboard() reads the aggregate view (no user filter --
    it is a cross-user leaderboard exposing only non-sensitive counts)."""

    def list_daily(self, user_id: str) -> list[dict]:
        result = (
            db.admin()
            .table("daily_activity")
            .select("activity_date, questions_done_count")
            .eq("user_id", user_id)
            .execute()
        )
        return result.data or []

    def count_lessons(self, user_id: str) -> int:
        result = db.admin().table("lessons").select("id").eq("user_id", user_id).execute()
        return len(result.data or [])

    def count_completed_lessons(self, user_id: str) -> int:
        result = (
            db.admin()
            .table("lesson_progress")
            .select("lesson_id")
            .eq("user_id", user_id)
            .eq("status", "done")
            .execute()
        )
        return len(result.data or [])

    def leaderboard(self) -> list[dict]:
        result = db.admin().table("leaderboard_view").select("*").execute()
        return result.data or []


repo = _Repo()


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user)):
    rows = repo.list_daily(user.user_id)
    active = {date.fromisoformat(r["activity_date"]) for r in rows}
    counts = {date.fromisoformat(r["activity_date"]): r["questions_done_count"] for r in rows}

    today = vn_today()
    current, longest = compute_streaks(active, today)
    total = repo.count_lessons(user.user_id)
    completed = repo.count_completed_lessons(user.user_id)
    return MeOut(
        current_streak=current,
        longest_streak=longest,
        weekly_questions=build_weekly(counts, today),
        lessons_completed=completed,
        lessons_total=total,
        completion_pct=completion_pct(completed, total),
    )


@router.get("/leaderboard", response_model=list[LeaderRow])
def leaderboard(user: CurrentUser = Depends(get_current_user)):
    rows = repo.leaderboard()
    rows.sort(
        key=lambda r: (r["active_days"], r["lessons_completed"], r["total_questions_done"]),
        reverse=True,
    )
    return [
        LeaderRow(
            user_id=r["user_id"],
            display_name=r["display_name"],
            avatar_url=r.get("avatar_url"),
            active_days=r["active_days"],
            lessons_completed=r["lessons_completed"],
            total_questions_done=r["total_questions_done"],
            is_me=r["user_id"] == user.user_id,
        )
        for r in rows
    ]
