# Frontdesk — Project Summary

> Source of truth for the build. Update the **Progress checklist** at the bottom after each step.

## 1. Overview & goal

**Frontdesk** is a support ticket system for **Arvo Systems**: 9 support agents handling roughly 40 tickets a day. It replaces the current spreadsheet + WhatsApp setup, which has caused three recorded incidents (see §4).

**Goal (hiring test, about 8 hours):** ship a working, **hosted** system that:

- tracks every ticket from intake to close, with a clear owner,
- enforces SLAs in **working time only**,
- never leaks internal notes to customers,
- keeps an audit trail that cannot be changed after the fact.

**Out of scope (on purpose):** inbound email parsing, attachments, customer accounts or passwords, reporting dashboards, real outbound email delivery (emails are rendered and logged, not sent), multi-tenancy.

## 2. Tech stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, SQLAlchemy 2.x, Alembic migrations |
| Database | PostgreSQL on **Neon** (use the pooled connection string, `NullPool` in serverless) |
| Hosting | **Vercel**: static frontend + Python serverless functions for the API |
| Scheduled jobs | **Vercel Cron** calling a protected cron endpoint |
| Tests | pytest, run against a real Postgres (Neon branch or local Docker) because triggers and atomic `UPDATE` behaviour must be tested for real |
| Auth | Seeded agent accounts, email + password, JWT in `Authorization` header |

**Time handling:** all timestamps are stored as UTC `timestamptz`. Business-hours logic converts to `Asia/Kolkata` (no DST) inside the working-hours calculator only.

## 3. Business rules

### 3.1 SLA by priority

| Priority | First reply due | Resolution due |
|---|---|---|
| **URGENT** | 2 working hours (120 min) | Same working day (by 18:30 IST of the working day the ticket starts counting) |
| **MEDIUM** | 4.5 working hours (270 min, half a day) | 3 working days (1,620 min) |
| **LOW** | 1 working day (540 min) | 5 working days (2,700 min) |

- 1 working day = 540 working minutes (09:30–18:30).
- **First reply** = the first **PUBLIC** agent message. Internal notes do not count.
- *Assumption:* for URGENT, if the end of the working day comes before the first-reply deadline (for example, a ticket created at 17:45), the resolution deadline becomes the first-reply deadline, so resolution is never due before the first reply.
- **Who sets priority (decision, notes/15):** customers don't. A ticket submitted on the public form:
  - starts at **MEDIUM**, so the SLA clock runs on the MEDIUM targets from submission;
  - has `needs_triage = true`;
  - records the customer's stated **impact** (`customer_impact`, required on the form): `CANNOT_WORK` ("I can't work"), `PARTIAL` ("partly affected") or `QUESTION` ("just a question"). The impact is a **hint for agents only**: it never changes priority or deadlines automatically, and customers never see it or the priority.
  - **Triage = any agent's `PATCH /priority`.** It always clears `needs_triage`:
    - With a new priority, deadlines are recomputed from `created_at` (§3.6) and the change is audited as `PRIORITY_CHANGED`, with the old and new priority, flag and deadlines.
    - Confirming the current priority only clears the flag and is audited as `TRIAGED`.
  - Agent-created and seeded non-NEW tickets have `needs_triage = false` and no impact.
  - The ticket list returns `needs_triage` and `customer_impact`, and can filter with `?needs_triage=true`.

### 3.2 Working time only

- Working hours: **09:30–18:30 Asia/Kolkata, Monday–Friday**, excluding dates in the `holidays` table.
- Tickets created outside working hours start counting at the next working minute.
- Example: a LOW ticket created **Friday 18:00** has 30 min counted on Friday, and its first reply is due **Monday 18:00**. It is **not** late on Sunday.
- Example: an URGENT ticket created Friday 18:00 has its first reply due Monday 11:00.
- One module (`working_hours.py`) owns this logic:
  - `add_working_minutes(start_utc, minutes, holidays) -> datetime`
  - `working_minutes_between(a_utc, b_utc, holidays) -> int`

### 3.3 Waiting on customer pauses the SLA clock

- Moving to `WAITING_ON_CUSTOMER` sets `paused_at = now()`.
- On a customer reply (or when an agent manually resumes), add `working_minutes_between(paused_at, now)` to `paused_minutes`, clear `paused_at`, and return the ticket to `OPEN`.
- Deadlines are always derived: `due = add_working_minutes(created_at, sla_minutes + paused_minutes)`.
- While paused, the UI shows the SLA badge as grey ("paused") and the ticket is never counted as late.

### 3.4 Auto-close

