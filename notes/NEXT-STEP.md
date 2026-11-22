# Next step: Build step 4, atomic claim + PUBLIC/INTERNAL separation

Source of truth: PROJECT_SUMMARY.md §4 (INC-0291, INC-0304) and §7. This step also closes **notes 10 and 12**.

## What to build

1. **Atomic claim (INC-0291):** `POST /api/tickets/{id}/claim`
   - `UPDATE tickets SET assignee_id=:me, status='OPEN' WHERE id=:id AND assignee_id IS NULL RETURNING id`
   - 1 row: 200, plus `CLAIMED` and `STATUS_CHANGED` (NEW → OPEN) audit events in the same transaction.
   - 0 rows: if the ticket is already mine, 200 (idempotent); otherwise **409** with the current assignee's name; unknown ticket, 404.
2. **Replies:** `POST /api/tickets/{id}/replies` (PUBLIC)
   - Assignee only: 403 otherwise, and 409 if the ticket is unassigned ("claim first").
   - Sets `first_response_at` on the first reply (**note 12**). Writes a `REPLY_SENT` audit event.
3. **Notes:** `POST /api/tickets/{id}/notes` (INTERNAL). Any agent. Writes a `NOTE_ADDED` audit event. Never sets `first_response_at`.
4. **Single customer serializer (INC-0304):** `app/serializers/customer.py: serialize_for_customer(ticket)`, which drops every INTERNAL message. Plus `serialize_for_agent(ticket)`, which includes internal notes.
5. **Public routes** using only that serializer:
   - `GET /api/public/tickets/{token}`
   - `POST /api/public/tickets/{token}/replies` (resumes the SLA if the ticket was waiting)
   - `GET /api/tickets/{id}/export` (transcript)
   - `render_customer_email(ticket)` (logged, not sent)
6. **Status/priority permission (note 10):** apply the decided rule. Recommended: assignee or ADMIN for status changes, any agent for priority.

## Tests

- **Concurrent claim:** two threads with separate DB connections claim the same ticket; exactly one 200 and one 409.
- Reply by a non-assignee is 403; reply on an unassigned ticket is 409.
- `first_response_at` is set by the first public reply only; internal notes don't set it.
- **Leak test:** an internal note containing a sentinel `SECRET-NOTE-7f3a` never appears in the public GET, the export, the email render, or the response to a customer reply.
- **Route inventory:** every `/api/public/*` route is in the leak-tested list; a new uncovered route fails the test.

## Prompt to start it

> Read CLAUDE.md, PROJECT_SUMMARY.md (§4, §7) and notes/NEXT-STEP.md. Do build step 4 only, including notes 10 (use the recommended option) and 12. Log any new issues as separate numbered files in notes/. Run pytest and show the output; if all pass, tick item 4, mark notes 10 and 12 resolved, update notes/NEXT-STEP.md for step 5, commit "Step 4: atomic claim, public/internal separation" and push to main.
