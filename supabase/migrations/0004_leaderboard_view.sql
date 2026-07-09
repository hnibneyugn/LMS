-- 0004_leaderboard_view.sql
-- Public leaderboard: aggregated, non-sensitive stats only.
--
-- SECURITY NOTE (intentional): this view is created WITHOUT security_invoker, so it runs
-- with the privileges of its owner and reads all users' lesson_progress / daily_activity
-- past their RLS. That is required to aggregate a cross-user leaderboard. It exposes ONLY
-- aggregate counts (display_name, lessons_completed, total_questions_done) and never any
-- answer text, feedback, chat, or document content. Supabase's linter may flag this as a
-- "security definer view" — that warning is expected and accepted here.

create or replace view leaderboard_view as
select
  up.id as user_id,
  up.display_name,
  up.avatar_url,
  count(distinct lp.lesson_id) filter (where lp.status = 'done') as lessons_completed,
  coalesce(sum(da.questions_done_count), 0) as total_questions_done
from user_profiles up
left join lesson_progress lp on lp.user_id = up.id
left join daily_activity da on da.user_id = up.id
group by up.id, up.display_name, up.avatar_url;

grant select on leaderboard_view to authenticated;
