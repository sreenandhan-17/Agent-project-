# 09: The 7-day reopen window isn't enforced, and reopened tickets keep their old deadline

> **✅ RESOLVED in step 7.** The 7-calendar-day window check and the fresh resolution deadline
> both live inside `transition()` itself (raises `ReopenWindowExpired` for `to_status is
> REOPENED` past the window), so `PATCH /status`, the new `POST /{id}/reopen`, and customer
> replies all enforce it the same way — there's one code path, not three that could diverge.
> `reopen()` is a thin, readable wrapper around `transition(..., REOPENED, ...)`.
> `create_follow_up()` opens a new ticket (`parent_ticket_id` set, same priority,
> `needs_triage=true`) when a customer reply arrives past the window; `FOLLOW_UP_CREATED` is
> audited on the old ticket, `TICKET_CREATED` on the new one. Boundary tested at exactly 7 days
> (succeeds) and 7 days + 1 second (rejected). Tests: `tests/test_reopen_and_followup.py` (20).

**Found in:** step 3
**Severity:** 🟠 Business rule gap
**Fixed in:** step 7 (auto-close + reopen)

**What:** `transition()` allows `RESOLVED → REOPENED` and `CLOSED → REOPENED` at any time, and keeps the original `resolution_due_at`.

**Rule (PROJECT_SUMMARY.md §3.5):**
- A ticket can be reopened only within **7 calendar days of `resolved_at`** (or `closed_at` if it was never resolved).
- After that window, a customer reply creates a **new ticket** with `parent_ticket_id` set (`FOLLOW_UP_CREATED`).
- A reopened ticket gets a **new resolution deadline counted from when it was reopened**.

**Note:** `transition()` currently clears `resolved_at` when a ticket is reopened. Step 7 must check the window **before** that happens.

**Fix (step 7):** add `reopen(session, ticket, actor, now)` in `services/tickets.py`. It checks the window, calls `transition()`, and resets the resolution deadline from the reopen time. Add a `create_follow_up()` for replies after the window. Route `POST /api/tickets/{id}/reopen` and customer replies through them.
