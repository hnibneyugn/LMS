# Personal LMS — Frontend

React + Vite + React Router SPA (no SSR). Handles authentication directly with Supabase Auth and
calls the FastAPI backend with the resulting JWT.

See the [repo README](../README.md) for the whole project and [`../architecture.md`](../architecture.md)
for how the halves fit together.

## Run

```bash
cp .env.example .env.local   # fill in — see ../SETUP.md
npm install
npm run dev                  # http://localhost:5173
npm run build                # type-check + production build
```

The backend must be running at `VITE_API_BASE_URL` (default `http://localhost:8000`) for
authenticated calls to work. Supabase **Site URL must be `http://localhost:5173`** or magic-link
redirects land on the wrong origin.

## Environment

| Variable | Purpose |
|---|---|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Browser-safe anon key (constrained by RLS) |
| `VITE_API_BASE_URL` | FastAPI backend base URL |

Never put the service-role key here — it bypasses RLS and belongs only in the backend.

## Layout

```
src/
  main.tsx  App.tsx          # entry + routes
  lib/
    supabase.ts              # browser Supabase client (auth + session)
    api.ts                   # apiFetch() — attaches Authorization: Bearer
    utils.ts                 # cn()
    database.types.ts        # DB types (placeholder until regenerated)
  components/
    ProtectedRoute.tsx       # client-side route guard
    ui/                      # Shadcn components
  pages/
    Login.tsx  AuthCallback.tsx  Home.tsx
```

Import alias `@` → `src` (configured in `vite.config.ts` and both tsconfigs).

## Conventions

- User-facing strings are **Vietnamese**; code, identifiers and comments are **English**.
- All backend calls go through `apiFetch()` — don't hand-roll `fetch` with a token.
- Add Shadcn components with `npx shadcn@latest add <name>` (lands in `src/components/ui/`).
