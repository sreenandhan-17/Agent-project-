"""Working-hours calculator and SLA policy. Pure: no database.

Reference week (Nov 2026): Fri 20, Sat 21, Sun 22, Mon 23, Tue 24, Wed 25, Thu 26, Fri 27, Mon 30.
"""

import random
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Priority
from app.sla.policy import deadlines_for
from app.sla.working_hours import (
    TZ,
    add_working_minutes,
    end_of_working_day,
    is_working_day,
    next_working_moment,
    working_minutes_between,
)

NONE: set = set()


def ist(day: int, hour: int, minute: int = 0, month: int = 11) -> datetime:
    """A moment in IST, November 2026 by default."""
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


def holidays(*days: int) -> set:
    return {ist(d, 0).date() for d in days}


# --- §3.2: the Friday-evening case -------------------------------------------------------


def test_low_friday_1800_first_reply_due_monday_1800_not_late_on_sunday():
    first_due, _ = deadlines_for(Priority.LOW, ist(20, 18), 0, NONE)
    assert first_due == ist(23, 18)
    assert ist(22, 12) < first_due  # Sunday noon: not late


def test_urgent_friday_1800_first_reply_due_monday_1100():
    first_due, _ = deadlines_for(Priority.URGENT, ist(20, 18), 0, NONE)
    assert first_due == ist(23, 11)


def test_low_friday_1800_resolution_due_next_friday_1800():
    _, resolve_due = deadlines_for(Priority.LOW, ist(20, 18), 0, NONE)
    assert resolve_due == ist(27, 18)


# --- Outside working hours -> next 09:30 -------------------------------------------------


@pytest.mark.parametrize(
    "created, starts",
    [
        (ist(21, 10), ist(23, 9, 30)),  # Saturday
        (ist(22, 15), ist(23, 9, 30)),  # Sunday
        (ist(24, 7), ist(24, 9, 30)),  # 07:00 on a working day
        (ist(24, 20), ist(25, 9, 30)),  # 20:00 on a working day
        (ist(20, 20), ist(23, 9, 30)),  # Friday 20:00 -> Monday
    ],
)
def test_outside_hours_snaps_to_next_working_start(created, starts):
    assert next_working_moment(created, NONE) == starts
    assert add_working_minutes(created, 60, NONE) == starts + timedelta(minutes=60)


# --- Holidays ----------------------------------------------------------------------------


def test_midweek_holiday_is_skipped():
    # MEDIUM resolution (1620 min) from Tue 10:00. Normally Fri 10:00; Wed holiday -> Mon 10:00.
    assert add_working_minutes(ist(24, 10), 1620, NONE) == ist(27, 10)
    assert add_working_minutes(ist(24, 10), 1620, holidays(25)) == ist(30, 10)


def test_monday_holiday_after_weekend():
    first_due, _ = deadlines_for(Priority.URGENT, ist(20, 18), 0, holidays(23))
    assert first_due == ist(24, 11)


def test_created_on_holiday_starts_next_working_day():
    assert next_working_moment(ist(25, 11), holidays(25)) == ist(26, 9, 30)


def test_is_working_day():
    assert is_working_day(ist(23, 0).date(), NONE)
    assert not is_working_day(ist(21, 0).date(), NONE)  # Saturday
    assert not is_working_day(ist(23, 0).date(), holidays(23))


# --- Multi-day spans ---------------------------------------------------------------------


def test_medium_three_day_resolution_spans_weekend():
    _, resolve_due = deadlines_for(Priority.MEDIUM, ist(25, 10), 0, NONE)
    assert resolve_due == ist(30, 10)  # Wed 10:00 -> Mon 10:00


# --- Boundaries --------------------------------------------------------------------------


def test_exactly_0930_is_inside_working_hours():
    assert next_working_moment(ist(23, 9, 30), NONE) == ist(23, 9, 30)
    assert add_working_minutes(ist(23, 9, 30), 540, NONE) == ist(23, 18, 30)


def test_exactly_1830_is_outside_working_hours():
    assert next_working_moment(ist(23, 18, 30), NONE) == ist(24, 9, 30)
    assert add_working_minutes(ist(23, 18, 30), 1, NONE) == ist(24, 9, 31)


def test_deadline_landing_on_1830_stays_that_day():
    assert add_working_minutes(ist(23, 18), 30, NONE) == ist(23, 18, 30)


