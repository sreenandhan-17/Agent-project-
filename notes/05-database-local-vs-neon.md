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
