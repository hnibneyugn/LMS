"""Pure stat math for the dashboard: streaks, weekly zero-fill, completion.
`today` is injected so these are deterministic regardless of run time."""

from datetime import date

from app.routers.dashboard import build_weekly, completion_pct, compute_streaks


def d(day):
    return date(2026, 7, day)


def test_streak_counts_consecutive_days_ending_today():
    active = {d(20), d(21), d(22)}
    current, longest = compute_streaks(active, today=d(22))
    assert current == 3
    assert longest == 3


def test_current_streak_is_zero_when_today_not_studied():
    # Studied through yesterday but not today -> past VN midnight, streak is lost.
    active = {d(19), d(20), d(21)}
    current, longest = compute_streaks(active, today=d(22))
    assert current == 0
    assert longest == 3


def test_longest_ignores_gaps_and_survives_zero_current():
    active = {d(1), d(2), d(3), d(4), d(10), d(20), d(21)}
    current, longest = compute_streaks(active, today=d(22))
    assert current == 0
    assert longest == 4


def test_empty_history_is_zero_zero():
    assert compute_streaks(set(), today=d(22)) == (0, 0)


def test_single_day_today_is_one_one():
    assert compute_streaks({d(22)}, today=d(22)) == (1, 1)


def test_weekly_has_seven_zero_filled_entries_oldest_first():
    counts = {d(22): 5, d(20): 2}
    weekly = build_weekly(counts, today=d(22))
    assert [w["date"] for w in weekly] == [
        "2026-07-16", "2026-07-17", "2026-07-18", "2026-07-19",
        "2026-07-20", "2026-07-21", "2026-07-22",
    ]
    assert [w["count"] for w in weekly] == [0, 0, 0, 0, 2, 0, 5]


def test_completion_pct_rounds_and_guards_zero_total():
    assert completion_pct(1, 3) == 33
    assert completion_pct(2, 3) == 67
    assert completion_pct(0, 0) == 0
    assert completion_pct(4, 4) == 100
