# SETUP — Provisioning the Personal LMS

Step-by-step guide to wiring up the external services. Copy `.env.example` to `.env.local` first
and fill values in as you go. Nothing here has live keys yet — this is Pass 1 (scaffold + schema).

## 1. Supabase (database + auth)

1. Create a project at https://supabase.com (Free tier is fine).
2. **Apply the schema.** Either:
   - **SQL editor**: open each file in `supabase/migrations/` in order (`0001` → `0005`) and run it; **or**
   - **Supabase CLI**: `supabase link --project-ref <ref>` then `supabase db push`.
3. **Auth settings** (Authentication → Providers/Settings):
   - Enable **Email** provider with **Magic Link**.
   - **Disable public sign-ups** (invite-only). Add member emails manually (Authentication → Users)
     or later via the in-app `/admin/invite` page.
4. Grab keys from **Project Settings → API**:
   - `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
5. (Optional) Regenerate types once the schema is live:
   `supabase gen types typescript --project-id <ref> > server/types/database.types.ts`.

> Local option: with Docker + Supabase CLI you can run `supabase start` then `supabase db reset`
> to apply all migrations against a local instance and verify they run cleanly.

## 2. Cloudflare R2 (file storage)

1. In the Cloudflare dashboard → **R2**, create a **private** bucket named `user-documents`.
2. **Manage R2 API Tokens** → create an S3 access key/secret.
3. Fill env: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`.
   The S3 endpoint will be `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`.

## 3. Google Gemini (AI)

1. Create an API key at https://aistudio.google.com/apikey.
2. Fill `GOOGLE_GENERATIVE_AI_API_KEY`.
3. **Model IDs are deferred** (chat + embedding). The spec names `gemini-2.5-pro` / `gemini-2.0-flash`
   and `gemini-embedding-2` (768-dim), but exact current IDs will be confirmed when the AI features
   are built. Embeddings must use `output_dimensionality = 768` to match `document_chunks.embedding`.

## 4. GitHub content-sync webhook

1. In the private repo synced from your Obsidian vault (via the Obsidian Git plugin):
   **Settings → Webhooks → Add webhook**.
2. Payload URL: `https://<your-vercel-domain>/api/sync` (route added in a later pass).
3. Content type `application/json`, set a **Secret**, trigger on **push**.
4. Put the same secret in `GITHUB_WEBHOOK_SECRET`.

## 5. Admin

- Set `ADMIN_EMAIL` to the email allowed to access `/admin/invite`.

## 6. Vercel (deploy — later pass)

- Import the repo, add every variable from `.env.example` under **Project → Settings → Environment
  Variables**, then deploy.

---

## Dependencies added later (per feature pass)

Installed now: `@supabase/supabase-js`, `@supabase/ssr`, `zod` (+ Shadcn deps). Deferred until their
feature is built:

| Package | For |
|---|---|
| `gray-matter` | Markdown frontmatter parsing (parser) |
| `ai`, `@ai-sdk/google` | Gemini grading + chat + embeddings |
| `@aws-sdk/client-s3`, `@aws-sdk/s3-request-presigner` | Cloudflare R2 upload / presigned URLs |
| `mammoth` | DOCX → text extraction (RAG) |
| a pptx text parser (e.g. `node-pptx-parser`) | PPTX extraction (RAG) |
| `@tremor/react` | Dashboard charts |
