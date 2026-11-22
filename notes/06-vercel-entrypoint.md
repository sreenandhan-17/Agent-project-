# 06: No Vercel entrypoint yet

**What:** The planned `/api/index.py` and `vercel.json` don't exist yet (PROJECT_SUMMARY.md §9).

**Impact:** The app can't be deployed until they're added. This is planned for step 6.

**Fix (step 6):**
- `api/index.py`: add `backend/` to `sys.path` and import `app.main:app`.
- `vercel.json`: build the frontend from `/frontend` (output `frontend/dist`), rewrite `/api/(.*)` to the Python function, and add the cron entry for `/api/cron/auto-close`.
- Root `requirements.txt`, which Vercel reads, pointing to `backend/requirements.txt` (production dependencies only).
- Set `JWT_SECRET` and `CRON_SECRET` in Vercel.
