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