- A cron job closes tickets in `WAITING_ON_CUSTOMER` or `RESOLVED` after **5 working days** (2,700 working minutes) with no customer reply. The clock counts from `paused_at` or `resolved_at`.
- The job sets the status to `CLOSED` and writes an `AUTO_CLOSED` audit event with **actor = system**.
- The job is idempotent and safe to run more than once.
- **Implemented:** `services/tickets.py: auto_close_overdue_tickets()`, called by `GET /api/cron/auto-close` (Vercel Cron, daily). Idempotency works because a closed ticket's status no longer matches the query on the next run — no separate "already processed" flag needed.

### 3.5 Reopen

- A `RESOLVED` or `CLOSED` ticket can be reopened (by a customer reply or by an agent) **within 7 calendar days of `resolved_at`**. The status becomes `REOPENED`, `reopen_count` goes up by 1, and a new resolution deadline is computed from the reopen time using the same priority.
- After 7 days, a customer reply creates a **new ticket** with `parent_ticket_id` pointing to the old one. Both tickets get audit events, and the UI links them.
- Tickets that were closed without ever being resolved (for example, auto-closed while waiting) follow the same rule, measured from `closed_at`.
- **Implemented:** the window check lives inside `transition()` itself (raises `ReopenWindowExpired` targeting `REOPENED`), so `PATCH /status`, `POST /reopen` and customer replies all enforce it identically — there's exactly one code path, not three that could drift apart. Only the resolution deadline is recomputed on reopen; `first_response_at`/`first_response_due_at` are left as they were (that target was already met earlier in the ticket's life). A customer reply past the window creates a follow-up via `create_follow_up()`; an agent past the window just gets a clear 409 (agents have no auto-follow-up path).

### 3.6 Priority change mid-way

- Recompute both deadlines **from `created_at`** with the new priority's SLA, plus `paused_minutes`.
- The ticket may become **breached immediately** (for example, LOW changed to URGENT on a 2-day-old ticket). That is expected.
- Write a `PRIORITY_CHANGED` audit event with the old and new priority **and** the old and new deadlines.
- Document this behaviour in the README.

## 4. Incidents & fixes

### INC-0291 — Two agents claimed the same ticket

**Fix: atomic claim.**

```sql
UPDATE tickets
   SET assignee_id = :me, status = 'OPEN', updated_at = now()
 WHERE id = :id AND assignee_id IS NULL
RETURNING id;
```

- 1 row: claimed (200), plus a `CLAIMED` audit event in the same transaction.
- 0 rows: re-read the ticket. If it is already mine, return 200 (idempotent). Otherwise return **HTTP 409 Conflict** with the current assignee's name.
- **Only the assignee can send a public reply** (otherwise 403). Any agent can add an internal note.
- **Who may change what** (decision, notes/10):
  - **Status** (`PATCH /status`): only the **assignee** or an **ADMIN**, otherwise 403. One exception: **any agent may close a NEW, unassigned ticket** (spam or duplicate) without claiming it.
  - **Priority** (`PATCH /priority`): **any active agent**, so leads can triage unassigned tickets. Every change is audited with the old and new deadlines.
  - The permission check runs before transition validation: a non-assignee gets 403, not 422.
- Test: two concurrent sessions claim the same ticket; exactly one gets 200 and the other gets 409.

### INC-0304 — An internal note leaked to a customer

**Fix: visibility enforced on the server.**

- `messages.visibility` is `PUBLIC` or `INTERNAL`.
- Separate endpoints (`/replies` vs `/notes`) and separate UI boxes. Internal notes are styled **yellow** everywhere.
- **One** server-side serializer, `serialize_for_customer()`, is the only path to any customer-facing output: public API, customer ticket list, transcript export, and rendered email. It drops `INTERNAL` messages, and it is not optional.
- Tests:
  - Seed an internal note containing a sentinel string, call every customer-facing endpoint plus the export and email renderer, and assert the sentinel never appears.
  - A route-inventory test fails if a new `/api/public/*` route is added without being covered.

### INC-0318 — No proof of who did what

**Fix: append-only audit log.**

- `audit_events` stores actor (type + id), action, field, old value, new value, and a **server timestamp** (`DEFAULT now()`; client-supplied values are ignored).
- A Postgres **trigger** raises an exception on `UPDATE`, `DELETE` and `TRUNCATE` of `audit_events`.
- Every state change writes its audit event **in the same transaction** as the change.
- The ticket detail page shows the timeline.
- Test: an `UPDATE` or `DELETE` on `audit_events` raises an error.

## 5. Ticket statuses

`NEW`, `OPEN`, `WAITING_ON_CUSTOMER`, `RESOLVED`, `CLOSED`, `REOPENED`

