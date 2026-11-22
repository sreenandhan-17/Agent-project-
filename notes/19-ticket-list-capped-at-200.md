# 19: The ticket list is capped at 200 rows with no pagination

**Found in:** step 5
**Severity:** 🟡 Silent truncation over time
**Fixed in:** after step 7, or record it in the "what I didn't finish" note

**What:** `GET /api/tickets` takes `limit` (default 200, max 500) and the UI never asks for more. At about 40 tickets a day, the **All** view passes 200 rows in roughly a week. Closed tickets sort last, so the oldest closed tickets drop off the bottom with no "more…" indicator.

**Impact:** Low for the working views (Mine, Unassigned, Late, Waiting and Needs triage only contain active tickets). Old tickets are still reachable by search, but the All view looks complete when it isn't.

**Fix:** use cursor pagination ordered by `(closed_last, next_due, id)` and a "Load more" button, or make **All** default to active tickets with a separate "Closed" tab. Also return `X-Total-Count` so the UI can say "showing 200 of 1,240".
