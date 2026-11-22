# 07: No README / local setup docs

> **✅ RESOLVED in step 8.** Root `README.md` now has: the live URL and demo logins; a 5-minute
> walkthrough exercising INC-0291/0304/0318 and the SLA pause; a table mapping each incident to
> its mechanism, file and tests; an SLA rules summary; the full "Decisions & assumptions" section
> (kept from steps 4–5, plus new notes on agent session storage, reopen/follow-up/auto-close);
> the tech stack; exact, verified local-setup commands (every command checked to actually exist,
> e.g. `venv/Scripts/pytest.exe`); a pointer to `DEPLOY.md`; and an honest "what I didn't finish"
> list sourced from `notes/README.md`'s still-open rows (14, 19, 21, the daily-cron limit, and
> that email is logged rather than sent).

**What:** There's no root `README.md`. Local setup is only described in these notes.

**Impact:** The README is a required deliverable, and a reviewer can't run the project without one.

**Fix (step 8):** Write a README covering:
- prerequisites (Python 3.12, Node, Docker or Neon)
- `.env` setup, `alembic upgrade head`, `python seed.py`, `uvicorn app.main:app`, and `npm run dev`
- `pytest`
- demo logins (password `frontdesk-demo`)
- the business-rule assumptions from PROJECT_SUMMARY.md §3
- the "what I didn't finish" note
