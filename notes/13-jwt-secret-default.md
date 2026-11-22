# 13: `JWT_SECRET` silently falls back to a hard-coded default

**Found in:** step 4
**Severity:** 🔴 Security, must fix before deploy
**Fixed in:** step 6 (deploy)

**What:** `app/config.py` has `jwt_secret: str = "dev-only-secret"`. If `JWT_SECRET` isn't set on Vercel, the app still starts, and anyone who reads the public repo can create a valid token for any agent. `CRON_SECRET` has the same problem.

**Fix:**
- Remove the defaults so the settings fail to load when the variables are missing. Or keep the defaults only when an `ENV=dev` variable is set.
- Reject secrets shorter than 32 bytes (PyJWT also warns about short HMAC keys).
- Generate production values with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and set them in Vercel.

**Done when:** starting the app without `JWT_SECRET` in production mode fails with a clear error.
