# Personal LMS

A private, invite-only Learning Management System (< 10 users). Lesson content is authored in
Obsidian and auto-synced to the web; learners study theory, answer free-text questions graded by
AI, chat with a Socratic tutor, and upload personal documents used as RAG context.

> **Status: Pass 1 — scaffold + database schema.** The Next.js app and the full Supabase schema
> exist; product features are added in later passes. See [`check_list.md`](./check_list.md).

## Docs

- [`CLAUDE.md`](./CLAUDE.md) — conventions & rules for working in this repo
- [`project_context.md`](./project_context.md) — goals, key decisions, assumptions
- [`architecture.md`](./architecture.md) — system architecture + data model
- [`check_list.md`](./check_list.md) — 14-step build progress
- [`SETUP.md`](./SETUP.md) — how to provision Supabase / R2 / Gemini / GitHub / Vercel

## Tech stack

Next.js (App Router) · TypeScript · Tailwind CSS · Shadcn UI · Supabase (Postgres + `pgvector`) ·
Cloudflare R2 · Google Gemini (Vercel AI SDK) · Vercel hosting.

## Local development

```bash
cp .env.example .env.local   # then fill in values (see SETUP.md)
npm install
npm run dev                  # http://localhost:3000
```

Other scripts: `npm run build`, `npm run lint`.

## Database

Schema lives in [`supabase/migrations/`](./supabase/migrations) as ordered SQL files
(`0001`–`0005`). Apply them via the Supabase SQL editor or the Supabase CLI (`supabase db push`).
See [`SETUP.md`](./SETUP.md).
