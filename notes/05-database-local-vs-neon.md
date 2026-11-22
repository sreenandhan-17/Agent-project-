# 05: Local dev depends on Docker; Neon not set up

> **✅ RESOLVED in step 6.** Neon project `frontdesk` (org `org-frosty-math-74782744`, project
> `royal-wind-94847579`, branch `production`, region `aws-us-east-2`) provisioned via the
> `neon` CLI (`neon login`, `neon link`, `neon connection-string`). Both the pooled and direct
> connection strings are saved locally in `backend/.env.neon` (gitignored). `alembic upgrade
> head` and `python seed.py` were run against the **direct** URL; Vercel's `DATABASE_URL` env
> var uses the **pooled** one. Verified end-to-end against the pooled connection locally
> (health checked 5x in a row, login, ticket list, cron) to confirm `prepare_threshold=None`
> actually prevents the "_pg3_0 does not exist" failure against Neon's real PgBouncer pooler,
> not just in theory. Local Docker Postgres (`frontdesk-pg`) is kept for day-to-day dev/tests;
> it's unrelated to and doesn't block the live deployment anymore.
>
> **Update:** the Neon-Managed Vercel integration (Neon Console → Integrations → Vercel) was
> also connected afterward, from the dashboard. It added its own `DATABASE_URL` /
> `DATABASE_URL_UNPOOLED` as **Development**-environment Config vars (for local `vercel dev` /
> `vercel env pull`, which this repo doesn't use) and one `DATABASE_URL_UNPOOLED` in
> **Production**. It left the Production `DATABASE_URL` Secret set manually in this step
> untouched. Re-confirmed live afterward: health, login, and the ticket list (11 tickets —
> 10 seeded + the one from the step-6 smoke test — same database, no redeploy needed).

**What:** The backend and tests currently use a local Docker container:
- container `frontdesk-pg`, port **5433**, user and password `frontdesk`
- databases `frontdesk` (dev) and `frontdesk_test` (pytest)

**Impact:**
- Docker Desktop must be running, or migrations, seed and tests fail to connect.
- No hosted database exists yet, so the live URL is blocked.

**Restart after a reboot:**
```bash
docker start frontdesk-pg
```

**Fix (step 6):**
1. Create a Neon project and copy the **pooled** connection string.
2. Set `DATABASE_URL` in Vercel's environment variables (never commit it).
3. Run `alembic upgrade head` and `python seed.py` once against Neon from your machine.
4. Optionally create a Neon branch for `TEST_DATABASE_URL`.
