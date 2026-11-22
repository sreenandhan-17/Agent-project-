# 06: No Vercel entrypoint yet

> **✅ RESOLVED in step 6.** `api/index.py` (adds `backend/` to `sys.path`, imports
> `app.main:app`), root `requirements.txt` (production deps only), and `vercel.json`
> (frontend build, `/api/(.*)` rewrite, SPA fallback rewrite to `/index.html`, daily cron for
> `/api/cron/auto-close`) all exist and are deployed. Project `frontdesk` created and deployed
> via the `vercel` CLI (`vercel project create`, `vercel env add` ×4, `vercel deploy --prod`).
> **Live:** https://frontdesk-mu-neon.vercel.app. `JWT_SECRET` and `CRON_SECRET` were generated
> fresh and set directly in Vercel (type Secret: write-only, never read back). Full steps in
> `DEPLOY.md`.
>
> **Hit along the way:** `vercel link` fails on this machine with a Windows symlink `EPERM`
> while warming its local Python-builder cache (needs Developer Mode or admin, which the CLI
> can't require of a dev box). Worked around it entirely by using `--project <name>
> --create-if-missing` on `vercel deploy`/`vercel env add` instead of linking — no local
> `.vercel/` link file was created, which is why `.gitignore` ignores `.vercel` defensively
> but none exists. If `vercel link`'s convenience (bare `vercel` with no `--project` flag) is
> wanted later, turn on Windows Developer Mode (Settings → Privacy & security → For
> developers) first.
>
> **Also:** `neon init` was first run with a stray working directory inside `frontend/`, which
> added `@neon/config`/`@neon/env` as dependencies of the React app (wrong — that SDK is for
> Node apps reading env vars at runtime; our backend is Python with its own config system).
> Reverted before committing; `frontend/package.json` was never pushed in that state.

**What:** The planned `/api/index.py` and `vercel.json` don't exist yet (PROJECT_SUMMARY.md §9).

**Impact:** The app can't be deployed until they're added. This is planned for step 6.

**Fix (step 6):**
- `api/index.py`: add `backend/` to `sys.path` and import `app.main:app`.
- `vercel.json`: build the frontend from `/frontend` (output `frontend/dist`), rewrite `/api/(.*)` to the Python function, and add the cron entry for `/api/cron/auto-close`.
- Root `requirements.txt`, which Vercel reads, pointing to `backend/requirements.txt` (production dependencies only).
- Set `JWT_SECRET` and `CRON_SECRET` in Vercel.
