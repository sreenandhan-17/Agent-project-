# Next step: Build step 2, working-hours calculator + tests

Source of truth: PROJECT_SUMMARY.md §3.1–3.2. Rule: **all SLA times use this calculator** (CLAUDE.md).

## What to build

`backend/app/sla/working_hours.py`, made of pure functions with no database access. Holidays are passed in as a `set[date]`.

```python
TZ = ZoneInfo("Asia/Kolkata")
DAY_START = time(9, 30)
DAY_END = time(18, 30)
MINUTES_PER_DAY = 540

def is_working_day(d: date, holidays: set[date]) -> bool: ...
def next_working_moment(dt_utc: datetime, holidays) -> datetime: ...   # snap to next 09:30 if outside hours
def add_working_minutes(start_utc: datetime, minutes: int, holidays) -> datetime: ...
def working_minutes_between(a_utc: datetime, b_utc: datetime, holidays) -> int: ...
def end_of_working_day(dt_utc: datetime, holidays) -> datetime: ...   # for the URGENT "same day" rule
```

Also `backend/app/sla/policy.py`, which holds the SLA table:

| Priority | First reply | Resolve |
|---|---|---|
| URGENT | 120 min | end of the same working day (but never before the first-reply deadline) |
| MEDIUM | 270 min | 1,620 min |
| LOW | 540 min | 2,700 min |

**Rules:**
- Inputs and outputs are timezone-aware UTC datetimes. Convert to IST only inside the module. Raise an error on naive datetimes.
- Hop whole days at a time, never loop minute by minute.
- Adding minutes from exactly 18:30 rolls over to the next working day's 09:30.

## Test cases (`backend/tests/test_working_hours.py`)

These tests need no database.

| # | Case | Expected |
|---|---|---|
| 1 | LOW created **Fri 18:00**, +540 min | **Mon 18:00** (30 min Friday + 510 min Monday), so it's not late on Sunday |
| 2 | URGENT created Fri 18:00, +120 min | Mon 11:00 |
| 3 | Created Sat 14:00, +60 min | Mon 10:30 |
| 4 | Created Tue 08:00 (before opening), +30 min | Tue 10:00 |
| 5 | Created Fri 18:00, Monday is a holiday, +120 min | Tue 11:00 |
| 6 | MEDIUM created Wed 10:00, +1,620 min (3 days) | Mon 10:00 |
| 7 | Start at exactly 18:30, +1 min | next working day 09:31 |
| 8 | `working_minutes_between(Fri 18:00, Mon 10:00)` | 60 |
| 9 | `working_minutes_between` across a whole weekend plus a holiday | weekend and holiday count as 0 |
| 10 | Round trip: `between(s, add(s, n)) == n` for many `s` and `n` | always true |
| 11 | URGENT created Tue 17:45: resolve due | max(Tue 18:30, first-reply due of Wed 10:45) = Wed 10:45 |
| 12 | Naive datetime input | raises `ValueError` |

## Done when

- [ ] All of the tests above pass (`pytest tests/test_working_hours.py -v`)
- [ ] The existing 6 tests still pass
- [ ] Tick item 2 in PROJECT_SUMMARY.md, commit "Step 2: working-hours calculator", push

**Prompt to start it:**
> Read CLAUDE.md, PROJECT_SUMMARY.md and notes/NEXT-STEP.md. Do build step 2 only. Run pytest and show the output; if all pass, tick item 2, commit "Step 2: working-hours calculator" and push to main.
