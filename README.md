# Frontdesk

A support ticket system for Arvo Systems: 9 agents, ~40 tickets a day, replacing a spreadsheet and WhatsApp with SLA tracking, an audit trail, and a customer portal. The full plan is in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md); open issues are tracked in [notes/](notes/README.md); a short summary of what's finished and what isn't is in [COMPLETION_NOTE.md](COMPLETION_NOTE.md).

## Live demo

**https://frontdesk-mu-neon.vercel.app**

**Agent login IDs** (all 9, from `backend/seed.py`):

| Name | Email (login ID) | Role |
|---|---|---|
| Ananya Rao | `ananya@arvo.example` | Admin |
| Rahul Menon | `rahul@arvo.example` | Agent |
| Priya Nair | `priya@arvo.example` | Agent |
| Vikram Shah | `vikram@arvo.example` | Agent |
| Meera Iyer | `meera@arvo.example` | Agent |
| Arjun Pillai | `arjun@arvo.example` | Agent |
| Sneha Kulkarni | `sneha@arvo.example` | Agent |
| Karthik Reddy | `karthik@arvo.example` | Agent |
| Divya Joshi | `divya@arvo.example` | Agent |

Demo password is shared privately with reviewers in the submission note.

**Customer:** no login — open [`/new`](https://frontdesk-mu-neon.vercel.app/new) to submit a ticket.

## Try it in 5 minutes

1. **As a customer:** open [`/new`](https://frontdesk-mu-neon.vercel.app/new), submit a ticket with impact **"I can't work at all"**. You land on `/t/{token}` — keep that link, it's your private way back in.
2. **As an agent:** log in. The ticket shows up under **Unassigned** and **Needs triage**. Set its priority (this clears the triage flag) and click **Take ticket**.
3. **As a second agent**, in another browser (or an incognito window): open the same ticket and click **Take ticket**. You'll get *"Already taken by \<name\>"* — this is the atomic-claim fix for **INC-0291**.
4. **Back as the first agent:** add an **internal note**, then send a **public reply**. Refresh your customer `/t/{token}` tab — only the reply is there; the note never appears. This is **INC-0304**.
5. Open the ticket's **Timeline** tab: every action is listed with who did it and a server timestamp nobody could have backdated — **INC-0318**.
6. Set the status to **Waiting on customer**: the SLA badge turns grey ("Paused"), and the ticket stops being counted as late while it waits.

## How each incident is fixed

| Incident | Mechanism | Where | Proven by |
|---|---|---|---|
| **INC-0291** — two agents claimed the same ticket | One conditional `UPDATE ... WHERE assignee_id IS NULL`; 0 rows updated → re-check and return 409 with the current owner's name | `backend/app/services/tickets.py: claim()`, route in `backend/app/routers/tickets.py` | `tests/test_claim_and_messages.py::test_two_simultaneous_http_claims_one_wins`, `::test_claim_blocked_mid_transaction_loses`, `::test_claim_of_taken_ticket_is_409_with_name` |
| **INC-0304** — an internal note leaked to a customer | One serializer, `serialize_for_customer()`, built from an explicit field **allow-list** (not a deny-list); every customer-facing route, the transcript export and the email renderer all go through it, nothing else | `backend/app/serializers/customer.py`, used by `backend/app/routers/public.py`, `routers/tickets.py` (export), `services/email.py` | `tests/test_no_leaks.py::test_no_customer_facing_output_contains_internal_note`, `::test_customer_view_is_exactly_the_allow_list`, `::test_every_public_route_is_leak_tested` |
| **INC-0318** — no proof of who did what | `audit_events` is append-only: a Postgres trigger raises on `UPDATE`/`DELETE`/`TRUNCATE`, and `created_at` is always the server's clock, never a client-supplied value | Trigger in `backend/alembic/versions/0001_initial_schema.py`; writes via `backend/app/services/audit.py: record()` | `tests/test_audit_append_only.py::test_update_is_blocked`, `::test_delete_is_blocked`, `::test_truncate_is_blocked`, `::test_client_supplied_timestamp_is_ignored` |

## SLA rules summary

| Priority | First reply due | Resolution due |
|---|---|---|
| **URGENT** | 2 working hours | End of the same working day (never before the first-reply deadline) |
| **MEDIUM** | 4.5 working hours (half a working day) | 3 working days |
| **LOW** | 1 working day | 5 working days |

- **Working hours only:** 09:30–18:30 Asia/Kolkata, Monday–Friday, skipping the holidays in the `holidays` table. A ticket logged Friday evening doesn't age over the weekend.
- **Waiting on customer** pauses both deadlines; the paused working minutes are added back when the ticket resumes.
- **Changing priority** recomputes both deadlines from the ticket's original `created_at` — it can make a ticket instantly late, which is correct and expected.
- **Reopen:** a resolved or closed ticket can be reopened within **7 calendar days**, with a fresh resolution deadline from the moment it's reopened. After 7 days, a customer reply opens a new, linked follow-up ticket instead.
- **Auto-close:** a daily job closes anything left `WAITING_ON_CUSTOMER` or `RESOLVED` for **5 working days** with no customer reply.

## Decisions & assumptions

Business-rule choices that PROJECT_SUMMARY.md left open, and how they were settled.

### Permissions
- **Public replies:** only the ticket's assignee (403 otherwise). Agents must **Take ticket** first. Blocked entirely once a ticket is **CLOSED** (409 — reopen first); still allowed on **RESOLVED**, since only CLOSED is truly terminal. Internal notes are never blocked, on any status.
- **Internal notes:** any agent.
- **Status changes** (`PATCH /api/tickets/{id}/status`): only the **assignee** or an **ADMIN** (403 otherwise). The permission check runs before the transition check, so a non-assignee gets 403, not 422.
  - **Exception:** any agent may **close a NEW, unassigned ticket** (spam or duplicate) without claiming it.
  - Moving a ticket from NEW to OPEN happens by claiming it, not through `PATCH /status`.
- **Priority changes** (`PATCH /api/tickets/{id}/priority`): **any active agent**, so leads can triage unassigned tickets. Every change is audited with the old and new priority and deadlines.

### Triage (who sets priority)
- Customers **don't choose priority**. Public-form tickets start at **MEDIUM** with `needs_triage = true`, so the SLA clock runs from submission.
- The form asks for **impact** (*I can't work* / *partly affected* / *just a question*). This is a hint for agents only and never changes priority automatically.
- Any agent's priority change is the triage decision and clears the flag. Confirming the current priority is logged as `TRIAGED`; a new priority is logged as `PRIORITY_CHANGED`, with deadlines recomputed and possibly breached immediately.

### Customer portal
- Customers use **`/new`** to contact support and **`/t/{token}`** to follow and reply. The token is an unguessable private link; the portal has no customer accounts or passwords.
- The portal only ever shows the server's customer view: public messages, the support team name instead of agent names, and status in customer wording.
- **Spam:** a hidden honeypot field silently drops bot submissions. There's no rate limit yet (notes/14).
- Email links are absolute: `{PUBLIC_BASE_URL}/t/{token}`.

### Agent session
- The agent frontend keeps its JWT in `sessionStorage` (survives a refresh, gone when the tab closes), never in `localStorage` or a cookie. Any 401 response clears it and redirects to `/login`. Message bodies are rendered as plain React text, never as HTML, so there's no injection path through a ticket body or note.

### Reopen, follow-ups and auto-close
- The 7-day reopen window and the fresh resolution deadline both live inside one function, `transition()`, so `PATCH /status`, `POST /{id}/reopen`, and a customer's own reply all enforce the exact same rule — there's one code path, not three that could quietly drift apart.
- Only **customer** replies past the window get an automatic follow-up ticket; an agent trying to reopen past the window just gets a clear error. Agents have no API for creating a follow-up on someone else's behalf.
- **Vercel's Hobby plan runs at most one cron schedule a day**, so auto-close is checked once daily (03:30 UTC) rather than continuously — a ticket can sit up to ~24 hours past its exact 5-working-day mark before the job catches it. Good enough for a 40-ticket-a-day desk; a paid plan would allow hourly.

### SLA
- Working time is 09:30–18:30 Asia/Kolkata, Mon–Fri, excluding the 2026 Central Government gazetted holidays (DoPT list, notes/02).
- **URGENT "same working day":** resolve by 18:30 IST of the day the ticket starts counting, but never before the first-reply deadline (for example, a ticket created at 17:45 is due the next morning).
- **First response:** the first **public** agent reply. Internal notes don't count.
- **Waiting on customer:** pauses both clocks. The paused *working* minutes push both deadlines later when the ticket resumes.
- **Priority change:** deadlines are recomputed from `created_at` with the new priority, plus paused time. A ticket can be breached immediately.

## Tech stack

- **Frontend:** React + Vite + TypeScript + Tailwind, in `/frontend`
- **Backend:** Python FastAPI + SQLAlchemy + Alembic, in `/backend`
- **Database:** PostgreSQL on Neon (local dev uses Docker instead)
- **Hosting:** Vercel — static frontend + the backend as one Python function (`/api/index.py`), Vercel Cron for the daily auto-close job
- **Tests:** pytest, against a real Postgres (never SQLite — the append-only trigger and the atomic claim are genuinely Postgres-specific)

## Local setup

**Prerequisites:** Python 3.12, Node.js, and either Docker Desktop (for a local Postgres) or a Neon account.

```bash
# 1. Start Postgres (first time: creates the container; after that, `docker start frontdesk-pg`)
docker run -d --name frontdesk-pg \
  -e POSTGRES_USER=frontdesk -e POSTGRES_PASSWORD=frontdesk -e POSTGRES_DB=frontdesk \
  -p 5433:5432 postgres:16
docker exec frontdesk-pg psql -U frontdesk -c "CREATE DATABASE frontdesk_test"

# 2. Backend: environment
cd backend
cp .env.example .env
# Edit .env: DATABASE_URL=postgresql://frontdesk:frontdesk@localhost:5433/frontdesk
#            TEST_DATABASE_URL=postgresql://frontdesk:frontdesk@localhost:5433/frontdesk_test
#            ENV=dev (this allows the pre-filled dev-only JWT_SECRET/CRON_SECRET to stay as-is;
#            outside of ENV=dev, both must be real secrets at least 32 characters long)

# 3. Backend: install, migrate, seed, run
python -m venv venv
./venv/Scripts/pip install -r requirements.txt      # Windows; use venv/bin/pip on macOS/Linux
./venv/Scripts/alembic upgrade head
./venv/Scripts/python seed.py                       # 9 agents, 5 customers, holidays, demo tickets
./venv/Scripts/uvicorn app.main:app --reload --port 8000

# 4. Frontend, in a second terminal (proxies /api to localhost:8000 — see vite.config.ts)
cd frontend
npm install
npm run dev                                         # http://localhost:5173

# 5. Tests, from /backend
./venv/Scripts/pytest
```

Log in at `http://localhost:5173/login` with any seeded agent email above; the password is whatever you passed to `DEMO_AGENT_PASSWORD` when seeding (or the dev-only placeholder `seed.py` prints if you left it unset with `ENV=dev`). The customer portal is at `http://localhost:5173/new`.

⚠️ **`TEST_DATABASE_URL`, if set, is wiped and rebuilt from scratch on every pytest run.** Point it at a disposable database, never at `DATABASE_URL` or anything with real data. Leaving it unset is fine — tests then run against `DATABASE_URL` inside a transaction that's always rolled back.

To use Neon instead of Docker for local dev, just put a Neon connection string in `DATABASE_URL`; everything else is identical.

## Deployment

Full steps — Neon setup, Vercel environment variables, migrations, smoke tests — are in **[DEPLOY.md](DEPLOY.md)**.

In short: the Vercel project is Git-connected to this repo's `main` branch, so every push **builds and deploys automatically** — no manual `vercel deploy` needed. Database migrations are the one thing that still has to be run by hand (`alembic upgrade head` against Neon's direct connection) whenever a new revision ships.

## What I didn't finish, and why

- **No per-IP rate limit on the public endpoints** (notes/14). A hidden honeypot field stops simple bots, but nothing stops a determined script from submitting tickets or replies repeatedly. *Next:* a small per-IP counter table, or Cloudflare Turnstile on the form.
- **The ticket list is capped at 200 rows with no pagination** (notes/19). Fine at ~40 tickets/day for weeks, but the "All" view will eventually drop old closed tickets silently off the bottom. *Next:* cursor pagination, or split "All" into active vs. a separate closed-tickets tab.
- **A customer re-reading an old, superseded ticket's link doesn't know a follow-up exists** (notes/21) — they only discover it by typing a new reply, which then redirects them. Viewing the link alone shows no hint. *Next:* a small field on the customer view naming the newer ticket, or a redirecting endpoint.
- **Auto-close runs once a day, not continuously** — Vercel's Hobby plan only allows one cron schedule per day, so a ticket can sit up to ~24 hours past its exact 5-working-day mark. *Next:* a paid plan allows more frequent schedules, or an external trigger (e.g. GitHub Actions) could call the endpoint more often.
- **Outbound email is never actually sent** — by design, per the project brief (it's logged, not delivered). `render_customer_email()`/`send_customer_email()` build and log the message; wiring in a real provider (Postmark, SES) is a small, separate step.
- Anything else still open is tracked in [notes/README.md](notes/README.md), each with its own file explaining what's missing and what the fix would look like.
