-- 0006_lessons_per_user_and_files.sql
-- Sub-project #1a. Lessons become PRIVATE per user (each user uploads their own
-- material), and user_files gains the draft chapter outline produced by ingest.

-- ---------------------------------------------------------------------------
-- lessons: shared content -> private per user.
-- ---------------------------------------------------------------------------
alter table lessons
  add column if not exists user_id uuid not null references auth.users(id) on delete cascade,
  add column if not exists source_file_id uuid references user_files(id) on delete set null,
  add column if not exists order_index int not null default 0;

-- Slug is only unique within one user's library now.
alter table lessons drop constraint if exists lessons_slug_key;
create unique index if not exists lessons_user_slug_idx on lessons (user_id, slug);

-- 0003 granted every authenticated user SELECT on lessons (content used to be
-- shared). Policies are OR-ed, so that policy must go or per-user isolation
-- would be a no-op.
drop policy if exists "lessons_select" on lessons;

alter table lessons enable row level security;
-- CREATE POLICY has no IF NOT EXISTS, so drop first to keep this file re-runnable.
drop policy if exists "lessons_own" on lessons;
create policy "lessons_own" on lessons
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- user_files: draft outline + wider type/status vocabularies.
-- ---------------------------------------------------------------------------
alter table user_files add column if not exists draft_outline jsonb;

alter table user_files drop constraint if exists user_files_file_type_check;
alter table user_files add constraint user_files_file_type_check
  check (file_type in ('md', 'pdf', 'docx', 'pptx'));

alter table user_files drop constraint if exists user_files_processing_status_check;
alter table user_files add constraint user_files_processing_status_check
  check (processing_status in
    ('pending', 'processing', 'ready_for_review', 'done', 'error'));
