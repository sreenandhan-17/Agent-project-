# Next step: Build step 6, deploy to Vercel + Neon

Source of truth: PROJECT_SUMMARY.md §2, §9, §11. This step closes **notes 05 and 06**. Optionally add **14** (rate limit).

## You need (once)
- A **Neon** account. Create a project in an India or Singapore region and copy the **pooled** connection string.
- A **Vercel** account. Run `npx vercel login` in the terminal (type `! npx vercel login` here).

## What to build
1. **`api/index.py`:** add `backend/` to `sys.path`, then `from app.main import app`.
2. **Root `requirements.txt`:** production dependencies only (no pytest or httpx). Vercel's Python runtime reads it from the root.
3. **`vercel.json`:**
   - build the frontend: `cd frontend && npm ci && npm run build`, output `frontend/dist`
   - rewrite `/api/(.*)` to the Python function
   - SPA fallback: every other path goes to `/index.html`, so `/tickets/9` works on reload
   - cron entry for `/api/cron/auto-close` (the endpoint itself comes in step 7)
4. **⚠️ Neon pooler + psycopg 3:** the pooled URL goes through PgBouncer in transaction mode, which breaks psycopg's automatic prepared statements. In `app/db.py`, pass `connect_args={"prepare_threshold": None}`. Otherwise requests fail randomly with `prepared statement "_pg3_0" does not exist`.
5. **Vercel environment variables:** `DATABASE_URL` (pooled), `JWT_SECRET` and `CRON_SECRET`, each from `python -c "import secrets; print(secrets.token_urlsafe(48))"`. **Do not set `ENV=dev`** (note 13).
6. **Database:** run `alembic upgrade head` and `python seed.py` once against Neon from your machine, using the **direct** (non-pooled) URL for migrations.
7. **Smoke test on the live URL:** `GET /api/health` returns `{"status":"ok","db":true}`; log in as ananya; the list loads; reloading `/tickets/1` works.

## Prompt to start it
> Read CLAUDE.md, PROJECT_SUMMARY.md and notes/NEXT-STEP.md. Do build step 6: api/index.py, root requirements.txt, vercel.json (frontend build, /api rewrite, SPA fallback), psycopg prepare_threshold for the Neon pooler, then deploy. Ask me for the Neon URL / Vercel login when needed and never print secrets. Smoke-test the live URL and show the results. If it works, tick item 6, mark notes 05 and 06 resolved, update NEXT-STEP.md for step 7, commit "Step 6: deploy to Vercel + Neon" and push.
