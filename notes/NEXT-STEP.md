# Next step: Build step 8, README + "what I didn't finish" note

Source of truth: PROJECT_SUMMARY.md §11 (Deliverables) and build step 8. This closes **note 07**
and is the last build step.

## What to build

The root `README.md` already has a **"Decisions & assumptions"** section (from steps 4–5).
Keep that, and add above/around it:

1. **Local setup**, exact commands, in order:
   - prerequisites: Python 3.12, Node, and either Docker (local Postgres) or a Neon account
   - `backend/.env` from `.env.example` (note the `ENV=dev` / secret-length rules from note 13)
   - `alembic upgrade head`, `python seed.py` (mention the demo password `frontdesk-demo`)
   - `uvicorn app.main:app --reload` and `npm run dev` (with the Vite proxy already pointing at
     `localhost:8000`)
   - `pytest` (mention `TEST_DATABASE_URL` gets wiped and rebuilt every run — never point it at
     anything real)
2. **Deployment** — point at `DEPLOY.md` rather than duplicating it; one line on the live URL
   and that it auto-deploys from `main` now (step 6).
3. **"What I didn't finish"** — a short, honest list. Pull straight from `notes/README.md`'s
   still-open rows rather than re-discovering them:
   - note 14: honeypot is in, but no per-IP rate limit on the public endpoints
   - note 19: the ticket list is capped at 200 rows with no pagination
   - note 21: a customer reloading an old, superseded ticket's link doesn't see that a
     follow-up was created (they only find out by replying, which then redirects them)
   - anything else still open in `notes/README.md` at the time this step runs
4. Double-check every command in the README actually works by running it fresh (or at least
   each step unmistakably matches what the backend/frontend expect right now).

## Not tests this time

This step is documentation, not code — no new pytest files expected. Still run the full suite
once at the end to confirm the written instructions describe a codebase that actually passes.

## Prompt to start it

> Read CLAUDE.md, PROJECT_SUMMARY.md §11 and notes/NEXT-STEP.md. Do build step 8: finish the
> root README.md (local setup, deployment pointer to DEPLOY.md, a short honest "what I didn't
> finish" list sourced from notes/README.md's open rows) without disturbing the existing
> "Decisions & assumptions" section. Run pytest once to confirm the instructions are accurate.
> Tick item 8, commit "Step 8: README + what's left" and push to main. This is the last build
> step — after this, mention that PROJECT_SUMMARY.md's checklist is fully ticked.
