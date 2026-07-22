# Dashboard (#6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Home placeholder with a real dashboard — personal streak/weekly-questions/completion stats plus a group leaderboard ranked by number of study days.

**Architecture:** A thin backend router `dashboard.py` (same `_Repo` + `db.admin()` + explicit `user_id` filter pattern as `quiz.py`) exposes `/api/dashboard/me` and `/api/dashboard/leaderboard`. A shared `app/util/dates.py` helper defines the app's day boundary as Vietnam time (UTC+7) and is used by both the dashboard and `quiz.py` (so streak/chart match the stored `daily_activity` rows). A migration rewrites `leaderboard_view` to add `active_days` and fix a fan-out bug. The frontend `Dashboard.tsx` renders stat cards, a Recharts 7-day bar chart, and a leaderboard table.

**Tech Stack:** Python + FastAPI + Pydantic + supabase-py (backend); React 19 + Vite + TypeScript + Tailwind v4 + **Recharts** (frontend); Postgres view (Supabase).

## Global Constraints

- User-facing strings = **Vietnamese**; code/identifiers/comments = **English**.
- Every private query goes through `db.admin()` and filters `user_id` **explicitly** (RLS is bypassed by the service role — the filter is the only isolation). Another user's row → 404, never 403.
- All dashboard data goes **through the backend** (D21); the frontend never reads Supabase directly here.
- Day boundary = **Vietnam time, UTC+7, no DST** (`app/util/dates.py`), applied at both write (`quiz.py`) and read (dashboard).
- `current_streak` must **end exactly today (VN)** — past midnight VN with no study, it is 0.
- Chart library = **Recharts** (Tremor is incompatible with Tailwind v4 / React 19).
- Backend `pytest` must be **green with clean output** (no warnings). Frontend `npm run build` + `oxlint` must be clean.
- Commit after each task.

---

## File Structure

- `backend/app/util/__init__.py` — new package marker (empty).
- `backend/app/util/dates.py` — VN day helpers (`vn_today`, `vn_date_of`, `VN_TZ`).
- `backend/app/routers/dashboard.py` — pure stat functions + `_Repo` + two endpoints.
- `backend/app/routers/quiz.py` — MODIFY: use `vn_today()` / `vn_date_of()` for `daily_activity`.
- `backend/app/main.py` — MODIFY: register `dashboard.router`.
- `supabase/migrations/0009_leaderboard_active_days.sql` — rewrite `leaderboard_view`.
- `backend/tests/test_dates.py` — unit tests for VN helpers.
- `backend/tests/test_dashboard_stats.py` — unit tests for pure stat functions.
- `backend/tests/test_dashboard_api.py` — endpoint tests with a fake repo.
- `backend/tests/test_dashboard_repo.py` — `_Repo` query-scoping tests with `FakeClient`.
- `backend/scripts/verify_6.py` — live end-to-end check.
- `frontend/src/lib/dashboard.ts` — payload types + `apiFetch` wrappers.
- `frontend/src/pages/Dashboard.tsx` — the page (replaces `Home.tsx`).
- `frontend/src/pages/Home.tsx` — DELETE.
- `frontend/src/App.tsx` — MODIFY: route `/*` → `Dashboard`.
- `frontend/package.json` — MODIFY: add `recharts`.

---

## Task 1: VN date helper

**Files:**
- Create: `backend/app/util/__init__.py` (empty)
- Create: `backend/app/util/dates.py`
- Test: `backend/tests/test_dates.py`

**Interfaces:**
- Produces:
  - `VN_TZ: timezone` — fixed UTC+7.
  - `vn_today() -> datetime.date` — today's date in VN time.
  - `vn_date_of(iso_ts: str) -> datetime.date` — VN calendar date of an ISO-8601 timestamp (with offset).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_dates.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.util'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/util/__init__.py` (empty file).

Create `backend/app/util/dates.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dates.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/util/__init__.py backend/app/util/dates.py backend/tests/test_dates.py
git commit -m "feat(6): VN (UTC+7) day-boundary helpers"
```

---

## Task 2: Rewrite leaderboard_view (migration 0009)

