# 03: Deprecation warning in pytest output

**What:** `6 passed, 1 warning`. The warning comes from inside Starlette's `TestClient`:
`DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated`.

**Impact:** None. It's a library issue, not our code.

**Fix (pick one):**
- Upgrade FastAPI/Starlette once a release fixes it, or
- Silence it in `backend/pytest.ini`:
  ```ini
  filterwarnings =
      ignore:The anyio.abc.BlockingPortal alias is deprecated:DeprecationWarning
  ```