| From | Allowed to | Trigger |
|---|---|---|
| NEW | OPEN | Agent claims the ticket |
| NEW | CLOSED | Agent closes it (spam or duplicate) |
| OPEN | WAITING_ON_CUSTOMER | Agent is waiting on the customer (pauses SLA) |
| OPEN | RESOLVED | Agent resolves |
| WAITING_ON_CUSTOMER | OPEN | Customer replies, or agent resumes (resumes SLA) |
| WAITING_ON_CUSTOMER | RESOLVED | Agent resolves |
| WAITING_ON_CUSTOMER | CLOSED | System auto-close (5 working days) |
| RESOLVED | CLOSED | System auto-close, or agent |
| RESOLVED | REOPENED | Customer reply or agent, within 7 days |
| CLOSED | REOPENED | Customer reply or agent, within 7 days of resolution |
| REOPENED | WAITING_ON_CUSTOMER, RESOLVED | Same as OPEN |

Any other transition returns **HTTP 422**. All transitions go through one function, `transition(ticket, to_status, actor)`, which validates the transition, applies pause and resume, and writes the audit event.

**Who may trigger an agent transition:** the ticket's **assignee** or an **ADMIN** (403 otherwise). The exception is **NEW (unassigned) → CLOSED**, which any agent may do for spam or duplicates. NEW → OPEN happens through the claim, not `PATCH /status`. System (auto-close) and customer (reply) transitions are not agent requests and are not subject to this rule. See §4.

## 6. Data model (key columns)

**agents:** `id`, `name`, `email` (unique), `password_hash`, `role` (`AGENT` | `ADMIN`), `is_active`, `created_at`

**customers:** `id`, `name`, `email` (unique), `phone`, `company`, `created_at`

**tickets:**
- `id`, `number` (human-readable, e.g. `FD-1042`), `subject`, `customer_id` (FK), `assignee_id` (FK, nullable), `status`, `priority`
- `created_at`, `updated_at`
- `first_response_at`, `first_response_due_at`, `resolution_due_at` (derived values, stored for filtering and sorting)
- `paused_at` (nullable), `paused_minutes` (int, default 0)
- `last_customer_reply_at`, `resolved_at`, `closed_at`, `reopen_count`
- `parent_ticket_id` (FK to tickets, nullable, for follow-ups after the reopen window)
- `needs_triage` (bool, default false; true for customer-submitted tickets until an agent sets priority; partial index), `customer_impact` (`CANNOT_WORK` | `PARTIAL` | `QUESTION`, nullable): see §3.1
- `public_token` (unguessable token for the customer view)
- Indexes on `(status)`, `(assignee_id)`, `(resolution_due_at)`

**messages:** `id`, `ticket_id` (FK), `author_type` (`AGENT` | `CUSTOMER` | `SYSTEM`), `author_agent_id`, `author_customer_id`, `visibility` (`PUBLIC` | `INTERNAL`), `body`, `created_at`

**audit_events** (append-only): `id`, `ticket_id` (nullable), `actor_type` (`AGENT` | `CUSTOMER` | `SYSTEM`), `actor_id` (nullable for system), `action`, `field`, `old_value` (jsonb), `new_value` (jsonb), `created_at` (`DEFAULT now()`, set by the server)
- Actions: `TICKET_CREATED`, `CLAIMED`, `STATUS_CHANGED`, `PRIORITY_CHANGED`, `REPLY_SENT`, `NOTE_ADDED`, `CUSTOMER_REPLIED`, `SLA_PAUSED`, `SLA_RESUMED`, `AUTO_CLOSED`, `REOPENED`, `FOLLOW_UP_CREATED`, `TRIAGED`

**holidays:** `date` (PK), `name`

## 7. API endpoints

All routes are under `/api`. Agent routes require a JWT. Public routes use the ticket's `public_token` and **always** go through `serialize_for_customer()`.

**Auth**
- `POST /api/auth/login`: email and password, returns a JWT
- `GET /api/auth/me`

**Agent: tickets**
- `GET /api/tickets?view=mine|unassigned|late|waiting&status=&priority=&needs_triage=&q=`: ticket list with SLA state, `needs_triage` and `customer_impact`
- `POST /api/tickets`: agent logs a ticket on behalf of a customer (phone or WhatsApp intake)
- `GET /api/tickets/{id}`: detail including internal notes, SLA state and linked tickets
- `GET /api/tickets/{id}/timeline`: audit events
- `POST /api/tickets/{id}/claim`: atomic claim, returns 200 or 409
- `POST /api/tickets/{id}/replies`: PUBLIC reply, assignee only (403 otherwise); 409 if the ticket is CLOSED (reopen first — RESOLVED is still allowed)
- `POST /api/tickets/{id}/notes`: INTERNAL note, any agent
- `PATCH /api/tickets/{id}/status`: `{ "status": ... }`, validated transition
- `PATCH /api/tickets/{id}/priority`: recomputes deadlines (§3.6)
- `POST /api/tickets/{id}/reopen`: within 7 calendar days of resolution/closure (409 otherwise). Same rule as `PATCH /status` targeting `REOPENED` — both go through the same `transition()` logic, so they can't diverge. Agents don't get an auto-created follow-up; only customer replies do (see below)
- `GET /api/tickets/{id}/export`: customer transcript (customer serializer, no internal notes)

