# 05: Local dev depends on Docker; Neon not set up

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