**Files:**
- Create: `supabase/migrations/0009_leaderboard_active_days.sql`

**Interfaces:**
- Produces: view `leaderboard_view` with columns `user_id, display_name, avatar_url, lessons_completed, total_questions_done, active_days`.

- [ ] **Step 1: Write the migration file**

Create `supabase/migrations/0009_leaderboard_active_days.sql`:

```sql
-- 0009_leaderboard_active_days.sql
-- Rank the leaderboard by number of distinct study days (#6). Also fixes a
-- fan-out bug in 0004: joining lesson_progress AND daily_activity in one query
-- multiplied sum(questions_done_count) by the done-lesson count. Each private
-- table is now aggregated in its own subquery so the counts are independent.
--
-- SECURITY NOTE (intentional, same as 0004): created WITHOUT security_invoker so
-- it reads all users' rows past RLS to build a cross-user leaderboard. It exposes
-- ONLY aggregates (display_name, avatar_url, lessons_completed,
-- total_questions_done, active_days) -- never answer text, feedback, chat, or
-- document content. Supabase's "security definer view" linter warning is expected
-- and accepted here.

create or replace view leaderboard_view as
select
  up.id as user_id,
  up.display_name,
  up.avatar_url,
  coalesce(lp.lessons_completed, 0)    as lessons_completed,
  coalesce(da.total_questions_done, 0) as total_questions_done,
  coalesce(da.active_days, 0)          as active_days
from user_profiles up
left join (
  select user_id, count(distinct lesson_id) as lessons_completed
  from lesson_progress where status = 'done' group by user_id
) lp on lp.user_id = up.id
left join (
  select user_id,
         count(distinct activity_date) as active_days,
         sum(questions_done_count)     as total_questions_done
  from daily_activity group by user_id
) da on da.user_id = up.id;

grant select on leaderboard_view to authenticated;
```

- [ ] **Step 2: Apply the migration to Supabase**

Apply via the Supabase MCP tool `apply_migration` with name `0009_leaderboard_active_days` and the SQL above. (Or `psql`/dashboard if MCP is unavailable.)

- [ ] **Step 3: Verify the view shape and no fan-out**

Run this read via the Supabase MCP `execute_sql` (or dashboard SQL editor):

```sql
select user_id, lessons_completed, total_questions_done, active_days
from leaderboard_view
order by active_days desc
limit 10;
```

Expected: query succeeds and returns an `active_days` column. Sanity-check one user known to have several done lessons and several activity days: `total_questions_done` equals the plain `sum(questions_done_count)` for that user (NOT multiplied by the number of done lessons). Confirm with:

```sql
select
  (select coalesce(sum(questions_done_count),0) from daily_activity where user_id = :uid) as raw_sum,
  (select total_questions_done from leaderboard_view where user_id = :uid) as view_sum;
```

Expected: `raw_sum = view_sum`.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0009_leaderboard_active_days.sql
git commit -m "feat(6): leaderboard_view adds active_days, fixes fan-out"
```

---

## Task 3: Dashboard pure stat functions

**Files:**
- Create: `backend/app/routers/dashboard.py` (functions only in this task)
- Test: `backend/tests/test_dashboard_stats.py`

**Interfaces:**
- Produces (module-level pure functions in `app.routers.dashboard`):
  - `compute_streaks(active_dates: set[date], today: date) -> tuple[int, int]` — returns `(current_streak, longest_streak)`. `current` counts consecutive days ending exactly at `today`; it is 0 if `today` is not in `active_dates`.
  - `build_weekly(counts_by_date: dict[date, int], today: date) -> list[dict]` — 7 entries oldest→newest, `today-6 … today`, each `{"date": iso, "count": int}`, zero-filled.
  - `completion_pct(completed: int, total: int) -> int` — rounded percent, 0 when `total <= 0`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_dashboard_stats.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dashboard_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.dashboard'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/routers/dashboard.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dashboard_stats.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/dashboard.py backend/tests/test_dashboard_stats.py
git commit -m "feat(6): dashboard streak/weekly/completion math"
```

---

