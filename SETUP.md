# SETUP — Provisioning the Personal LMS

Step-by-step guide to wiring up the external services. There are **two env files** — copy both
templates and fill values in as you go:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Supabase and the schema are already live for this project; sections 1–2 are what you'd redo on a
fresh project.

## 1. Supabase (database + auth)

1. Create a project at https://supabase.com (Free tier is fine).
2. **Apply the schema.** Either:
   - **SQL editor**: open each file in `supabase/migrations/` in order (`0001` → `0005`) and run it; **or**
   - **Supabase CLI**: `supabase link --project-ref <ref>` then `supabase db push`.
3. **Auth settings** (Authentication → Providers / URL Configuration):
   - Enable **Email** provider with **Magic Link**.
   - **Disable public sign-ups** (invite-only). Add member emails manually (Authentication → Users)
     or later via the in-app `/admin/invite` page (sub-project #7).
   - **Site URL** — set to `http://localhost:5173` for local dev. On deploy, change it to the Vercel
     domain **and add `http://localhost:5173/**` to Redirect URLs**, or local dev breaks.
4. Grab keys from **Project Settings → API**:
   - Backend (`backend/.env`): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
   - Frontend (`frontend/.env.local`): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
5. **JWT verification needs no secret.** The backend verifies tokens against the project's public
   JWKS at `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` (this project signs with **ES256**). If you
   ever point at a project that still signs HS256, `backend/app/dependencies/auth.py` must change —
   check the JWKS endpoint first to see which it is.
6. (Optional) Regenerate DB types once the frontend starts querying tables:
   `supabase gen types typescript --project-id <ref> > frontend/src/lib/database.types.ts`.

> Local option: with Docker + Supabase CLI you can run `supabase start` then `supabase db reset`
> to apply all migrations against a local instance and verify they run cleanly.

## 2. CORS + API base URL

- `backend/.env` → `ALLOWED_ORIGINS=http://localhost:5173` (comma-separated; add the production
  domain on deploy). Never `*` — requests carry Bearer tokens.
- `frontend/.env.local` → `VITE_API_BASE_URL=http://localhost:8000` (the Koyeb URL in production).

## 3. Cloudflare R2 (file storage — deferred with RAG)

1. In the Cloudflare dashboard → **R2**, create a **private** bucket named `user-documents`.
2. **Manage R2 API Tokens** → create an S3 access key/secret.
3. Add to `backend/.env`: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
   `R2_BUCKET_NAME`. The S3 endpoint is `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`.

## 4. Google Gemini (AI)

1. Create an API key at https://aistudio.google.com/apikey.
2. Add `GOOGLE_GENAI_API_KEY` to `backend/.env`.
3. **Model IDs are deferred** (chat + embedding). The spec names `gemini-2.5-pro` / `gemini-2.0-flash`
   and `gemini-embedding-2` (768-dim), but exact current IDs get confirmed when the AI features are
   built. Embeddings must use `output_dimensionality = 768` to match `document_chunks.embedding`.

## 5. GitHub content-sync webhook

1. In the private repo synced from your Obsidian vault (via the Obsidian Git plugin):
   **Settings → Webhooks → Add webhook**.
2. Payload URL: `https://<your-koyeb-domain>/api/sync` (route added in sub-project #2).
3. Content type `application/json`, set a **Secret**, trigger on **push**.
4. Put the same secret in `backend/.env` as `GITHUB_WEBHOOK_SECRET`.

## 6. Admin

- Set `ADMIN_EMAIL` in `backend/.env` — the email allowed to access `/admin/invite`.
- Bootstrap: since sign-ups are disabled, the admin must be added manually once via
  Authentication → Users, otherwise nobody can log in at all.

## 7. Deploy (sub-project #8)

- **Frontend → Vercel**: import the repo, set root directory to `frontend/`, framework Vite. Add
  `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL` under Project → Settings →
  Environment Variables. Static build, no Docker.
- **Backend → Koyeb**: deploy from `backend/Dockerfile` (connect the GitHub repo; Koyeb rebuilds on
  push). Add every variable from `backend/.env.example`. Free instance (512MB RAM, 0.1 vCPU).
- **Keep-alive**: a free cron job (cron-job.org / UptimeRobot) hitting `GET /api/health` every
  10 minutes, as insurance against future spin-down.
- After deploy: update Supabase **Site URL** and backend `ALLOWED_ORIGINS` to the production domain
  (see §1.3 about keeping localhost in Redirect URLs).

---

## Dependencies added later (per sub-project)

**Backend** — installed now: `fastapi`, `uvicorn`, `pyjwt[crypto]`, `python-dotenv`, `pytest`,
`httpx`. Deferred until their feature is built:

| Package | For |
|---|---|
| `python-frontmatter` | Markdown frontmatter parsing (#1 parser) |
| `supabase` | Supabase client from Python (#2 sync onward) |
| `google-genai` | Gemini grading + chat + embeddings (#4, #5) |
| `boto3` | Cloudflare R2 upload / presigned URLs (RAG, deferred) |
| `python-docx`, `python-pptx` | DOCX / PPTX text extraction (RAG, deferred) |

**Frontend** — installed now: `react-router-dom`, `@supabase/supabase-js`, Tailwind + Shadcn deps.

| Package | For |
|---|---|
| a markdown renderer | Rendering `lessons.content_md` (#3) |
| `@tremor/react` | Dashboard charts (#6) |
