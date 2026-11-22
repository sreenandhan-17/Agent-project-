# 13: `JWT_SECRET` silently falls back to a hard-coded default

> **✅ RESOLVED.** `app/config.py` no longer has defaults for `JWT_SECRET` or `CRON_SECRET`. Built-in dev secrets are used only when `ENV=dev`; anything else, including an unset `ENV`, counts as production. Both secrets must be at least 32 characters, even in dev. `app/main.py` loads the settings when it is imported, so a bad configuration stops startup with: `Invalid configuration: JWT_SECRET is not set (required unless ENV=dev). Generate a secret with: ...`. `hide_input_in_errors=True` keeps secrets and the database password out of that error. `backend/.env` now has `ENV=dev` and fresh 64-character secrets; `.env.example` documents this. Tests: `tests/test_config.py` (12 tests). For deploy (step 6): set `JWT_SECRET` and `CRON_SECRET` in Vercel and do **not** set `ENV=dev` there.

**Found in:** step 4
**Severity:** 🔴 Security, must fix before deploy
**Fixed in:** step 6 (deploy)

**What:** `app/config.py` has `jwt_secret: str = "dev-only-secret"`. If `JWT_SECRET` isn't set on Vercel, the app still starts, and anyone who reads the public repo can create a valid token for any agent. `CRON_SECRET` has the same problem.

**Fix:**
- Remove the defaults so the settings fail to load when the variables are missing. Or keep the defaults only when an `ENV=dev` variable is set.
- Reject secrets shorter than 32 bytes (PyJWT also warns about short HMAC keys).
- Generate production values with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and set them in Vercel.

**Done when:** starting the app without `JWT_SECRET` in production mode fails with a clear error.