## Task 4: Dashboard router — repo, endpoints, registration

**Files:**
- Modify: `backend/app/routers/dashboard.py` (add imports, models, `_Repo`, `repo`, two routes)
- Modify: `backend/app/main.py:7` and `:31` (import + include dashboard router)
- Test: `backend/tests/test_dashboard_api.py`
- Test: `backend/tests/test_dashboard_repo.py`

**Interfaces:**
- Consumes: `compute_streaks`, `build_weekly`, `completion_pct` (Task 3); `vn_today` (Task 1); `leaderboard_view` (Task 2); `get_current_user` / `CurrentUser` from `app.dependencies.auth`; `db` from `app`.
- Produces:
  - `GET /api/dashboard/me` → `MeOut { current_streak, longest_streak, weekly_questions: [{date, count}], lessons_completed, lessons_total, completion_pct }`.
  - `GET /api/dashboard/leaderboard` → `list[LeaderRow { user_id, display_name, avatar_url, active_days, lessons_completed, total_questions_done, is_me }]`, sorted by `(active_days, lessons_completed, total_questions_done)` desc.
  - `_Repo` methods: `list_daily(user_id) -> list[dict]` (rows `{activity_date, questions_done_count}`), `count_lessons(user_id) -> int`, `count_completed_lessons(user_id) -> int`, `leaderboard() -> list[dict]`.
  - Module attribute `repo = _Repo()` (tests monkeypatch it).

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/test_dashboard_api.py`:

```python
"""Dashboard endpoints with a fake repo (no DB, no clock dependence for the
leaderboard; /me still uses the real vn_today, so its assertions avoid exact
dates and check structure + counts)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import dashboard as dash
from tests.conftest import OTHER_USER_ID, USER_ID, auth_headers

client = TestClient(app)


class _FakeRepo:
    def __init__(self):
        self.daily: list[dict] = []
        self.total = 0
        self.completed = 0
        self.rows: list[dict] = []

    def list_daily(self, user_id):
        return [dict(r) for r in self.daily]

    def count_lessons(self, user_id):
        return self.total

    def count_completed_lessons(self, user_id):
        return self.completed

    def leaderboard(self):
        return [dict(r) for r in self.rows]


@pytest.fixture
def repo(monkeypatch):
    r = _FakeRepo()
    monkeypatch.setattr(dash, "repo", r)
    return r


def test_me_returns_full_shape(repo):
    repo.total = 4
    repo.completed = 1
    res = client.get("/api/dashboard/me", headers=auth_headers())
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {
        "current_streak", "longest_streak", "weekly_questions",
        "lessons_completed", "lessons_total", "completion_pct",
    }
    assert len(body["weekly_questions"]) == 7
    assert body["lessons_total"] == 4
    assert body["lessons_completed"] == 1
    assert body["completion_pct"] == 25


def test_me_requires_a_token(repo):
    assert client.get("/api/dashboard/me").status_code == 401


def test_leaderboard_sorted_by_active_days_and_flags_me(repo):
    repo.rows = [
        {"user_id": OTHER_USER_ID, "display_name": "An", "avatar_url": None,
         "active_days": 2, "lessons_completed": 1, "total_questions_done": 4},
        {"user_id": USER_ID, "display_name": "Tôi", "avatar_url": None,
         "active_days": 5, "lessons_completed": 3, "total_questions_done": 9},
    ]
    res = client.get("/api/dashboard/leaderboard", headers=auth_headers())
    assert res.status_code == 200
    body = res.json()
    # Sorted by active_days desc -> USER_ID first, flagged is_me.
    assert body[0]["user_id"] == USER_ID
    assert body[0]["is_me"] is True
    assert body[1]["is_me"] is False


def test_leaderboard_requires_a_token(repo):
    assert client.get("/api/dashboard/leaderboard").status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dashboard_api.py -v`
Expected: FAIL — the routes 404 (router not registered) / models undefined.

- [ ] **Step 3: Add models, repo, routes to `dashboard.py`**

Prepend the new imports to `backend/app/routers/dashboard.py` (above the existing `from datetime import date, timedelta` — keep that line):

```python
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import db
from app.dependencies.auth import CurrentUser, get_current_user
from app.util.dates import vn_today

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
```

Then append below the existing pure functions:

```python
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
```

- [ ] **Step 4: Register the router in `main.py`**

In `backend/app/main.py`, change the import line:

```python
from app.routers import chat, dashboard, files, health, lessons, me, quiz
```

and add after `app.include_router(chat.router)`:

```python
app.include_router(dashboard.router)
```

- [ ] **Step 5: Run the API test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dashboard_api.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Write the repo query-scoping test**

Create `backend/tests/test_dashboard_repo.py`:

```python
"""_Repo query building for dashboard.py against a fake supabase client. The
explicit .eq('user_id', ...) filters are the only isolation past RLS, so a
dropped filter reds a test."""

import pytest

from app.routers import dashboard as dash
from tests.conftest import OTHER_USER_ID, USER_ID, FakeClient


@pytest.fixture
def stores(monkeypatch):
    tables = {
        "daily_activity": {},
        "lessons": {},
        "lesson_progress": {},
        "leaderboard_view": {},
    }
    client_ = FakeClient({}, tables=tables)
    monkeypatch.setattr(dash.db, "admin", lambda: client_)
    return tables


def test_list_daily_only_returns_own_rows(stores):
    stores["daily_activity"]["r1"] = {
        "id": "r1", "user_id": USER_ID, "activity_date": "2026-07-22",
        "questions_done_count": 3,
    }
    stores["daily_activity"]["r9"] = {
        "id": "r9", "user_id": OTHER_USER_ID, "activity_date": "2026-07-22",
        "questions_done_count": 9,
    }
    repo = dash._Repo()
    rows = repo.list_daily(USER_ID)
    assert len(rows) == 1
    assert rows[0]["questions_done_count"] == 3


def test_count_lessons_scoped_to_user(stores):
    stores["lessons"]["l1"] = {"id": "l1", "user_id": USER_ID}
    stores["lessons"]["l2"] = {"id": "l2", "user_id": USER_ID}
    stores["lessons"]["l9"] = {"id": "l9", "user_id": OTHER_USER_ID}
    repo = dash._Repo()
    assert repo.count_lessons(USER_ID) == 2
    assert repo.count_lessons(OTHER_USER_ID) == 1


def test_count_completed_lessons_filters_status_and_user(stores):
    stores["lesson_progress"]["p1"] = {
        "id": "p1", "user_id": USER_ID, "lesson_id": "l1", "status": "done",
    }
    stores["lesson_progress"]["p2"] = {
        "id": "p2", "user_id": USER_ID, "lesson_id": "l2", "status": "not_done",
    }
    stores["lesson_progress"]["p9"] = {
        "id": "p9", "user_id": OTHER_USER_ID, "lesson_id": "l1", "status": "done",
    }
    repo = dash._Repo()
    assert repo.count_completed_lessons(USER_ID) == 1


def test_leaderboard_reads_all_rows(stores):
    stores["leaderboard_view"]["u1"] = {
        "id": "u1", "user_id": USER_ID, "display_name": "A", "avatar_url": None,
        "active_days": 2, "lessons_completed": 1, "total_questions_done": 4,
    }
    stores["leaderboard_view"]["u2"] = {
        "id": "u2", "user_id": OTHER_USER_ID, "display_name": "B", "avatar_url": None,
        "active_days": 5, "lessons_completed": 3, "total_questions_done": 9,
    }
    repo = dash._Repo()
    assert len(repo.leaderboard()) == 2
```

Note: `FakeClient` rows need an `id` key because `FakeTable` inserts index on `id`; here we only read, but the store dict is keyed by whatever we set — the fake matches on the `.eq` filters against row fields, so include `user_id`/`status` as shown.

- [ ] **Step 7: Run the repo test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dashboard_repo.py -v`
Expected: PASS (4 passed).

- [ ] **Step 8: Run the full backend suite (clean output)**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass, no warnings.

- [ ] **Step 9: Commit**

```bash
git add backend/app/routers/dashboard.py backend/app/main.py backend/tests/test_dashboard_api.py backend/tests/test_dashboard_repo.py
git commit -m "feat(6): /api/dashboard/me + /leaderboard endpoints"
```

---

## Task 5: quiz.py uses VN day boundary

**Files:**
- Modify: `backend/app/routers/quiz.py` (imports, `_attempt_date`, `today`)

**Interfaces:**
- Consumes: `vn_today`, `vn_date_of` (Task 1).
- Produces: no signature change; `daily_activity.activity_date` is now the VN date; the "first attempt of the day" check compares VN dates.

- [ ] **Step 1: Replace the UTC date usage**

In `backend/app/routers/quiz.py`:

Change the datetime import line (currently `from datetime import datetime, timezone`) — keep it (still needed for `created_at` timestamps) and add the helper import right after the `from app import db` line:

```python
from app.util.dates import vn_date_of, vn_today
```

Replace the `_attempt_date` helper:

```python
def _attempt_date(attempt: dict):
    """VN calendar date of an attempt's created_at (ISO string with offset)."""
    return vn_date_of(attempt["created_at"])
