# 02: Festival holiday dates need verification

**What:** `seed.py` holds the 2026 holidays. The fixed dates are certain: Republic Day (Jan 26), Independence Day (Aug 15), Gandhi Jayanti (Oct 2), Labour Day (May 1) and Christmas (Dec 25). These lunar-calendar dates are best estimates:

| Holiday | Seeded date | Check |
|---|---|---|
| Holi | 2026-03-04 | |
| Id-ul-Fitr | 2026-03-20 | depends on moon sighting |
| Good Friday | 2026-04-03 | |
| Dussehra | 2026-10-20 | |
| Diwali | 2026-11-09 | Lakshmi Puja is Sun Nov 8; is Mon Nov 9 the office holiday? |

**Impact:** A wrong holiday shifts SLA deadlines by a full working day, which can make a ticket wrongly late or wrongly on time.

**Fix:** Confirm the dates against Arvo's official 2026 holiday list. Edit `HOLIDAYS` in `seed.py`, and update or insert the corrected rows in the `holidays` table (re-seeding only adds missing dates; it doesn't change existing ones).