**Public (customer-facing)**
- `POST /api/public/tickets`: customer submits a ticket (creates the customer record if new)
- `GET /api/public/tickets/{token}`: customer view of the ticket and its public messages
- `POST /api/public/tickets/{token}/replies`: customer reply. Resumes the SLA, or reopens the ticket, or creates a follow-up ticket.

**Admin**
- `GET /api/holidays`, `POST /api/holidays`, `DELETE /api/holidays/{date}`

**System**
- `GET /api/cron/auto-close`: called by Vercel Cron. Requires `Authorization: Bearer $CRON_SECRET`.
- `GET /api/health`

## 8. Agent UI

**Login page.**

**Ticket list**
- Filter tabs: **Mine**, **Unassigned**, **Late**, **Waiting on customer**, **Needs triage** (plus All). Search by number, subject or customer. Auto-refresh every 30 seconds.
- Columns: number, subject, customer, priority, status, assignee, and **SLA badge**.
- SLA badge (for the next pending deadline: first reply if none has been sent yet, otherwise resolution):
  - **Red:** breached
  - **Amber:** less than 25% of the SLA budget remaining
  - **Green:** on track
  - **Grey:** paused (waiting on customer)
- Badge tooltip shows the due time in IST and the working time remaining.

**Ticket detail**
- Header: subject, customer, status and priority controls, assignee, SLA badges for first reply and resolution, and a link to the parent or child ticket.
- **Take ticket** button when unassigned. A 409 shows "Already taken by X" and refreshes the page.
- **Conversation:** public messages, with internal notes inline in **yellow** cards labelled "Internal note".
- **Reply box** (public): enabled only for the assignee. For everyone else it shows "Take the ticket to reply."
- **Internal note box:** separate, yellow, always available to agents.
- **Timeline tab:** audit events with actor, action, old → new value, and server timestamp.

## 9. Planned folder layout

```
/frontend          Vite + React + TS + Tailwind app
/backend
  app/
    main.py        FastAPI app
    db.py          engine/session (NullPool for serverless)
    models.py      SQLAlchemy models
    sla/working_hours.py
    services/      tickets.py (transition, claim), audit.py, autoclose.py
    serializers/   customer.py (serialize_for_customer), agent.py
    routers/       auth, tickets, public, holidays, cron
  alembic/         migrations (incl. audit trigger)
  tests/
/api/index.py      Vercel entrypoint that imports backend.app.main:app
vercel.json        rewrites + cron schedule
```

## 10. Build order

1. **Schema + audit:** models, Alembic migration, append-only trigger, seed data (agents, customers, holidays).
2. **Working-hours calculator + tests:** weekends, holidays, after-hours start, the Friday 18:00 case, multi-day spans.
3. **Status, pause, resume:** `transition()`, the transition table, SLA pause and resume, priority change and recompute.
4. **Claim + note separation:** atomic claim with 409, assignee-only replies, `serialize_for_customer()`, and the leak test.
5. **UI:** login, ticket list with filters and badges, ticket detail with conversation, timeline, Take ticket, Reply and Internal note boxes.
6. **Deploy:** Vercel project, Neon database, environment variables, migrations run against Neon, smoke test on the live URL.
7. **Auto-close + reopen:** cron endpoint and schedule, 7-day reopen window, follow-up ticket linking.
8. **README + "what I didn't finish" note.**

## 11. Deliverables

- **Live URL** on Vercel, kept up for **1 week** after submission, with demo agent logins in the README.
  **Live:** https://frontdesk-mu-neon.vercel.app (Vercel project `frontdesk` + Neon project `frontdesk`, region `aws-us-east-2`). See `DEPLOY.md`.
- **Repository** with the full source.
- **README:** local setup (Postgres, environment variables, `alembic upgrade head`, seed, run backend and frontend, run tests), deployment notes, and the business-rule decisions and assumptions from §3.
- **Short note:** what was finished, what wasn't, and what I would do next.

## 12. Progress checklist

- [x] 1. Schema + audit (models, migration, append-only trigger, seed)
- [x] 2. Working-hours calculator + tests
- [x] 3. Status transitions, SLA pause/resume, priority recompute
- [x] 4. Atomic claim (409) + PUBLIC/INTERNAL separation + leak test
- [x] 5. Agent UI (list, filters, SLA badges, detail, timeline, reply/note boxes)
- [x] 6. Deploy to Vercel + Neon, live URL working
- [x] 7. Auto-close cron + reopen window + follow-up tickets
- [ ] 8. README + "what I didn't finish" note
