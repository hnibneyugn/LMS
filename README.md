# Personal LMS

A private, invite-only Learning Management System (< 10 users). Lesson content is authored in
Obsidian and auto-synced to the web; learners study theory, answer free-text questions graded by
AI, and chat with a Socratic tutor. Personal-document RAG is designed but deferred.

> **Status: sub-project #0 (Foundation + Auth) complete.** Login via Magic Link works end-to-end
> against the live Supabase project; the FastAPI backend verifies Supabase JWTs. Product features
> are built in later sub-projects — see [`check_list.md`](./check_list.md).

## Architecture

Two independent halves in one repo, talking over REST with a Supabase-issued JWT:

- **`frontend/`** — React + Vite + React Router SPA (no SSR). Handles auth directly with Supabase
  Auth; deployed as a static build on Vercel.
- **`backend/`** — Python + FastAPI. Verifies the Supabase JWT (JWKS/ES256), owns sync/AI/storage
  logic; deployed as a Docker container on Koyeb.

See [`architecture.md`](./architecture.md) for the full picture.

## Docs

- [`CLAUDE.md`](./CLAUDE.md) — conventions & rules for working in this repo
- [`project_context.md`](./project_context.md) — goals, key decisions, assumptions
- [`architecture.md`](./architecture.md) — system architecture + data model
- [`check_list.md`](./check_list.md) — sub-project progress (#0–#8)
- [`SETUP.md`](./SETUP.md) — how to provision Supabase / R2 / Gemini / GitHub / Vercel / Koyeb
- [`docs/superpowers/`](./docs/superpowers) — per-sub-project design specs and implementation plans

## Tech stack

React · Vite · React Router · TypeScript · Tailwind CSS · Shadcn UI · Python · FastAPI ·
Supabase (Postgres + `pgvector`) · Cloudflare R2 · Google Gemini (`google-genai`) ·
Vercel (frontend) · Koyeb (backend).

## Local development

Copy the env templates first and fill them in (see [`SETUP.md`](./SETUP.md)):

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

**Backend** — run it in a virtualenv (not Docker) for day-to-day dev:

```bash
cd backend
python -m venv .venv
.venv/Scripts/Activate.ps1        # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
pytest                            # run the test suite
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
npm run build                     # type-check + production build
```

Supabase **Site URL must be `http://localhost:5173`** for magic-link redirects to work locally.

`docker-compose.yml` can run both in containers instead, but the venv + `npm run dev` path is
lighter and is what the project uses.

## Database

Schema lives in [`supabase/migrations/`](./supabase/migrations) as ordered SQL files
(`0001`–`0005`), already applied to the live project. Apply them via the Supabase SQL editor or the
Supabase CLI (`supabase db push`). See [`SETUP.md`](./SETUP.md).
