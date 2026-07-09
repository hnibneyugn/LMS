-- 0002_tables.sql
-- All tables for the Personal LMS. See architecture.md for the data model overview.
-- Shared content (lessons, questions) is written only by the service role via /api/sync.
-- Private per-user tables are guarded by RLS in 0003_rls.sql.

-- User profiles (extends Supabase auth.users). Auto-populated by trigger in 0005.
create table if not exists user_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  avatar_url text,
  created_at timestamptz default now()
);

-- Lesson content (SHARED across the group, synced from Obsidian).
create table if not exists lessons (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,          -- derived from the file path in the vault
  title text not null,
  week int,
  topic text,
  content_md text not null,
  updated_at timestamptz default now()
);

-- Review questions (SHARED, tied to a lesson).
create table if not exists questions (
  id uuid primary key default gen_random_uuid(),
  lesson_id uuid references lessons(id) on delete cascade,
  type text not null check (type in ('recall', 'scenario', 'compare', 'explain')),
  question_text text not null,
  order_index int default 0
);

-- Quiz attempts (PRIVATE per user).
create table if not exists quiz_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  question_id uuid references questions(id) on delete cascade,
  user_answer text not null,
  ai_score numeric(3,1) check (ai_score >= 0 and ai_score <= 10),
  ai_feedback jsonb,                  -- { missing_points: string[], comment: string }
  created_at timestamptz default now()
);

-- Lesson progress (PRIVATE per user).
create table if not exists lesson_progress (
  user_id uuid references auth.users(id) on delete cascade,
  lesson_id uuid references lessons(id) on delete cascade,
  status text not null default 'not_done' check (status in ('done', 'not_done')),
  completed_at timestamptz,
  primary key (user_id, lesson_id)
);

-- Socratic chat history (PRIVATE per user).
create table if not exists chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  lesson_id uuid references lessons(id) on delete cascade,
  messages jsonb not null default '[]',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Daily activity (PRIVATE per user) — powers streak + weekly chart.
create table if not exists daily_activity (
  user_id uuid references auth.users(id) on delete cascade,
  activity_date date not null,
  questions_done_count int default 0,
  primary key (user_id, activity_date)
);

-- Uploaded personal document metadata (original file lives in Cloudflare R2).
create table if not exists user_files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  lesson_id uuid references lessons(id) on delete set null,  -- optional link
  file_name text not null,
  file_type text not null check (file_type in ('pdf', 'docx', 'pptx', 'image')),
  storage_path text not null,         -- key in the R2 bucket
  file_size bigint not null,
  processing_status text not null default 'pending'
    check (processing_status in ('pending', 'processing', 'ready', 'error')),
  error_message text,
  uploaded_at timestamptz default now()
);

-- Chunks + vector embeddings for RAG (PRIVATE per user).
create table if not exists document_chunks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  user_file_id uuid references user_files(id) on delete cascade,
  chunk_text text not null,
  embedding vector(768),              -- reduced from 3072 to 768 to save space
  chunk_index int not null
);

-- Vector similarity search index (cosine).
create index if not exists document_chunks_embedding_idx
  on document_chunks using hnsw (embedding vector_cosine_ops);