```

Replace the `today` assignment inside `grade` (currently `today = datetime.now(timezone.utc).date()`):

```python
    today = vn_today()
```

Leave `created_at = datetime.now(timezone.utc).isoformat()` unchanged — the stored timestamp stays UTC; only the day-bucketing is VN.

- [ ] **Step 2: Run the quiz tests**

Run: `cd backend && python -m pytest tests/test_quiz_api.py tests/test_quiz_repo.py -v`
Expected: PASS. (These tests assert counts/behavior, not the literal UTC date string, so they stay green under the VN boundary.)

- [ ] **Step 3: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: all pass, clean output.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/quiz.py
git commit -m "feat(6): quiz stamps daily_activity by VN day, not UTC"
```

---

## Task 6: Frontend data layer — recharts + lib/dashboard.ts

**Files:**
- Modify: `frontend/package.json` (add `recharts`)
- Create: `frontend/src/lib/dashboard.ts`

**Interfaces:**
- Produces:
  - types `WeeklyPoint { date: string; count: number }`, `DashboardMe { current_streak; longest_streak; weekly_questions: WeeklyPoint[]; lessons_completed; lessons_total; completion_pct }`, `LeaderRow { user_id; display_name; avatar_url: string | null; active_days; lessons_completed; total_questions_done; is_me }`.
  - `getDashboardMe(): Promise<DashboardMe>`, `getLeaderboard(): Promise<LeaderRow[]>`.

