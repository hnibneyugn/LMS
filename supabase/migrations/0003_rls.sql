-- 0003_rls.sql
-- Row Level Security. Every private table is locked to its owner (auth.uid() = user_id).
-- Policies cover only the operations each table actually performs (see comments).
-- The service role (used by /api/sync) bypasses RLS entirely.

-- ---------------------------------------------------------------------------
-- Enable RLS
-- ---------------------------------------------------------------------------
alter table user_profiles   enable row level security;
alter table lessons         enable row level security;
alter table questions       enable row level security;
alter table quiz_attempts   enable row level security;
alter table lesson_progress enable row level security;
alter table chat_sessions   enable row level security;
alter table daily_activity  enable row level security;
alter table user_files      enable row level security;
alter table document_chunks enable row level security;

-- ---------------------------------------------------------------------------
-- user_profiles: everyone (authenticated) can read (needed for leaderboard names),
-- but a user can only update their own profile. Inserts happen via the SECURITY
-- DEFINER trigger in 0005, so no client INSERT policy is granted.
-- ---------------------------------------------------------------------------
create policy "profiles_select_all" on user_profiles
  for select using (true);
create policy "profiles_update_own" on user_profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

-- ---------------------------------------------------------------------------
-- lessons / questions: shared read-only for authenticated users.
-- No write policies -> clients cannot mutate; only the service role can.
-- ---------------------------------------------------------------------------
create policy "lessons_select" on lessons
  for select using (auth.role() = 'authenticated');
create policy "questions_select" on questions
  for select using (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- quiz_attempts: immutable history. Read + insert own rows only.
-- ---------------------------------------------------------------------------
create policy "quiz_attempts_select_own" on quiz_attempts
  for select using (auth.uid() = user_id);
create policy "quiz_attempts_insert_own" on quiz_attempts
  for insert with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- lesson_progress: upsert (toggle done/not_done) -> needs SELECT + INSERT + UPDATE.
-- ---------------------------------------------------------------------------
create policy "lesson_progress_select_own" on lesson_progress
  for select using (auth.uid() = user_id);
create policy "lesson_progress_insert_own" on lesson_progress
  for insert with check (auth.uid() = user_id);
create policy "lesson_progress_update_own" on lesson_progress
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- chat_sessions: create a session then append messages -> SELECT + INSERT + UPDATE.
-- ---------------------------------------------------------------------------
create policy "chat_sessions_select_own" on chat_sessions
  for select using (auth.uid() = user_id);
create policy "chat_sessions_insert_own" on chat_sessions
  for insert with check (auth.uid() = user_id);
create policy "chat_sessions_update_own" on chat_sessions
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- daily_activity: upsert increment -> SELECT + INSERT + UPDATE.
-- ---------------------------------------------------------------------------
create policy "daily_activity_select_own" on daily_activity
  for select using (auth.uid() = user_id);
create policy "daily_activity_insert_own" on daily_activity
  for insert with check (auth.uid() = user_id);
create policy "daily_activity_update_own" on daily_activity
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- user_files: manage own files -> SELECT + INSERT + UPDATE (status) + DELETE.
-- ---------------------------------------------------------------------------
create policy "user_files_select_own" on user_files
  for select using (auth.uid() = user_id);
create policy "user_files_insert_own" on user_files
  for insert with check (auth.uid() = user_id);
create policy "user_files_update_own" on user_files
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "user_files_delete_own" on user_files
  for delete using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- document_chunks: RAG chunks -> SELECT + INSERT + DELETE own.
-- (Retrieval always additionally filters WHERE user_id = auth.uid() in queries.)
-- ---------------------------------------------------------------------------
create policy "document_chunks_select_own" on document_chunks
  for select using (auth.uid() = user_id);
create policy "document_chunks_insert_own" on document_chunks
  for insert with check (auth.uid() = user_id);
create policy "document_chunks_delete_own" on document_chunks
  for delete using (auth.uid() = user_id);
