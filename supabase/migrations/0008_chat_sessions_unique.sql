-- 0008_chat_sessions_unique.sql
-- One persistent Socratic chat per (user, lesson) — see #5 D-chat-3.
-- The table (0002) has only `id` as PK, so two concurrent first-messages could
-- create two rows. This unique index prevents the duplicate row; the router's
-- load-or-create still has to catch the resulting unique-violation and fall
-- back to re-reading the row the other request created (see chat.py).
create unique index if not exists chat_sessions_user_lesson_idx
  on chat_sessions (user_id, lesson_id);