- [ ] **Step 1: Install recharts**

Run: `cd frontend && npm install recharts@^3`
Expected: `recharts` added to `dependencies`; `npm install` exits 0.

- [ ] **Step 2: Create the data layer**

Create `frontend/src/lib/dashboard.ts`:

```ts
import { apiFetch } from "@/lib/api"

export interface WeeklyPoint {
  date: string // ISO yyyy-mm-dd
  count: number
}

export interface DashboardMe {
  current_streak: number
  longest_streak: number
  weekly_questions: WeeklyPoint[]
  lessons_completed: number
  lessons_total: number
  completion_pct: number
}

export interface LeaderRow {
  user_id: string
  display_name: string
  avatar_url: string | null
  active_days: number
  lessons_completed: number
  total_questions_done: number
  is_me: boolean
}

/** Personal streak / weekly-questions / completion stats for the current user. */
export async function getDashboardMe(): Promise<DashboardMe> {
  return (await apiFetch("/api/dashboard/me")) as DashboardMe
}

/** Group leaderboard, already ranked by number of study days. */
export async function getLeaderboard(): Promise<LeaderRow[]> {
  return (await apiFetch("/api/dashboard/leaderboard")) as LeaderRow[]
}
```

- [ ] **Step 3: Verify the build compiles**

Run: `cd frontend && npm run build`
Expected: no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/dashboard.ts
git commit -m "feat(6): recharts dep + dashboard data layer"
```

---

## Task 7: Dashboard page replaces Home

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`
- Delete: `frontend/src/pages/Home.tsx`
- Modify: `frontend/src/App.tsx` (import + `/*` route)