def test_adding_zero_returns_start():
    assert add_working_minutes(ist(21, 10), 0, NONE) == ist(21, 10)


def test_end_of_working_day():
    assert end_of_working_day(ist(23, 11), NONE) == ist(23, 18, 30)
    assert end_of_working_day(ist(23, 19), NONE) == ist(24, 18, 30)
    assert end_of_working_day(ist(21, 11), NONE) == ist(23, 18, 30)


# --- working_minutes_between -------------------------------------------------------------


def test_between_same_day():
    assert working_minutes_between(ist(23, 10), ist(23, 12, 15), NONE) == 135


def test_between_across_weekend():
    assert working_minutes_between(ist(20, 18), ist(23, 10), NONE) == 60


def test_between_across_holiday():
    assert working_minutes_between(ist(24, 18), ist(26, 10), holidays(25)) == 60
    assert working_minutes_between(ist(24, 18), ist(26, 10), NONE) == 600


def test_between_weekend_only_is_zero():
    assert working_minutes_between(ist(21, 9), ist(22, 20), NONE) == 0


def test_between_reversed_or_equal_is_zero():
    assert working_minutes_between(ist(23, 12), ist(23, 10), NONE) == 0
    assert working_minutes_between(ist(23, 12), ist(23, 12), NONE) == 0


# --- Round trip --------------------------------------------------------------------------


def test_round_trip_add_then_measure():
    rng = random.Random(1234)
    hols = {ist(24, 0).date(), ist(25, 0, month=12).date()}
    base = ist(1, 0)
    for _ in range(2000):
        start = base + timedelta(minutes=rng.randrange(60 * 24 * 60))  # any minute in ~60 days
        minutes = rng.randrange(0, 6000)
        end = add_working_minutes(start, minutes, hols)
        assert working_minutes_between(start, end, hols) == minutes, (start, minutes)


# --- SLA policy rules --------------------------------------------------------------------


def test_urgent_created_1745_resolution_equals_first_response_due():
    first_due, resolve_due = deadlines_for(Priority.URGENT, ist(24, 17, 45), 0, NONE)
    assert first_due == ist(25, 10, 45)
    assert resolve_due == first_due


def test_urgent_created_morning_resolves_same_day():
    first_due, resolve_due = deadlines_for(Priority.URGENT, ist(23, 10), 0, NONE)
    assert first_due == ist(23, 12)
    assert resolve_due == ist(23, 18, 30)


def test_paused_minutes_push_deadlines_later():
    first, resolve = deadlines_for(Priority.MEDIUM, ist(23, 10), 0, NONE)
    first_p, resolve_p = deadlines_for(Priority.MEDIUM, ist(23, 10), 60, NONE)
    assert (first, first_p) == (ist(23, 14, 30), ist(23, 15, 30))
    assert (resolve, resolve_p) == (ist(26, 10), ist(26, 11))


def test_paused_minutes_push_urgent_same_day_into_next_day():
    _, resolve_due = deadlines_for(Priority.URGENT, ist(23, 10), 60, NONE)
    assert resolve_due == ist(24, 10, 30)


def test_priority_change_recomputes_from_created_at():
    # A LOW ticket from Monday 10:00 bumped to URGENT on Wednesday is already breached.
    created = ist(23, 10)
    first_due, _ = deadlines_for(Priority.URGENT, created, 0, NONE)
    assert first_due == ist(23, 12) < ist(25, 10)


# --- Input validation & output format ----------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda naive: next_working_moment(naive, NONE),
        lambda naive: add_working_minutes(naive, 10, NONE),
        lambda naive: working_minutes_between(naive, ist(23, 10), NONE),
        lambda naive: working_minutes_between(ist(23, 10), naive, NONE),
        lambda naive: end_of_working_day(naive, NONE),
    ],
)
def test_naive_datetimes_rejected(call):
    with pytest.raises(ValueError):
        call(datetime(2026, 11, 23, 10, 0))


def test_negative_minutes_rejected():
    with pytest.raises(ValueError):
        add_working_minutes(ist(23, 10), -1, NONE)


def test_results_are_utc():
    result = add_working_minutes(ist(23, 10), 30, NONE)
    assert result.tzinfo == timezone.utc
    assert result == datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)  # 10:30 IST
