# Frontdesk

Support ticket system for Arvo Systems. The full plan is in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md), and open issues are tracked in [notes/](notes/README.md).

> Setup, deployment and the "what I didn't finish" note are added in build step 8 (notes/07).

## Decisions & assumptions

Business-rule choices that PROJECT_SUMMARY.md left open, and how they were settled.

### Permissions
- **Public replies:** only the ticket's assignee (403 otherwise). Agents must **Take ticket** first.
- **Internal notes:** any agent.
- **Status changes** (`PATCH /api/tickets/{id}/status`): only the **assignee** or an **ADMIN** (403 otherwise). The permission check runs before the transition check, so a non-assignee gets 403, not 422.
  - **Exception:** any agent may **close a NEW, unassigned ticket** (spam or duplicate) without claiming it.
  - Moving a ticket from NEW to OPEN happens by claiming it, not through `PATCH /status`.
- **Priority changes** (`PATCH /api/tickets/{id}/priority`): **any active agent**, so leads can triage unassigned tickets. Every change is audited with the old and new priority and deadlines.

### Triage (who sets priority)
- Customers **don't choose priority**. Public-form tickets start at **MEDIUM** with `needs_triage = true`, so the SLA clock runs from submission.
- The form asks for **impact** (*I can't work* / *partly affected* / *just a question*). This is a hint for agents only and never changes priority automatically.
- Any agent's priority change is the triage decision and clears the flag. Confirming the current priority is logged as `TRIAGED`; a new priority is logged as `PRIORITY_CHANGED`, with deadlines recomputed and possibly breached immediately.

### SLA
- Working time is 09:30–18:30 Asia/Kolkata, Mon–Fri, excluding the 2026 Central Government gazetted holidays (DoPT list).
- **URGENT "same working day":** resolve by 18:30 IST of the day the ticket starts counting, but never before the first-reply deadline (for example, a ticket created at 17:45 is due the next morning).
- **First response:** the first **public** agent reply. Internal notes don't count.
- **Waiting on customer:** pauses both clocks. The paused *working* minutes push both deadlines later when the ticket resumes.
- **Priority change:** deadlines are recomputed from `created_at` with the new priority, plus paused time. A ticket can be breached immediately.