**Interfaces:**
- Consumes: `getDashboardMe`, `getLeaderboard`, `DashboardMe`, `LeaderRow` (Task 6); `errorMessage` from `@/lib/files`; `Button` from `@/components/ui/button`; Recharts `BarChart`.

- [ ] **Step 1: Write the Dashboard page**

Create `frontend/src/pages/Dashboard.tsx`:

```tsx
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { supabase } from "@/lib/supabase"
import { errorMessage } from "@/lib/files"
import { getDashboardMe, getLeaderboard, type DashboardMe, type LeaderRow } from "@/lib/dashboard"
import { Button } from "@/components/ui/button"

const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"]

/** "yyyy-mm-dd" -> Vietnamese short weekday, parsed as a local date (no TZ shift). */
function dayLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number)
  return WEEKDAYS[new Date(y, m - 1, d).getDay()]
}

export function Dashboard() {
  const navigate = useNavigate()
  const [email, setEmail] = useState<string | null>(null)
  const [me, setMe] = useState<DashboardMe | null>(null)
  const [board, setBoard] = useState<LeaderRow[] | null>(null)
  const [meError, setMeError] = useState<string | null>(null)
  const [boardError, setBoardError] = useState<string | null>(null)
  const [signOutError, setSignOutError] = useState<string | null>(null)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setEmail(data.user?.email ?? null))
    getDashboardMe().then(setMe).catch((e) => setMeError(errorMessage(e)))
    getLeaderboard().then(setBoard).catch((e) => setBoardError(errorMessage(e)))
  }, [])

  async function handleSignOut() {
    const { error } = await supabase.auth.signOut()
    if (error) {
      setSignOutError("Không đăng xuất được. Vui lòng thử lại.")
      return
    }
    navigate("/login", { replace: true })
  }

  const chartData = me?.weekly_questions.map((p) => ({ label: dayLabel(p.date), count: p.count })) ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Bảng điều khiển</h1>
          {email && <p className="text-sm text-gray-500">{email}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => navigate("/lessons")}>Bài học</Button>
          <Button variant="outline" onClick={() => navigate("/files")}>
            Tài liệu của tôi
          </Button>
          <Button variant="outline" onClick={() => navigate("/account")}>
            Tài khoản
          </Button>
          <Button variant="outline" onClick={handleSignOut}>
            Đăng xuất
          </Button>
        </div>
      </header>
      {signOutError && <p className="text-sm text-red-600">{signOutError}</p>}

      {/* Stat cards */}
      {meError ? (
        <p className="text-sm text-red-600">Không tải được thống kê: {meError}</p>
      ) : !me ? (
        <p className="text-sm text-gray-500">Đang tải thống kê…</p>
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Streak hiện tại" value={`${me.current_streak} 🔥`} sub="ngày liên tiếp" />
            <StatCard label="Streak dài nhất" value={`${me.longest_streak}`} sub="ngày" />
            <StatCard
              label="Hoàn thành bài học"
              value={`${me.completion_pct}%`}
              sub={`${me.lessons_completed}/${me.lessons_total} bài`}
            />
          </section>

          <section className="rounded-lg border p-4">
            <h2 className="mb-2 text-sm font-medium text-gray-700">Câu hỏi đã làm 7 ngày qua</h2>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={24} />
                  <Tooltip formatter={(v) => [`${v} câu`, "Đã làm"]} labelFormatter={() => ""} />
                  <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        </>
      )}

      {/* Leaderboard */}
      <section className="rounded-lg border p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-700">Bảng xếp hạng chuyên cần</h2>
        {boardError ? (
          <p className="text-sm text-red-600">Không tải được bảng xếp hạng: {boardError}</p>
        ) : !board ? (
          <p className="text-sm text-gray-500">Đang tải…</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-1 pr-2">#</th>
                <th className="py-1 pr-2">Tên</th>
                <th className="py-1 pr-2 text-right">Ngày học</th>
                <th className="py-1 pr-2 text-right">Bài xong</th>
                <th className="py-1 text-right">Câu hỏi</th>
              </tr>
            </thead>
            <tbody>
              {board.map((row, i) => (
                <tr
                  key={row.user_id}
                  className={row.is_me ? "rounded bg-blue-50 font-medium" : ""}
                >
                  <td className="py-1 pr-2">{i + 1}</td>
                  <td className="py-1 pr-2">{row.display_name}</td>
                  <td className="py-1 pr-2 text-right">{row.active_days}</td>
                  <td className="py-1 pr-2 text-right">{row.lessons_completed}</td>
                  <td className="py-1 text-right">{row.total_questions_done}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

function StatCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      <p className="text-xs text-gray-400">{sub}</p>
    </div>
  )
}
```

