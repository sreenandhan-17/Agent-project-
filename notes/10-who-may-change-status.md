# 10: Any agent can change any ticket's status or priority

> **✅ RESOLVED (decision: option 2).** `PATCH /status` is limited to the assignee or an ADMIN (403 otherwise), checked before transition validity. Exception: any agent may close a NEW unassigned ticket as spam or a duplicate. `PATCH /priority` is open to any active agent and audited. Implemented in `may_change_status()` (`app/services/tickets.py`). Recorded in PROJECT_SUMMARY.md §4/§5 and in README "Decisions & assumptions". Tests: `tests/test_status_permissions.py` (12 tests).

**Found in:** step 3
**Severity:** 🟡 Decision needed
**Fixed in:** step 4 (alongside claim and assignee rules)

**What:** `PATCH /status` and `PATCH /priority` accept any active agent. PROJECT_SUMMARY.md only restricts **public replies** to the assignee (INC-0291) and says nothing about status or priority changes.

**Options:**
1. **Leave it open** to any agent (simplest; the audit log shows who did it).
2. **Assignee or ADMIN only** for status changes, with any agent allowed to change priority (triage).
3. **Assignee or ADMIN only** for both.

**Recommendation:** option 2. It is consistent with "only the assignee replies", while still letting a lead re-prioritise unassigned tickets.

**Fix:** decide, then add the check in the router (return 403), add tests, and record the decision in PROJECT_SUMMARY.md §4/§5.
