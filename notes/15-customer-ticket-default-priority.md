# 15: Customer-submitted tickets default to MEDIUM priority

> **✅ RESOLVED (decision: option 1 + impact hint).** Migration `0002` adds `tickets.needs_triage` (bool, default false, with a partial index), `tickets.customer_impact` (`CANNOT_WORK`/`PARTIAL`/`QUESTION`, nullable) and the audit action `TRIAGED`. Public-form tickets start at MEDIUM with `needs_triage=true`; impact is required on the form and is never shown to the customer. Any agent's `PATCH /priority` clears the flag: a new priority is audited as `PRIORITY_CHANGED`, confirming the current one as `TRIAGED`. `GET /api/tickets` returns both fields (`?needs_triage=true` filters). Recorded in PROJECT_SUMMARY.md §3.1/§6/§7 and the README. Tests: `tests/test_triage.py` (16).

**Found in:** step 4
**Severity:** 🟡 Decision needed
**Fixed in:** step 5 (UI triage) or a quick decision

**What:** `create_customer_ticket()` sets `priority=MEDIUM`. PROJECT_SUMMARY.md doesn't say who sets priority on intake. Customers aren't allowed to choose it, because everyone would pick URGENT.

**Impact:** The SLA clock starts on the MEDIUM targets (4.5h first reply). If an agent later changes it to URGENT, the deadlines are recomputed from `created_at` (§3.6), so it may be breached straight away. That's correct per the rules, but agents need to triage quickly.

**Options:**
1. Keep MEDIUM as the default and show a "needs triage" marker in the list until an agent confirms it.
2. Default to URGENT (safest for SLA, noisiest).
3. Use keyword hints such as "down", "outage" or "cannot login", suggested but not applied automatically.

**Recommendation:** option 1. Record the decision in PROJECT_SUMMARY.md §3.1.
