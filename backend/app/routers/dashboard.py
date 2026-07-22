"""Dashboard stats (#6): personal streak/weekly/completion + group leaderboard.

The pure functions here take `today` explicitly so they are deterministic and
timezone-agnostic; the route handler passes vn_today(). db.admin() bypasses RLS,
so every _Repo query filters user_id explicitly (added in a later task)."""

from datetime import date, timedelta


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
