# 08: Endpoints trust an `X-Agent-Id` header (temporary auth)

**Found in:** step 3
**Severity:** 🔴 Security, must fix before deploy
**Fixed in:** step 4 or 5, before step 6 (deploy)

**What:** `app/deps.py:get_current_agent` identifies the agent from an `X-Agent-Id` request header. Anyone who can reach the API can act as any agent by sending a different number.

**Why:** Login (JWT) isn't built yet, but the status and priority endpoints need an actor for the audit log.

**Impact:** The audit trail (INC-0318) can be faked, and the assignee-only reply rule (INC-0291, step 4) could be bypassed.

**Fix:**
1. Add `POST /api/auth/login` (bcrypt check, signed with `JWT_SECRET`) and `GET /api/auth/me`.
2. Change `get_current_agent` to read `Authorization: Bearer <jwt>`, keeping the same function name so routers don't change.
3. Update `tests/test_ticket_api.py` to log in or mint a token instead of sending `X-Agent-Id`.

**Done when:** a search for `X-Agent-Id` in `backend/app` finds nothing, and requests without a valid token get 401.
