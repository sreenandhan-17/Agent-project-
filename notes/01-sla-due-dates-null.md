# 01: SLA due dates are NULL on seeded tickets

> **✅ RESOLVED in step 2.** `seed.py` now calls `compute_deadlines()` on every ticket it creates, and `python -m scripts.backfill_deadlines` filled the 10 existing rows. Verified: `SELECT count(*) FROM tickets WHERE resolution_due_at IS NULL` returns 0.

**What:** `first_response_due_at` and `resolution_due_at` are empty for all 10 seeded tickets.

**Why:** Due dates must come from the working-hours calculator (CLAUDE.md rule 3), which doesn't exist yet.

**Impact:** None yet. Nothing reads these columns. The list's Late filter and the SLA badges (step 5) will need them.

**Fix:**
1. Step 2: build `backend/app/sla/working_hours.py`.
2. Step 3: add `compute_deadlines(ticket, holidays)` and call it on create, priority change and resume.
3. Update `seed.py` to call `compute_deadlines()`, and backfill the existing rows with a one-off script or by re-seeding a fresh database.

**Done when:** `SELECT count(*) FROM tickets WHERE resolution_due_at IS NULL` returns 0.
