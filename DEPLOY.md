# Deploying Frontdesk

One Vercel project serves both halves: the React frontend as static files, and the FastAPI
backend as a single Python serverless function (`api/index.py`). Postgres is Neon.

## 1. Create the Neon database

1. At https://console.neon.tech, create a project (pick a region close to your users; Vercel
   serverless functions run in a single region by default — US East unless your project changes
   it — so a Neon region close to that keeps query latency down, but any region works).
2. On the project dashboard, click **Connect**.
3. Copy the **pooled** connection string (toggle "Connection pooling" ON — the hostname
   contains `-pooler`). This is your production `DATABASE_URL`.
4. Toggle pooling **OFF** and copy that string too — the **direct** connection. You only use
   this once, from your own machine, to run migrations (§2 below). Never put it in Vercel.

Both strings look like:
```
postgresql://<user>:<password>@<host>/<dbname>?sslmode=require
```
only the host differs (`...-pooler...` vs `...` without it).

## 2. Run migrations and seed (from your machine, using the DIRECT url)

```bash
cd backend
# Temporarily point at Neon directly — do not edit .env; pass everything inline so it never lingers.
DATABASE_URL="<paste the DIRECT connection string>" ./venv/Scripts/alembic upgrade head
DATABASE_URL="<paste the DIRECT connection string>" DEMO_AGENT_PASSWORD="<pick a password>" \
  ./venv/Scripts/python seed.py
```
(PowerShell: `$env:DATABASE_URL="..."; .\venv\Scripts\alembic upgrade head`, then
`$env:DATABASE_URL="..."; $env:DEMO_AGENT_PASSWORD="..."; .\venv\Scripts\python seed.py`, then
unset both after: `Remove-Item Env:DATABASE_URL; Remove-Item Env:DEMO_AGENT_PASSWORD`.)

**`DEMO_AGENT_PASSWORD` is never committed anywhere** — pass it inline exactly like
`DATABASE_URL` above, and share it with whoever needs to log in through a private channel, not
in this repo, a commit message, or an issue. To change the password on an already-seeded
deployment without re-running the full seed, use `scripts/reset_agent_passwords.py` instead
("Rotating the demo password" under Notes, below).

Migrations go through the direct connection because Alembic's DDL (`CREATE TYPE`, trigger
functions) doesn't play well with PgBouncer's transaction-pooling mode that Neon's pooler uses.
The app itself (runtime queries) uses the **pooled** URL once deployed.

## 3. Generate secrets

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # run twice: once each for JWT_SECRET and CRON_SECRET
```
Each must be at least 32 characters (enforced at startup — see `notes/13`).

## 4. Create the Vercel project and set environment variables

Via the dashboard (https://vercel.com/new) or `vercel link` from the repo root, then set these
**Production** environment variables (Project → Settings → Environment Variables):

| Variable | Value |
|---|---|
| `DATABASE_URL` | Neon **pooled** connection string (§1) |
| `JWT_SECRET` | from §3 |
| `CRON_SECRET` | from §3 — **must be named exactly `CRON_SECRET`**: Vercel auto-sends it as `Authorization: Bearer $CRON_SECRET` to cron-triggered requests |
| `ENV` | `production` (anything other than the literal string `dev` works the same — see `app/config.py`) |
| `PUBLIC_BASE_URL` | optional — leave unset and the app falls back to `https://$VERCEL_PROJECT_PRODUCTION_URL`, which Vercel sets automatically. Set it explicitly once you attach a custom domain. |

Do **not** set `TEST_DATABASE_URL` in Vercel — tests never run there.

## 5. Deploy

```bash
npx vercel --prod
```
This builds the frontend (`cd frontend && npm ci && npm run build`) and uploads
`api/index.py` as a Python function per `vercel.json`.

## 6. Smoke-test the live URL

| Check | How |
|---|---|
| Health | `curl https://<url>/api/health` → `{"status":"ok","db":true}` |
| Agent login | Log in at `/login` as `ananya@arvo.example` with whatever you passed to `DEMO_AGENT_PASSWORD` in §2 |
| Ticket list | Loads with SLA badges |
| Claim a ticket | "Take ticket" succeeds, assignee updates |
| Reply | Assignee sends a public reply |
| Internal note | Add a note; confirm it's yellow and never appears in the customer view |
| Customer portal | `/new` → submit → redirects to `/t/<token>` |
| No leaks | On `/t/<token>`, confirm the internal note's text is **not** present anywhere in the page or its network responses |
| SPA reload | Reload `/tickets/9` and `/t/<token>` directly (not just by clicking) — should **not** 404 |
| Cron auth | `curl -i https://<url>/api/cron/auto-close` → `401`; with the real `CRON_SECRET` as a Bearer token → `200` |

## Notes

- **Cron:** `/api/cron/auto-close` runs daily at 03:30 UTC (Vercel Hobby plan allows at most one
  schedule firing all cron jobs once a day; see `vercel.json`). It closes `WAITING_ON_CUSTOMER`/
  `RESOLVED` tickets after 5 working days of no customer reply (§3.4, step 7) — idempotent, so
  it's also safe to trigger manually with the `CRON_SECRET` bearer token between scheduled runs.
- **Redeploying:** the Vercel project is Git-connected (GitHub App installed on
  `sreenandhan-17/Agent-project-`, production branch `main`). Every push to `main` builds and
  deploys automatically — no manual `vercel deploy` needed. Check progress with
  `vercel list --project frontdesk` or the Vercel dashboard. Migrations are **not** run
  automatically — repeat §2 whenever a new Alembic revision needs to go live, same as before.
- **Rolling back:** use the Vercel dashboard's "Promote to Production" on a previous deployment,
  or `git revert` + redeploy. Database migrations are not automatically rolled back.
- **Rotating the demo password** on an already-seeded deployment, without touching tickets,
  customers, or the audit log: run `scripts/reset_agent_passwords.py` against the Neon
  **direct** URL, same pattern as §2:
  ```bash
  cd backend
  DATABASE_URL="<paste the DIRECT connection string>" DEMO_AGENT_PASSWORD="<new password>" \
    ./venv/Scripts/python -m scripts.reset_agent_passwords
  ```
  It prints the agents it updated, never the password itself. Do this whenever a password may
  have been exposed (e.g. committed by mistake) — rotating is just a re-run with a new value.