- [ ] **Step 2: Swap the route in `App.tsx`**

In `frontend/src/App.tsx`, replace the `Home` import:

```tsx
import { Dashboard } from "@/pages/Dashboard"
```

and change the catch-all route element from `<Home />` to `<Dashboard />`:

```tsx
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
```

- [ ] **Step 3: Delete the old placeholder**

Run: `git rm frontend/src/pages/Home.tsx`
(Confirm no other file imports `Home` — only `App.tsx` did.)

- [ ] **Step 4: Verify build + lint**

Run: `cd frontend && npm run build && npx oxlint`
Expected: build succeeds (no TS errors), oxlint clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/App.tsx
git commit -m "feat(6): dashboard page replaces Home placeholder"
```

---

## Task 8: Live end-to-end verify (verify_6.py)

**Files:**
- Create: `backend/scripts/verify_6.py`

**Interfaces:**
- Consumes: `mint_access_token` from `backend/scripts/verify_1b.py`; running API at `http://localhost:8000`; `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_URL` env.

- [ ] **Step 1: Write the verify script**

Create `backend/scripts/verify_6.py`:

```python
"""Live check of #6 dashboard endpoints against the real API + Supabase.

Seeds one daily_activity row for the ADMIN user (VN today), asserts /me reflects
it (streak >= 1, 7-day chart, completion math) and /leaderboard flags the user,
then removes the seeded row.

Usage: PYTHONIOENCODING=utf-8 python scripts/verify_6.py
Requires the API on http://localhost:8000 and SUPABASE_ANON_KEY in the env
(it lives in frontend/.env.local); SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in backend/.env.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from verify_1b import mint_access_token

load_dotenv()

API = "http://localhost:8000"
VN_TZ = timezone(timedelta(hours=7))


def _svc_headers(service_key):
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }


def main() -> int:
    token = mint_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    base = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    # Resolve the admin user_id from /api/me.
    me_auth = httpx.get(f"{API}/api/me", headers=headers, timeout=30).json()
    user_id = me_auth["user_id"] if "user_id" in me_auth else me_auth["sub"]
    today = datetime.now(VN_TZ).date().isoformat()

    # Seed one daily_activity row for VN today (upsert, so we don't clobber counts
    # permanently -- we delete it at the end).
    seeded = httpx.post(
        f"{base}/rest/v1/daily_activity",
        headers=_svc_headers(service_key),
        json={"user_id": user_id, "activity_date": today, "questions_done_count": 3},
        timeout=30,
    )
    assert seeded.status_code in (200, 201), seeded.text

    me = httpx.get(f"{API}/api/dashboard/me", headers=headers, timeout=30).json()
    print("me:", me)
    assert me["current_streak"] >= 1, "today was seeded, streak must be >= 1"
    assert len(me["weekly_questions"]) == 7
    assert me["weekly_questions"][-1]["date"] == today
    assert me["weekly_questions"][-1]["count"] >= 3
    assert 0 <= me["completion_pct"] <= 100

    board = httpx.get(f"{API}/api/dashboard/leaderboard", headers=headers, timeout=30).json()
    mine = [r for r in board if r["is_me"]]
    print(f"leaderboard rows: {len(board)}; my row: {mine}")
    assert len(mine) == 1, "exactly one row should be flagged is_me"
    assert mine[0]["active_days"] >= 1

    # Clean up the seeded row.
    httpx.request(
        "DELETE",
        f"{base}/rest/v1/daily_activity",
        params={"user_id": f"eq.{user_id}", "activity_date": f"eq.{today}"},
        headers=_svc_headers(service_key),
        timeout=30,
    )
    print("cleaned up seeded daily_activity row")
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: if the admin already had a `daily_activity` row for VN today, the upsert overwrites `questions_done_count` to 3 and the final DELETE removes it — re-seed the real value only if the account was mid-use. For a clean account this is a no-op after cleanup.

- [ ] **Step 2: Run it live**

Start the backend (`cd backend && python -m uvicorn app.main:app --port 8000`) in one terminal, then in another:

Run: `cd backend && PYTHONIOENCODING=utf-8 SUPABASE_ANON_KEY=<anon from frontend/.env.local> python scripts/verify_6.py`
Expected: prints `ALL CHECKS PASSED`.

- [ ] **Step 3: Manual browser check**

Start frontend (`cd frontend && npm run dev`), log in, land on `/`:
- 3 stat cards show streak/longest/completion.
- Bar chart shows 7 day columns with Vietnamese labels.
- Leaderboard lists members; your row is highlighted.
- Nav buttons work; **Đăng xuất** returns to `/login`.
- F5 keeps you on the dashboard (session persists).

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/verify_6.py
git commit -m "test(6): live end-to-end verify_6"
```

