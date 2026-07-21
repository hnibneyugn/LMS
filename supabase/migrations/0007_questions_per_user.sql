-- 0007_questions_per_user.sql
-- Repurpose `questions` from shared content to per-user private (D13):
-- AI generates a review-question set per user from a lesson's content.

alter table questions
  add column user_id uuid references auth.users(id) on delete cascade;

-- The table is empty in production (no questions were ever generated). Any
-- pre-existing row would be orphaned by this model change -- it has no owner --
-- so drop such rows before making user_id mandatory.
delete from questions where user_id is null;

alter table questions alter column user_id set not null;

-- Drop the legacy lesson-scoped uniqueness. `questions_lesson_order_unique`
-- (UNIQUE (lesson_id, order_index)) predates the per-user pivot and is not
-- declared in any migration -- it lived only in the DB from the shared-questions
-- era. Under per-user questions it is wrong: two users generating questions for
-- the SAME lesson would each need (lesson_id, 0..n) and the second would
-- collide. `if exists` keeps this a no-op on a fresh DB that never had it.
alter table questions drop constraint if exists questions_lesson_order_unique;

-- One question set per (user, lesson); order_index is unique within it. Backs
-- the cache lookup and turns a concurrent double-generate into a unique
-- violation (handled in the router) instead of duplicated questions.
create unique index questions_user_lesson_order_idx
  on questions (user_id, lesson_id, order_index);

-- Replace the shared read policy with per-user RLS.
drop policy "questions_select" on questions;
create policy "questions_select_own" on questions
  for select using (auth.uid() = user_id);
