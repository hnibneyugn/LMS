"""The app's day boundary is Vietnam time (UTC+7, no DST). Both the write side
(quiz.py, which stamps daily_activity) and the read side (dashboard streak +
weekly chart) use these helpers so a study day means the same thing everywhere."""

from datetime import date, datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))


def vn_today() -> date:
    """Today's calendar date in Vietnam time."""
    return datetime.now(VN_TZ).date()


def vn_date_of(iso_ts: str) -> date:
    """Vietnam calendar date of an ISO-8601 timestamp that carries an offset."""
    return datetime.fromisoformat(iso_ts).astimezone(VN_TZ).date()