---

## Task 9: Update checklist + project context

**Files:**
- Modify: `check_list.md` (mark #6 items done, add verify notes)
- Modify: `project_context.md` (record D-dash-1..5)

**Interfaces:** none (documentation).

- [ ] **Step 1: Mark #6 done in `check_list.md`**

Under `### #6 — Dashboard`, change the four `- [ ]` items to `- [x]`, and append a short "✅ XONG (2026-07-22)" note plus the verify summary (streak resets at VN midnight, Recharts, leaderboard by active days, `verify_6.py` passed), mirroring how #5 is written.

- [ ] **Step 2: Record decisions in `project_context.md`**

Add D-dash-1..5 (from the spec's "Quyết định" section) to the decisions log in the same style as the existing D-entries: ranking by study days; Recharts over Tremor (Tailwind v4 / React 19); dashboard data through backend; leaderboard_view fan-out fix; VN (UTC+7) day boundary applied at write + read with strict-midnight streak reset.

- [ ] **Step 3: Final full verification**

Run: `cd backend && python -m pytest -q` → all green, clean.
Run: `cd frontend && npm run build && npx oxlint` → clean.

- [ ] **Step 4: Commit**

```bash
git add check_list.md project_context.md
git commit -m "docs(6): mark dashboard done, record D-dash decisions"
```

---

## Self-Review

**Spec coverage:**
- Streak (current + longest, VN midnight reset) → Task 3 (math) + Task 1 (VN) + Task 4 (wired).
- Weekly 7-day bar chart → Task 3 (`build_weekly`) + Task 7 (Recharts).
- % completion → Task 3 (`completion_pct`) + Task 4/7.
- Leaderboard by active days, self-highlight → Task 2 (view) + Task 4 (endpoint/sort/is_me) + Task 7 (table).
- Leaderboard_view fan-out fix → Task 2.
- VN day boundary at write + read → Task 1 + Task 5 (quiz) + Task 4 (dashboard).
- Data through backend (D21) → Tasks 4, 6.
- Recharts (not Tremor) → Tasks 6, 7.
- Home replaced + proper logout → Task 7.
- Tests (repo/api/stats/dates) + build/lint + live verify → Tasks 1,3,4,5,8.

**Placeholder scan:** none — every code step contains complete code.

**Type consistency:** `MeOut`/`LeaderRow`/`WeeklyPoint` fields match between backend (Task 4) and frontend `DashboardMe`/`LeaderRow`/`WeeklyPoint` (Task 6). `compute_streaks`/`build_weekly`/`completion_pct` signatures identical across Tasks 3 and 4. `list_daily`/`count_lessons`/`count_completed_lessons`/`leaderboard` identical across Tasks 4 (impl), test files, and the `_FakeRepo`.
