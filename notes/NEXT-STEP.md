# Next step: Build step 7, auto-close + reopen window

Source of truth: PROJECT_SUMMARY.md §3.4, §3.5. This step closes **notes 09 and 17**.

## What to build

1. **Auto-close cron job** (`app/routers/cron.py: auto_close`, replacing today's stub):
   - Find tickets in `WAITING_ON_CUSTOMER` or `RESOLVED` where 5 working days (2,700 working
     minutes) have passed since `paused_at` / `resolved_at` with no customer reply.
   - Move each to `CLOSED` via `transition()`, actor = `Actor.system()`, audit action
     `AUTO_CLOSED` (add this to `AuditAction` if not already present — check `models.py`).
   - Idempotent: running it twice must not double-close or double-audit.
   - Keep the `CRON_SECRET` check already in place.

2. **`reopen()`** in `services/tickets.py` (note 09):
   - Allowed only within **7 calendar days** of `resolved_at` (or `closed_at` if never
     resolved).
   - Calls `transition()` to `REOPENED`, then sets a **new** `resolution_due_at` computed from
     the reopen moment (not the original `created_at`) — reuse `compute_deadlines()` but
     anchor it on `now`, not `ticket.created_at`. Decide: does the SLA priority stay the same?
     (Recommend yes, same priority, just a new clock.)
   - Outside the window: raise a typed exception the caller turns into "create a follow-up
     instead" rather than a plain 422.

3. **`create_follow_up()`** (note 09): new `Ticket` with `parent_ticket_id` set to the old
   ticket's id, copying customer and a sensible subject/priority default (recommend: same
   priority as the parent, flagged `needs_triage` since it's effectively a fresh customer
   report). Audit `FOLLOW_UP_CREATED` on the **old** ticket, `TICKET_CREATED` on the new one.
   Link both directions in the UI (`parent_ticket_number` already exists in `TicketDetail`;
   add a `follow_up_ticket_number` the other way).

4. **Wire customer replies through these** (note 17): `add_customer_reply()` currently just
   resumes the SLA if `WAITING_ON_CUSTOMER`. Extend it:
   - `RESOLVED` or `CLOSED` within the 7-day window → `reopen()`, then add the message.
   - Outside the window → `create_follow_up()`, add the message to the **new** ticket, and
     the public API's response needs to tell the customer they're now on a new ticket number
     (the `CustomerTicketView` the reply endpoint returns should reflect the new ticket).

5. **Agent replies on closed tickets** (note 17, decided): **block them** with 409 ("reopen
   the ticket first"). Internal notes stay allowed on any status.

6. **`POST /api/tickets/{id}/reopen`** endpoint for agents, same rules as above.

## Tests

- Auto-close: a waiting ticket past 2,700 working minutes closes; one that hasn't, doesn't; a
  resolved ticket past the window closes; running the job twice is a no-op the second time;
  actor is `SYSTEM`.
- Reopen: within 7 days succeeds and sets a fresh deadline; at exactly 7 days (boundary); past
  7 days is rejected (and routes to follow-up for customer replies); `reopen_count` increments.
- Follow-up: creates a new ticket linked both ways, audits on both tickets, customer's reply
  lands on the new ticket's messages, not the old one.
- Closed-ticket replies: agent reply on CLOSED → 409; internal note on CLOSED → 201 still.
- Update `tests/test_cron.py`'s stub-response assertions for the real behavior.

## Prompt to start it

> Read CLAUDE.md, PROJECT_SUMMARY.md (§3.4, §3.5) and notes/NEXT-STEP.md. Do build step 7:
> real auto-close logic in the cron endpoint, reopen() with the 7-day window and a fresh
> deadline, create_follow_up() for replies after the window, and block agent replies on closed
> tickets (note 17, decided: block). Log any new issues as separate numbered files in notes/.
> Run pytest and show the output; if all pass, tick item 7, mark notes 09 and 17 resolved,
> update notes/NEXT-STEP.md for step 8, commit "Step 7: auto-close + reopen" and push to main.
