"""Working-time arithmetic. See PROJECT_SUMMARY.md §3.2.

Working time is 09:30-18:30 Asia/Kolkata, Monday-Friday, excluding holidays.
All inputs and outputs are timezone-aware datetimes; outputs are in UTC.
Pure functions: holidays are passed in, nothing touches the database.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kolkata")
DAY_START = time(9, 30)
DAY_END = time(18, 30)
MINUTES_PER_DAY = 540

# Guard against an endless search if someone loads a holiday table covering every day.
_MAX_DAYS_SEARCHED = 366 * 5


def _require_aware(dt: datetime) -> None:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"naive datetime not allowed: {dt!r}")


def _at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=TZ)


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


def is_working_day(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def _next_working_date(d: date, holidays: set[date]) -> date:
    """First working date strictly after d."""
    for _ in range(_MAX_DAYS_SEARCHED):
        d += timedelta(days=1)
        if is_working_day(d, holidays):
            return d
    raise ValueError("no working day found; check the holidays table")


def next_working_moment(dt_utc: datetime, holidays: set[date]) -> datetime:
    """dt itself if it falls inside working hours, else the next 09:30 working-day start.

    Exactly 18:30 is outside (the day is used up); exactly 09:30 is inside.
    """
    _require_aware(dt_utc)
    local = dt_utc.astimezone(TZ)
    d = local.date()
    if is_working_day(d, holidays):
        if local < _at(d, DAY_START):
            return _utc(_at(d, DAY_START))
        if local < _at(d, DAY_END):
            return _utc(local)
    return _utc(_at(_next_working_date(d, holidays), DAY_START))


def add_working_minutes(start_utc: datetime, minutes: int, holidays: set[date]) -> datetime:
    """The moment `minutes` working minutes after start.

    Adding 0 returns start unchanged. A result landing exactly on 18:30 stays on that day.
    """
    _require_aware(start_utc)
    if minutes < 0:
        raise ValueError("minutes must be >= 0")
    if minutes == 0:
        return _utc(start_utc)

    remaining = timedelta(minutes=minutes)
    cur = next_working_moment(start_utc, holidays).astimezone(TZ)
    while True:
        available = _at(cur.date(), DAY_END) - cur
        if remaining <= available:
            return _utc(cur + remaining)
        remaining -= available
        cur = _at(_next_working_date(cur.date(), holidays), DAY_START)


def working_minutes_between(a_utc: datetime, b_utc: datetime, holidays: set[date]) -> int:
    """Whole working minutes in [a, b). 0 if b <= a."""
    _require_aware(a_utc)
    _require_aware(b_utc)
    if b_utc <= a_utc:
        return 0

    a, b = a_utc.astimezone(TZ), b_utc.astimezone(TZ)
    total = timedelta()
    d = a.date()
    while d <= b.date():
        if is_working_day(d, holidays):
            lo = max(a, _at(d, DAY_START))
            hi = min(b, _at(d, DAY_END))
            if hi > lo:
                total += hi - lo
        d += timedelta(days=1)
    return int(total.total_seconds() // 60)


def end_of_working_day(dt_utc: datetime, holidays: set[date]) -> datetime:
    """18:30 IST of the working day that dt counts on (the next one if dt is outside hours)."""
    start = next_working_moment(dt_utc, holidays).astimezone(TZ)
    return _utc(_at(start.date(), DAY_END))
