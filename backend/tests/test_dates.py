"""Vietnam-time day boundary helpers. The app treats UTC+7 as 'today' so a
question answered at 6am Vietnam time counts for that Vietnam day, not the
UTC day before it."""

from datetime import date, datetime

from app.util.dates import VN_TZ, vn_date_of, vn_today


def test_vn_tz_is_utc_plus_7():
    assert VN_TZ.utcoffset(None).total_seconds() == 7 * 3600


def test_vn_date_of_shifts_late_utc_into_next_vn_day():
    # 23:30 UTC on the 21st is 06:30 on the 22nd in Vietnam.
    assert vn_date_of("2026-07-21T23:30:00+00:00") == date(2026, 7, 22)


def test_vn_date_of_keeps_same_day_when_no_crossing():
    # 02:00 UTC on the 22nd is 09:00 the 22nd in Vietnam.
    assert vn_date_of("2026-07-22T02:00:00+00:00") == date(2026, 7, 22)


def test_vn_today_matches_now_in_vn_tz():
    assert vn_today() == datetime.now(VN_TZ).date()
