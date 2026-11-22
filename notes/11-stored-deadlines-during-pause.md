# 11: While a ticket is paused, its stored deadlines don't include the current pause

> **✅ RESOLVED in step 5.** `app/sla/state.py: sla_state()` returns `paused` (grey) whenever `paused_at` is set or the status is WAITING_ON_CUSTOMER, whatever the stored deadline says. RESOLVED and CLOSED return `done`. The Late view (`app/services/queries.py: late_condition`) only counts NEW, OPEN and REOPENED tickets that aren't paused and whose tracked deadline has passed. Tests: `test_waiting_is_paused_even_when_stored_deadline_passed`, `test_waiting_ticket_is_never_late`, and `test_late_view_matches_red_badges` (Late view and red badges always agree).

**Found in:** step 3
**Severity:** 🟡 Affects the "Late" filter and SLA badges
**Fixed in:** step 5 (UI and list filters)

**What:** `paused_minutes` only grows when a pause **ends** (§3.3). While a ticket is in `WAITING_ON_CUSTOMER`, its `resolution_due_at` still reflects past pauses only. After a long wait it can look overdue even though the clock is stopped.

**Impact:** The list's **Late** filter, sorting by due date, and the red badge would wrongly flag waiting tickets.

**Fix (step 5):**
- **Late** = `resolution_due_at < now() AND status NOT IN ('WAITING_ON_CUSTOMER','RESOLVED','CLOSED')`. For the first reply, `first_response_at IS NULL AND first_response_due_at < now()` (also excluding waiting tickets).
- The badge shows **grey "paused"** whenever `paused_at IS NOT NULL`, ignoring the stored deadline.
- Optionally show "would be due" as `deadlines_for(..., paused_minutes + working_minutes_between(paused_at, now))`.

**Done when:** a test shows a ticket that has been waiting a long time isn't in the Late list.
