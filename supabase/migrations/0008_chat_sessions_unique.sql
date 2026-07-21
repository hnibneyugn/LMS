-- 0008_chat_sessions_unique.sql
-- One persistent Socratic chat per (user, lesson) — see #5 D-chat-3.
-- The table (0002) has only `id` as PK, so two concurrent first-messages could
-- create two rows. This unique index makes load-or-create race-safe.
create unique index if not exists chat_sessions_user_lesson_idx
  on chat_sessions (user_id, lesson_id);
