# 07: No README / local setup docs

**What:** There's no root `README.md`. Local setup is only described in these notes.

**Impact:** The README is a required deliverable, and a reviewer can't run the project without one.

**Fix (step 8):** Write a README covering:
- prerequisites (Python 3.12, Node, Docker or Neon)
- `.env` setup, `alembic upgrade head`, `python seed.py`, `uvicorn app.main:app`, and `npm run dev`
- `pytest`
- demo logins (password `frontdesk-demo`)
- the business-rule assumptions from PROJECT_SUMMARY.md §3
- the "what I didn't finish" note
