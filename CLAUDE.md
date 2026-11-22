# CLAUDE.md

Working instructions for **Frontdesk** (a support ticket system for Arvo Systems).

## Source of truth

**`PROJECT_SUMMARY.md`** holds the plan: business rules, incidents, data model, API, UI and build order. Read it before starting work. If the code and the summary disagree, raise it; don't silently pick one.

## Stack

- **Frontend:** React + Vite + TypeScript + Tailwind, in `/frontend`
- **Backend:** Python FastAPI + SQLAlchemy + Alembic, in `/backend`
- **Database:** PostgreSQL on Neon
- **Hosting:** Vercel (static frontend + Python functions via `/api/index.py`); Vercel Cron for scheduled jobs
- **Tests:** pytest against a real Postgres

## Folder layout (planned)

```
/frontend        React app
/backend/app     FastAPI app (models, sla/, services/, serializers/, routers/)
/backend/alembic migrations
/backend/tests   pytest
/api/index.py    Vercel entrypoint
vercel.json
```

## Rules (non-negotiable)

1. **Never expose INTERNAL messages outside agent endpoints.** Every customer-facing output (public API, export, email) goes through `serialize_for_customer()`. Never hand-build customer payloads.
2. **`audit_events` is append-only.** Never `UPDATE` or `DELETE` its rows, and never weaken the DB trigger. Write each audit event in the same transaction as the change it records.
3. **All SLA times use the working-hours calculator** (`backend/app/sla/working_hours.py`). No ad-hoc `timedelta` arithmetic for deadlines.
4. **Update the checklist in `PROJECT_SUMMARY.md` after each build step.**

## Conventions

- Store timestamps as UTC `timestamptz`. Convert to `Asia/Kolkata` only for working-hours math and display.
- Status changes go through `transition()`. Claims use the atomic `UPDATE ... WHERE assignee_id IS NULL`.
