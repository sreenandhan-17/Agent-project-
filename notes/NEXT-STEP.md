# Next step: Build step 5, agent UI

Source of truth: PROJECT_SUMMARY.md §8. This step also closes **notes 11 and 16**, and should settle **15** (and **10** if decided).

## Backend first (the UI needs these)

- `GET /api/tickets?view=all|mine|unassigned|late|waiting&status=&priority=&q=`: list with customer name, assignee name and an **SLA state** per ticket: `{target: "first_response"|"resolution", due_at, state: "green"|"amber"|"red"|"paused", remaining_minutes}`.
  - **Late** must exclude paused, resolved and closed tickets (**note 11**).
  - Amber means less than 25% of the SLA budget is left. Grey "paused" whenever `paused_at` is set.
- `GET /api/tickets/{id}`: detail with **all** messages (including INTERNAL, marked as such), assignee, customer and SLA state.
- `GET /api/tickets/{id}/timeline`: audit events with actor names.
- `GET /api/agents`: names, for displaying assignees.
- Tests: the SLA state calculation (green/amber/red/paused boundaries), each view filter, and that a waiting ticket is never Late.

## Frontend (`/frontend`)

- **Login page:** store the token in `sessionStorage` (**note 16**). On any 401, clear it and go to `/login`.
- **Ticket list:** tabs for All, Mine, Unassigned, Late and Waiting; columns for number, subject, customer, priority, status, assignee and **SLA badge** (red/amber/green/grey, with a tooltip showing the due time in IST and the working time remaining); auto-refresh every 30 seconds.
- **Ticket detail:**
  - Header with status and priority controls (showing a 422 message on an invalid transition).
  - **Take ticket** button; on 409, a toast saying "Already taken by X" and a refresh.
  - **Conversation:** public messages, with internal notes inline as **yellow** cards labelled "Internal note".
  - **Reply box:** enabled only for the assignee; otherwise it shows "Take the ticket to reply".
  - **Internal note box:** separate and yellow.
  - **Timeline tab.**
- API base URL from `VITE_API_URL`, with a Vite dev proxy to `localhost:8000`.
- Never render message bodies with `dangerouslySetInnerHTML`.

## Prompt to start it

> Read CLAUDE.md, PROJECT_SUMMARY.md (§8) and notes/NEXT-STEP.md. Do build step 5: the list/detail/timeline endpoints with SLA state (fixing note 11), then the React UI (fixing note 16 with sessionStorage). Log any new issues as separate numbered files in notes/. Run pytest and `npm run build`, show the output, and start both servers so I can try it. If all pass, tick item 5, mark notes 11 and 16 resolved, update notes/NEXT-STEP.md for step 6, commit "Step 5: agent UI" and push to main.
